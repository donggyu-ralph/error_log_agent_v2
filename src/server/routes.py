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

@router.get("/api/dashboard/summary")
async def dashboard_summary():
    """Dashboard summary data."""
    errors = await _db.list_error_logs(limit=10)
    history = await _db.list_fix_history(limit=5)
    timeline = await _db.get_error_timeline(days=7)
    by_type = await _db.get_error_by_type(days=7)

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
):
    """List error logs with optional filter."""
    return await _db.list_error_logs(service_name=service_name, limit=limit, offset=offset)


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
async def list_services():
    """List monitored services."""
    return await _db.list_monitored_services()


@router.post("/api/dashboard/services", status_code=201)
async def add_service(service: dict, user: dict = Depends(require_role(UserRole.OPERATOR))):
    """Add a monitored service (Operator+)."""
    svc_id = await _db.add_monitored_service(**service)
    return {"id": svc_id}


@router.put("/api/dashboard/services/{service_id}")
async def update_service(service_id: str, updates: dict, user: dict = Depends(require_role(UserRole.OPERATOR))):
    """Update a monitored service (Operator+)."""
    await _db.update_monitored_service(service_id, **updates)
    return {"status": "updated"}


@router.delete("/api/dashboard/services/{service_id}", status_code=204)
async def delete_service(service_id: str, user: dict = Depends(require_role(UserRole.OPERATOR))):
    """Remove a monitored service (Operator+)."""
    await _db.delete_monitored_service(service_id)
