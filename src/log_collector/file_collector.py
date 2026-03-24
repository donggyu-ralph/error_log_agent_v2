"""Remote file log collector via SSH."""
import subprocess

from src.config.logging_config import get_logger

logger = get_logger(__name__)


class RemoteFileCollector:
    """Collect logs from remote servers via SSH."""

    def __init__(self):
        self._offsets: dict[str, int] = {}  # host:path -> last offset

    async def collect(
        self,
        host: str,
        user: str,
        log_path: str,
    ) -> list[str]:
        """Read new lines from a remote log file since last offset."""
        key = f"{host}:{log_path}"
        offset = self._offsets.get(key, 0)

        cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            f"{user}@{host}",
            f"wc -c < {log_path} && tail -c +{offset + 1} {log_path}",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )

            if result.returncode != 0:
                logger.warning(
                    "ssh_log_collection_failed",
                    host=host,
                    log_path=log_path,
                    stderr=result.stderr[:500],
                )
                return []

            output = result.stdout
            lines = output.splitlines()

            if not lines:
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
            )
            return log_lines

        except subprocess.TimeoutExpired:
            logger.error("ssh_timeout", host=host)
            return []
        except FileNotFoundError:
            logger.error("ssh_not_found")
            return []
