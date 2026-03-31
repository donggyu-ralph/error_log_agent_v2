"""REST API endpoints for the agent and dashboard."""
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Depends

from src.auth.deps import get_current_user, require_auth, require_role
from src.auth.schemas import UserRole
from src.config.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Will be set during app startup
_db = None


def set_db(db):
    global _db
    _db = db


# --- Dashboard API ---

async def _get_user_service_names(user: dict | None) -> list[str] | None:
    """Get service names the user has access to. None = all (admin or unauthenticated)."""
    if not user or user.get("role") == "admin":
        return None  # No filter
    services = await _db.list_user_services(user["id"])
    return [s["name"] for s in services]


@router.get("/api/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    """Dashboard summary data (filtered by user's services)."""
    svc_names = await _get_user_service_names(user)

    errors = await _db.list_error_logs(limit=10)
    history = await _db.list_fix_history(limit=5)
    timeline = await _db.get_error_timeline(days=7)
    by_type = await _db.get_error_by_type(days=7)

    # Filter by user's services
    if svc_names is not None:
        errors = [e for e in errors if e.get("service_name") in svc_names]
        history = [h for h in history if True]  # Fix history doesn't have service_name yet

    return {
        "recent_errors": errors,
        "recent_fixes": history,
        "timeline": timeline,
        "by_type": by_type,
        "total_errors_today": sum(
            t.get("total", 0) for t in timeline
            if timeline and str(t.get("date")) == str(timeline[-1].get("date"))
        ),
    }


@router.get("/api/dashboard/errors")
async def list_errors(
    service_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """List error logs (filtered by user's services)."""
    errors = await _db.list_error_logs(service_name=service_name, limit=limit, offset=offset)

    svc_names = await _get_user_service_names(user)
    if svc_names is not None:
        errors = [e for e in errors if e.get("service_name") in svc_names]

    return errors


@router.get("/api/dashboard/errors/{error_id}")
async def get_error(error_id: str):
    """Get error details."""
    # Simplified: use list with limit 1
    errors = await _db.list_error_logs(limit=200)
    for e in errors:
        if str(e.get("id")) == error_id:
            return e
    raise HTTPException(status_code=404, detail="Error not found")


@router.get("/api/dashboard/stats/timeline")
async def error_timeline(days: int = Query(7, ge=1, le=90)):
    """Error count timeline."""
    return await _db.get_error_timeline(days=days)


@router.get("/api/dashboard/stats/by-type")
async def errors_by_type(days: int = Query(7, ge=1, le=90)):
    """Error count by type."""
    return await _db.get_error_by_type(days=days)


@router.get("/api/dashboard/history")
async def fix_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List fix history."""
    return await _db.list_fix_history(limit=limit, offset=offset)


# --- Monitored Services ---

@router.get("/api/dashboard/services")
async def list_services(user: dict = Depends(get_current_user)):
    """List services. Authenticated: my services only. Unauthenticated/Admin: all."""
    if user and user.get("role") != "admin":
        return await _db.list_user_services(user["id"])
    return await _db.list_monitored_services()


@router.post("/api/dashboard/services", status_code=201)
async def add_service(service: dict, user: dict = Depends(require_role(UserRole.OPERATOR))):
    """Add a monitored service. Caller becomes Owner."""
    service["created_by"] = user["id"]
    svc_id = await _db.add_monitored_service(**service)

    # Add caller as owner
    await _db.add_service_member(svc_id, user["id"], role="owner")

    # Create Slack channel
    slack_channel_id = await _create_slack_channel(service.get("name", ""))
    if slack_channel_id:
        await _db.update_monitored_service(svc_id, slack_channel_id=slack_channel_id)
        # Invite owner to channel
        await _invite_to_slack_channel(slack_channel_id, user.get("slack_user_id"))

    return {"id": svc_id}


@router.get("/api/services/{service_id}")
async def get_service_detail(service_id: str, user: dict = Depends(require_auth)):
    """Get service detail."""
    svc = await _db.get_service_by_id(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    # Check access
    if user.get("role") != "admin":
        is_member = await _db.is_service_member(service_id, user["id"])
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this service")

    members = await _db.list_service_members(service_id)
    svc["members"] = members
    return svc


@router.put("/api/dashboard/services/{service_id}")
async def update_service(service_id: str, updates: dict, user: dict = Depends(require_auth)):
    """Update a monitored service (Owner only)."""
    role = await _db.get_service_member_role(service_id, user["id"])
    if role != "owner" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only owner can update service")
    await _db.update_monitored_service(service_id, **updates)
    return {"status": "updated"}


@router.delete("/api/dashboard/services/{service_id}", status_code=204)
async def delete_service(service_id: str, user: dict = Depends(require_auth)):
    """Remove a monitored service (Owner only)."""
    role = await _db.get_service_member_role(service_id, user["id"])
    if role != "owner" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only owner can delete service")
    await _db.delete_monitored_service(service_id)


# --- Service Members ---

@router.get("/api/services/{service_id}/members")
async def list_members(service_id: str, user: dict = Depends(require_auth)):
    """List members of a service."""
    if user.get("role") != "admin":
        is_member = await _db.is_service_member(service_id, user["id"])
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member")
    return await _db.list_service_members(service_id)


@router.post("/api/services/{service_id}/members", status_code=201)
async def invite_member(service_id: str, body: dict, user: dict = Depends(require_auth)):
    """Invite a member to a service (Owner only)."""
    role = await _db.get_service_member_role(service_id, user["id"])
    if role != "owner" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only owner can invite members")

    email = body.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    # Find user by email
    import src.auth.deps as auth_deps
    target_user = None
    if auth_deps._user_manager:
        users = await auth_deps._user_manager.list_users()
        for u in users:
            if u["email"] == email:
                target_user = u
                break

    if not target_user:
        raise HTTPException(status_code=404, detail=f"User {email} not found")

    # Check already member
    if await _db.is_service_member(service_id, target_user["id"]):
        raise HTTPException(status_code=409, detail="Already a member")

    member_id = await _db.add_service_member(service_id, target_user["id"], role="member", invited_by=user["id"])

    # Invite to Slack channel
    svc = await _db.get_service_by_id(service_id)
    if svc and svc.get("slack_channel_id"):
        await _invite_to_slack_channel(svc["slack_channel_id"], target_user.get("slack_user_id"))

    return {"id": member_id, "email": email}


@router.delete("/api/services/{service_id}/members/{user_id}", status_code=204)
async def remove_member(service_id: str, user_id: str, user: dict = Depends(require_auth)):
    """Remove a member from a service (Owner only)."""
    role = await _db.get_service_member_role(service_id, user["id"])
    if role != "owner" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only owner can remove members")

    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    success = await _db.remove_service_member(service_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Member not found")


# --- Slack Channel Helpers ---

async def _create_slack_channel(service_name: str) -> str | None:
    """Create a Slack channel for a service."""
    try:
        from src.slack.bot import get_slack_app
        from src.config.settings import get_settings
        settings = get_settings()
        if not settings.slack.enabled:
            return None

        app = get_slack_app()
        channel_name = f"svc-{service_name.lower().replace(' ', '-').replace('_', '-')[:70]}"
        result = await app.client.conversations_create(name=channel_name)
        return result["channel"]["id"]
    except Exception as e:
        logger.warning("slack_channel_creation_failed", error=str(e))
        return None


async def _invite_to_slack_channel(channel_id: str, slack_user_id: str | None) -> None:
    """Invite a user to a Slack channel."""
    if not channel_id or not slack_user_id:
        return
    try:
        from src.slack.bot import get_slack_app
        app = get_slack_app()
        await app.client.conversations_invite(channel=channel_id, users=slack_user_id)
    except Exception as e:
        logger.warning("slack_invite_failed", error=str(e))
