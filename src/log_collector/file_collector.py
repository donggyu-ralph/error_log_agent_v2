"""Remote file log collector via SSH."""
import asyncio
import subprocess
import time

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Error classification
_TRANSIENT_ERRORS = ["Connection refused", "Connection timed out", "Connection reset",
                     "No route to host", "Network is unreachable"]
_PERMANENT_ERRORS = ["Permission denied", "No such file or directory"]


class SSHConnectionError(Exception):
    """SSH connection failed."""
    pass


class RemoteFileNotFoundError(Exception):
    """Remote file does not exist or is inaccessible."""
    pass


class RemoteFileCollector:
    """Collect logs from remote servers via SSH."""

    def __init__(self, max_retries: int = 3, retry_base_delay: float = 2.0):
        self._offsets: dict[str, int] = {}
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    def _run_ssh(self, user: str, host: str, remote_cmd: str,
                 timeout: int = 30) -> subprocess.CompletedProcess:
        """Execute a command on remote host via SSH."""
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            f"{user}@{host}",
            remote_cmd,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _classify_error(self, stderr: str) -> str:
        """Classify SSH error as transient, permanent, or unknown."""
        for pattern in _PERMANENT_ERRORS:
            if pattern in stderr:
                return "permanent"
        for pattern in _TRANSIENT_ERRORS:
            if pattern in stderr:
                return "transient"
        return "unknown"

    async def check_connection(self, host: str, user: str) -> bool:
        """Test SSH connectivity to a remote host."""
        try:
            result = await asyncio.to_thread(
                self._run_ssh, user, host, "echo ok", timeout=30
            )
            return result.returncode == 0 and "ok" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def check_file_exists(self, host: str, user: str, log_path: str) -> dict:
        """Check if remote file exists and is readable."""
        try:
            result = await asyncio.to_thread(
                self._run_ssh, user, host,
                f"test -f {log_path} && test -r {log_path} && wc -c < {log_path} && echo EXISTS || echo MISSING",
                timeout=30,
            )
            output = result.stdout.strip()
            if "EXISTS" in output:
                lines = output.splitlines()
                size = int(lines[0]) if lines[0].isdigit() else 0
                return {"exists": True, "readable": True, "size": size}
            elif "MISSING" in output:
                return {"exists": False, "readable": False, "size": 0}
            else:
                return {"exists": False, "readable": False, "size": 0, "error": result.stderr[:200]}
        except Exception as e:
            return {"exists": False, "readable": False, "size": 0, "error": str(e)}

    async def collect(
        self,
        host: str,
        user: str,
        log_path: str,
    ) -> list[str]:
        """Read new lines from a remote log file since last offset.

        Includes retry logic with exponential backoff for transient errors.
        """
        key = f"{host}:{log_path}"
        offset = self._offsets.get(key, 0)

        last_error = None

        for attempt in range(self._max_retries):
            try:
                result = await asyncio.to_thread(
                    self._run_ssh, user, host,
                    f"wc -c < {log_path} && tail -c +{offset + 1} {log_path}",
                )

                if result.returncode != 0:
                    error_class = self._classify_error(result.stderr)

                    if error_class == "permanent":
                        logger.error(
                            "ssh_permanent_error",
                            host=host, log_path=log_path,
                            stderr=result.stderr[:300],
                            attempt=attempt + 1,
                        )
                        return []

                    # Transient or unknown — retry
                    last_error = result.stderr[:300]
                    if attempt < self._max_retries - 1:
                        delay = self._retry_base_delay * (2 ** attempt)
                        logger.warning(
                            "ssh_transient_error_retrying",
                            host=host, log_path=log_path,
                            attempt=attempt + 1,
                            next_retry_in=delay,
                            stderr=result.stderr[:200],
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "ssh_collection_failed_all_retries",
                            host=host, log_path=log_path,
                            attempts=self._max_retries,
                            stderr=result.stderr[:300],
                        )
                        return []

                # Success — parse output
                output = result.stdout
                lines = output.splitlines()

                if not lines:
                    logger.info("ssh_empty_response", host=host, log_path=log_path)
                    return []

                # First line is the file size
                try:
                    file_size = int(lines[0].strip())
                    self._offsets[key] = file_size
                    log_lines = lines[1:]
                except ValueError:
                    log_lines = lines

                logger.info(
                    "remote_logs_collected",
                    host=host,
                    log_path=log_path,
                    line_count=len(log_lines),
                    offset=offset,
                    new_offset=self._offsets.get(key, 0),
                )
                return log_lines

            except subprocess.TimeoutExpired:
                last_error = "SSH command timeout"
                if attempt < self._max_retries - 1:
                    delay = self._retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "ssh_timeout_retrying",
                        host=host, attempt=attempt + 1, next_retry_in=delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("ssh_timeout_all_retries", host=host, attempts=self._max_retries)
                    return []

            except FileNotFoundError:
                logger.error("ssh_binary_not_found")
                return []

        logger.error("ssh_collection_failed", host=host, last_error=last_error)
        return []

    def reset_offset(self, host: str, log_path: str) -> None:
        """Reset the offset for a specific host:path (re-read from beginning)."""
        key = f"{host}:{log_path}"
        self._offsets.pop(key, None)

    def get_offset(self, host: str, log_path: str) -> int:
        """Get current offset for a host:path."""
        return self._offsets.get(f"{host}:{log_path}", 0)
