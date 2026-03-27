"""Authentication API routes."""
from fastapi import APIRouter, Depends, HTTPException

from src.auth.schemas import UserCreate, UserLogin, UserUpdate, UserRead, UserRole, TokenResponse
from src.auth.manager import create_access_token
from src.auth.deps import require_auth, require_role, _user_manager

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=201)
async def register(data: UserCreate):
    """Register a new user."""
    try:
        user = await _user_manager.create_user(data.email, data.password, data.role)
        return UserRead(**user)
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Email already registered")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin):
    """Login and get JWT token."""
    user = await _user_manager.authenticate(data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user["id"], user["role"])
    return TokenResponse(access_token=token, user=UserRead(**user))


@router.get("/me", response_model=UserRead)
async def get_me(user: dict = Depends(require_auth)):
    """Get current user info."""
    return UserRead(**user)


@router.get("/users", response_model=list[UserRead])
async def list_users(user: dict = Depends(require_role(UserRole.ADMIN))):
    """List all users (Admin only)."""
    users = await _user_manager.list_users()
    return [UserRead(**u) for u in users]


@router.put("/users/{user_id}", response_model=dict)
async def update_user(
    user_id: str,
    data: UserUpdate,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """Update user role/status (Admin only)."""
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    success = await _user_manager.update_user(user_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated"}


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """Delete a user (Admin only)."""
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    success = await _user_manager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
