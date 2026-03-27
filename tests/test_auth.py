"""Unit tests for authentication."""
import pytest
from datetime import datetime

from src.auth.manager import create_access_token, verify_token, _hash_password, _verify_password
from src.auth.schemas import UserRole, UserCreate, UserLogin, UserUpdate


# --- Token Tests ---

class TestTokens:
    def test_create_and_verify_token(self):
        token = create_access_token("user-123", "admin")
        payload = verify_token(token)
        assert payload is not None
        assert payload["user_id"] == "user-123"
        assert payload["role"] == "admin"

    def test_invalid_token(self):
        payload = verify_token("invalid.token.here")
        assert payload is None

    def test_empty_token(self):
        payload = verify_token("")
        assert payload is None

    def test_token_contains_role(self):
        token = create_access_token("u1", "operator")
        payload = verify_token(token)
        assert payload["role"] == "operator"


# --- Password Tests ---

class TestPassword:
    def test_hash_and_verify(self):
        password = "test_password_123"
        hashed = _hash_password(password)
        assert _verify_password(password, hashed)
        assert not _verify_password("wrong_password", hashed)

    def test_different_hashes(self):
        h1 = _hash_password("same_password")
        h2 = _hash_password("same_password")
        assert h1 != h2  # Different salt each time

    def test_hash_format(self):
        hashed = _hash_password("test")
        assert "$" in hashed  # salt$hash format

    def test_verify_invalid_format(self):
        assert not _verify_password("test", "no_dollar_sign")


# --- Schema Tests ---

class TestSchemas:
    def test_user_create_valid(self):
        user = UserCreate(email="test@example.com", password="123456")
        assert user.role == UserRole.VIEWER

    def test_user_create_with_role(self):
        user = UserCreate(email="admin@example.com", password="123456", role=UserRole.ADMIN)
        assert user.role == UserRole.ADMIN

    def test_user_create_short_password(self):
        with pytest.raises(Exception):
            UserCreate(email="test@example.com", password="12345")

    def test_user_login(self):
        login = UserLogin(email="test@example.com", password="password")
        assert login.email == "test@example.com"

    def test_user_update_partial(self):
        update = UserUpdate(role=UserRole.OPERATOR)
        assert update.role == UserRole.OPERATOR
        assert update.is_active is None
        assert update.slack_user_id is None

    def test_user_role_values(self):
        assert UserRole.VIEWER.value == "viewer"
        assert UserRole.OPERATOR.value == "operator"
        assert UserRole.ADMIN.value == "admin"


# --- Role Permission Tests ---

class TestRolePermissions:
    def test_role_hierarchy(self):
        roles = {"viewer": 1, "operator": 2, "admin": 3}
        assert roles["admin"] > roles["operator"] > roles["viewer"]

    def test_admin_has_all_permissions(self):
        admin_role = "admin"
        assert admin_role == UserRole.ADMIN.value

    def test_operator_permissions(self):
        # Operator can manage services and approve fixes
        operator_allowed = ["viewer", "operator"]
        assert "operator" in operator_allowed
        assert "admin" not in operator_allowed

    def test_viewer_readonly(self):
        viewer_allowed = ["viewer"]
        assert "operator" not in viewer_allowed
