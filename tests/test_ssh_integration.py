"""Integration tests for SSH log collection (requires Mac Studio access).

Run with: pytest tests/test_ssh_integration.py -v -m integration
Skip in CI: these tests require network access to 192.168.50.26
"""
import pytest

from src.log_collector.file_collector import RemoteFileCollector
from src.log_collector.parser import parse_log_lines
from src.log_collector.filter import filter_errors

# Mac Studio connection info
MAC_STUDIO_HOST = "192.168.50.26"
MAC_STUDIO_USER = "sam"
MAC_STUDIO_LOG_PATH = "/Users/sam/dev/Qwen3VL-32b/logs/mlx_server.stderr.log"


@pytest.fixture
def collector():
    return RemoteFileCollector(max_retries=2, retry_base_delay=1.0)


@pytest.mark.integration
class TestSSHIntegration:
    """These tests require SSH access to Mac Studio (192.168.50.26)."""

    @pytest.mark.asyncio
    async def test_ssh_connection(self, collector):
        """Test SSH connectivity to Mac Studio."""
        connected = await collector.check_connection(MAC_STUDIO_HOST, MAC_STUDIO_USER)
        assert connected, f"Cannot SSH to {MAC_STUDIO_USER}@{MAC_STUDIO_HOST}"

    @pytest.mark.asyncio
    async def test_log_file_exists(self, collector):
        """Test that the Qwen log file exists and is readable."""
        info = await collector.check_file_exists(MAC_STUDIO_HOST, MAC_STUDIO_USER, MAC_STUDIO_LOG_PATH)
        assert info["exists"], f"Log file not found: {MAC_STUDIO_LOG_PATH}"
        assert info["readable"], f"Log file not readable: {MAC_STUDIO_LOG_PATH}"
        assert info["size"] > 0, "Log file is empty"

    @pytest.mark.asyncio
    async def test_collect_logs(self, collector):
        """Test full log collection pipeline."""
        lines = await collector.collect(MAC_STUDIO_HOST, MAC_STUDIO_USER, MAC_STUDIO_LOG_PATH)
        assert isinstance(lines, list)
        # File might be empty if no recent activity, that's OK
        print(f"Collected {len(lines)} lines")
        if lines:
            print(f"First line: {lines[0][:100]}")
            print(f"Last line: {lines[-1][:100]}")

    @pytest.mark.asyncio
    async def test_collect_and_parse(self, collector):
        """Test collection + parsing pipeline."""
        lines = await collector.collect(MAC_STUDIO_HOST, MAC_STUDIO_USER, MAC_STUDIO_LOG_PATH)
        errors = parse_log_lines(lines, source="file_log", service_name="qwen-mlx")
        filtered = filter_errors(errors)
        print(f"Lines: {len(lines)}, Errors: {len(errors)}, Filtered: {len(filtered)}")
        for err in filtered[:3]:
            print(f"  [{err.level}] {err.error_type}: {err.message[:80]}")

    @pytest.mark.asyncio
    async def test_offset_tracking(self, collector):
        """Test that offset tracking works across collections."""
        # First collection
        lines1 = await collector.collect(MAC_STUDIO_HOST, MAC_STUDIO_USER, MAC_STUDIO_LOG_PATH)
        offset1 = collector.get_offset(MAC_STUDIO_HOST, MAC_STUDIO_LOG_PATH)

        # Second collection (should return no new lines if no new writes)
        lines2 = await collector.collect(MAC_STUDIO_HOST, MAC_STUDIO_USER, MAC_STUDIO_LOG_PATH)
        offset2 = collector.get_offset(MAC_STUDIO_HOST, MAC_STUDIO_LOG_PATH)

        print(f"First: {len(lines1)} lines, offset {offset1}")
        print(f"Second: {len(lines2)} lines, offset {offset2}")
        assert offset2 >= offset1

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, collector):
        """Test graceful handling of nonexistent file."""
        lines = await collector.collect(MAC_STUDIO_HOST, MAC_STUDIO_USER, "/tmp/nonexistent_file.log")
        assert lines == []

    @pytest.mark.asyncio
    async def test_nonexistent_host(self, collector):
        """Test graceful handling of unreachable host."""
        collector._max_retries = 1
        lines = await collector.collect("192.168.50.99", "nobody", "/tmp/test.log")
        assert lines == []
