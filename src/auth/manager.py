"""User manager: DB operations for authentication."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import hashlib
import secrets

from jose import jwt, JWTError

from src.auth.schemas import UserRole, UserRead
from src.config.logging_config import get_logger

logger = get_logger(__name__)

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "error-log-agent-v2-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${hashed}"


def _verify_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt, hashed = stored.split("$", 1)
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == hashed

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN DEFAULT TRUE,
    slack_user_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);
"""


class UserManager:
    def __init__(self, conn):
        self.conn = conn

    async def initialize(self):
        with self.conn.cursor() as cur:
            cur.execute(INIT_SQL)
        # Create initial admin if no users exist
        await self._ensure_admin()

    async def _ensure_admin(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            if count == 0:
                admin_email = os.environ.get("ADMIN_EMAIL", "admin@atdev.co.kr")
                admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
                await self.create_user(admin_email, admin_password, UserRole.ADMIN)
                logger.info("initial_admin_created", email=admin_email)

    async def create_user(self, email: str, password: str, role: UserRole = UserRole.VIEWER) -> dict:
        user_id = str(uuid.uuid4())
        hashed = _hash_password(password)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, email, hashed_password, role) VALUES (%s, %s, %s, %s) RETURNING created_at",
                (user_id, email, hashed, role.value),
            )
            created_at = cur.fetchone()[0]
        return {"id": user_id, "email": email, "role": role.value, "is_active": True,
                "slack_user_id": None, "created_at": created_at}

    async def authenticate(self, email: str, password: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, email, hashed_password, role, is_active, slack_user_id, created_at FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            if not row:
                return None
            if not _verify_password(password, row[2]):
                return None
            if not row[4]:  # is_active
                return None
            return {"id": str(row[0]), "email": row[1], "role": row[3], "is_active": row[4],
                    "slack_user_id": row[5], "created_at": row[6]}

    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, email, role, is_active, slack_user_id, created_at FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {"id": str(row[0]), "email": row[1], "role": row[2], "is_active": row[3],
                    "slack_user_id": row[4], "created_at": row[5]}

    async def get_user_by_slack_id(self, slack_user_id: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, email, role, is_active, slack_user_id, created_at FROM users WHERE slack_user_id = %s", (slack_user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {"id": str(row[0]), "email": row[1], "role": row[2], "is_active": row[3],
                    "slack_user_id": row[4], "created_at": row[5]}

    async def list_users(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, email, role, is_active, slack_user_id, created_at FROM users ORDER BY created_at")
            return [{"id": str(r[0]), "email": r[1], "role": r[2], "is_active": r[3],
                     "slack_user_id": r[4], "created_at": r[5]} for r in cur.fetchall()]

    async def update_user(self, user_id: str, **kwargs) -> bool:
        if not kwargs:
            return False
        set_parts = []
        values = []
        for k, v in kwargs.items():
            if k in ("role", "is_active", "slack_user_id"):
                set_parts.append(f"{k} = %s")
                values.append(v)
        if not set_parts:
            return False
        values.append(user_id)
        with self.conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {', '.join(set_parts)} WHERE id = %s", values)
            return cur.rowcount > 0

    async def delete_user(self, user_id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            return cur.rowcount > 0


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"user_id": payload.get("sub"), "role": payload.get("role")}
    except JWTError:
        return None
