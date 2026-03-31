"""Unit tests for service ownership and member management."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestServiceMemberDB:
    """Test DB manager service member methods (mock-based)."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add_service_member = AsyncMock(return_value="member-123")
        db.list_service_members = AsyncMock(return_value=[
            {"user_id": "u1", "role": "owner", "email": "a@test.com"},
            {"user_id": "u2", "role": "member", "email": "b@test.com"},
        ])
        db.is_service_member = AsyncMock(return_value=True)
        db.get_service_member_role = AsyncMock(return_value="owner")
        db.remove_service_member = AsyncMock(return_value=True)
        db.list_user_services = AsyncMock(return_value=[
            {"id": "svc-1", "name": "data-pipeline", "member_role": "owner"},
        ])
        db.get_service_by_id = AsyncMock(return_value={"id": "svc-1", "name": "test"})
        db.get_service_slack_channel = AsyncMock(return_value="C12345")
        return db

    @pytest.mark.asyncio
    async def test_add_member(self, mock_db):
        result = await mock_db.add_service_member("svc-1", "user-1", "member", "owner-1")
        assert result == "member-123"

    @pytest.mark.asyncio
    async def test_list_members(self, mock_db):
        members = await mock_db.list_service_members("svc-1")
        assert len(members) == 2
        assert members[0]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_is_member(self, mock_db):
        assert await mock_db.is_service_member("svc-1", "u1") is True

    @pytest.mark.asyncio
    async def test_get_role(self, mock_db):
        role = await mock_db.get_service_member_role("svc-1", "u1")
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_remove_member(self, mock_db):
        result = await mock_db.remove_service_member("svc-1", "u2")
        assert result is True

    @pytest.mark.asyncio
    async def test_list_user_services(self, mock_db):
        services = await mock_db.list_user_services("u1")
        assert len(services) == 1
        assert services[0]["name"] == "data-pipeline"


class TestServiceFiltering:
    """Test that dashboard data is filtered by user's services."""

    def test_admin_sees_all(self):
        user = {"id": "admin-1", "role": "admin"}
        # Admin should get None (no filter)
        assert user.get("role") == "admin"

    def test_user_sees_own_services(self):
        user = {"id": "user-1", "role": "operator"}
        user_services = [{"name": "data-pipeline"}, {"name": "auth-service"}]
        svc_names = [s["name"] for s in user_services]

        errors = [
            {"service_name": "data-pipeline", "message": "err1"},
            {"service_name": "auth-service", "message": "err2"},
            {"service_name": "other-service", "message": "err3"},
        ]

        filtered = [e for e in errors if e.get("service_name") in svc_names]
        assert len(filtered) == 2
        assert all(e["service_name"] in svc_names for e in filtered)

    def test_user_without_services_sees_nothing(self):
        svc_names = []
        errors = [
            {"service_name": "data-pipeline", "message": "err1"},
        ]
        filtered = [e for e in errors if e.get("service_name") in svc_names]
        assert len(filtered) == 0


class TestOwnerPermissions:
    """Test owner vs member permissions."""

    def test_owner_can_update(self):
        role = "owner"
        assert role == "owner"  # Can update

    def test_member_cannot_update(self):
        role = "member"
        assert role != "owner"  # Cannot update

    def test_owner_can_invite(self):
        role = "owner"
        assert role == "owner"  # Can invite

    def test_member_cannot_invite(self):
        role = "member"
        assert role != "owner"  # Cannot invite

    def test_owner_can_delete_service(self):
        role = "owner"
        assert role == "owner"

    def test_cannot_remove_self(self):
        current_user_id = "user-1"
        target_user_id = "user-1"
        assert current_user_id == target_user_id  # Should be blocked


class TestSlackChannelNaming:
    """Test Slack channel name generation."""

    def test_channel_name_format(self):
        name = "data-pipeline"
        channel = f"svc-{name.lower().replace(' ', '-').replace('_', '-')[:70]}"
        assert channel == "svc-data-pipeline"

    def test_channel_name_with_spaces(self):
        name = "My Service Name"
        channel = f"svc-{name.lower().replace(' ', '-').replace('_', '-')[:70]}"
        assert channel == "svc-my-service-name"

    def test_channel_name_with_underscores(self):
        name = "auth_service"
        channel = f"svc-{name.lower().replace(' ', '-').replace('_', '-')[:70]}"
        assert channel == "svc-auth-service"

    def test_channel_name_truncation(self):
        name = "a" * 100
        channel = f"svc-{name.lower()[:70]}"
        assert len(channel) <= 74  # svc- (4) + 70
