"""Authentication dependencies for FastAPI."""
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.auth.manager import verify_token
from src.auth.schemas import UserRole

security = HTTPBearer(auto_error=False)

# Will be set during app startup
_user_manager = None


def set_user_manager(manager):
    global _user_manager
    _user_manager = manager


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Get current user from JWT token. Returns None if no token."""
    if not credentials:
        return None

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if _user_manager:
        user = await _user_manager.get_user_by_id(payload["user_id"])
        if not user or not user.get("is_active"):
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user

    return payload


async def require_auth(user: dict = Depends(get_current_user)) -> dict:
    """Require authentication. Returns 401 if not authenticated."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_role(*roles: UserRole):
    """Require specific role(s). Returns 403 if insufficient permissions."""
    async def check_role(user: dict = Depends(require_auth)) -> dict:
        user_role = user.get("role", "viewer")
        # Admin can do everything
        if user_role == UserRole.ADMIN.value:
            return user
        if user_role not in [r.value for r in roles]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check_role
