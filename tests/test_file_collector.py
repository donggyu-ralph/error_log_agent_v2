"""Unit tests for RemoteFileCollector (mock-based)."""
import subprocess
from unittest.mock import patch, MagicMock
import pytest
import asyncio

from src.log_collector.file_collector import RemoteFileCollector


@pytest.fixture
def collector():
    return RemoteFileCollector(max_retries=3, retry_base_delay=0.01)


# --- SSH Connection Tests ---

class TestSSHConnection:
    @pytest.mark.asyncio
    async def test_check_connection_success(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok\n"

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            result = await collector.check_connection("192.168.50.26", "sam")
            assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            result = await collector.check_connection("192.168.50.26", "sam")
            assert result is False

    @pytest.mark.asyncio
    async def test_check_connection_timeout(self, collector):
        with patch.object(collector, '_run_ssh', side_effect=subprocess.TimeoutExpired("ssh", 10)):
            result = await collector.check_connection("192.168.50.26", "sam")
            assert result is False

    @pytest.mark.asyncio
    async def test_check_connection_ssh_not_found(self, collector):
        with patch.object(collector, '_run_ssh', side_effect=FileNotFoundError):
            result = await collector.check_connection("192.168.50.26", "sam")
            assert result is False


# --- File Existence Tests ---

class TestFileExists:
    @pytest.mark.asyncio
    async def test_file_exists_and_readable(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\nEXISTS\n"

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            info = await collector.check_file_exists("host", "user", "/var/log/test.log")
            assert info["exists"] is True
            assert info["readable"] is True
            assert info["size"] == 12345

    @pytest.mark.asyncio
    async def test_file_missing(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "MISSING\n"

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            info = await collector.check_file_exists("host", "user", "/nonexistent.log")
            assert info["exists"] is False

    @pytest.mark.asyncio
    async def test_file_check_ssh_error(self, collector):
        with patch.object(collector, '_run_ssh', side_effect=Exception("SSH failed")):
            info = await collector.check_file_exists("host", "user", "/var/log/test.log")
            assert info["exists"] is False
            assert "SSH failed" in info.get("error", "")


# --- Log Collection Tests ---

class TestCollect:
    @pytest.mark.asyncio
    async def test_collect_success(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "100\n2026-03-24 10:00:00 - svc - ERROR - test error\n"

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert len(lines) == 1
            assert "ERROR" in lines[0]
            assert collector.get_offset("host", "/var/log/app.log") == 100

    @pytest.mark.asyncio
    async def test_collect_empty_file(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert lines == []

    @pytest.mark.asyncio
    async def test_collect_multiple_lines(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "500\nline1\nline2\nline3\n"

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert len(lines) == 3
            assert collector.get_offset("host", "/var/log/app.log") == 500

    @pytest.mark.asyncio
    async def test_collect_offset_tracking(self, collector):
        # First collection
        mock1 = MagicMock()
        mock1.returncode = 0
        mock1.stdout = "100\nfirst line\n"

        with patch.object(collector, '_run_ssh', return_value=mock1):
            await collector.collect("host", "user", "/var/log/app.log")
            assert collector.get_offset("host", "/var/log/app.log") == 100

        # Second collection — offset should be used
        mock2 = MagicMock()
        mock2.returncode = 0
        mock2.stdout = "200\nsecond line\n"

        with patch.object(collector, '_run_ssh', return_value=mock2) as mock_ssh:
            await collector.collect("host", "user", "/var/log/app.log")
            # Verify the command uses the offset
            call_args = mock_ssh.call_args
            assert "+101" in call_args[0][2]  # tail -c +101
            assert collector.get_offset("host", "/var/log/app.log") == 200

    @pytest.mark.asyncio
    async def test_collect_invalid_file_size(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not_a_number\nsome log line\n"

        with patch.object(collector, '_run_ssh', return_value=mock_result):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert len(lines) == 2  # Falls back to all lines


# --- Error Handling & Retry Tests ---

class TestRetry:
    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self, collector):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied (publickey)"

        with patch.object(collector, '_run_ssh', return_value=mock_result) as mock_ssh:
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert lines == []
            assert mock_ssh.call_count == 1  # No retry for permanent error

    @pytest.mark.asyncio
    async def test_transient_error_retries(self, collector):
        fail = MagicMock()
        fail.returncode = 1
        fail.stderr = "Connection refused"

        success = MagicMock()
        success.returncode = 0
        success.stdout = "50\nrecovered line\n"

        with patch.object(collector, '_run_ssh', side_effect=[fail, success]):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert len(lines) == 1
            assert "recovered" in lines[0]

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self, collector):
        fail = MagicMock()
        fail.returncode = 1
        fail.stderr = "Connection timed out"

        with patch.object(collector, '_run_ssh', return_value=fail) as mock_ssh:
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert lines == []
            assert mock_ssh.call_count == 3  # All retries used

    @pytest.mark.asyncio
    async def test_timeout_retries(self, collector):
        with patch.object(collector, '_run_ssh',
                          side_effect=[subprocess.TimeoutExpired("ssh", 30),
                                       subprocess.TimeoutExpired("ssh", 30),
                                       subprocess.TimeoutExpired("ssh", 30)]):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert lines == []

    @pytest.mark.asyncio
    async def test_timeout_then_success(self, collector):
        success = MagicMock()
        success.returncode = 0
        success.stdout = "100\nrecovered\n"

        with patch.object(collector, '_run_ssh',
                          side_effect=[subprocess.TimeoutExpired("ssh", 30), success]):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert len(lines) == 1

    @pytest.mark.asyncio
    async def test_ssh_binary_not_found(self, collector):
        with patch.object(collector, '_run_ssh', side_effect=FileNotFoundError):
            lines = await collector.collect("host", "user", "/var/log/app.log")
            assert lines == []


# --- Offset Management Tests ---

class TestOffsetManagement:
    def test_reset_offset(self, collector):
        collector._offsets["host:/path"] = 500
        collector.reset_offset("host", "/path")
        assert collector.get_offset("host", "/path") == 0

    def test_get_offset_default(self, collector):
        assert collector.get_offset("unknown", "/path") == 0


# --- Error Classification Tests ---

class TestErrorClassification:
    def test_classify_permanent(self, collector):
        assert collector._classify_error("Permission denied") == "permanent"
        assert collector._classify_error("No such file or directory") == "permanent"

    def test_classify_transient(self, collector):
        assert collector._classify_error("Connection refused") == "transient"
        assert collector._classify_error("Connection timed out") == "transient"
        assert collector._classify_error("Network is unreachable") == "transient"
        assert collector._classify_error("No route to host") == "transient"
        assert collector._classify_error("Connection reset by peer") == "transient"

    def test_classify_unknown(self, collector):
        assert collector._classify_error("some random error") == "unknown"
        assert collector._classify_error("") == "unknown"
