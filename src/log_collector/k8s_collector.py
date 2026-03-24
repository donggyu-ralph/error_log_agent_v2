"""K8s Pod log collector using kubectl."""
import subprocess

from src.config.logging_config import get_logger

logger = get_logger(__name__)


class K8sLogCollector:
    """Collect logs from K8s Pods via kubectl."""

    async def collect(
        self,
        namespace: str,
        label_selector: str,
        since_seconds: int = 120,
    ) -> list[str]:
        """Collect recent logs from pods matching the selector."""
        cmd = [
            "kubectl", "logs",
            "-n", namespace,
            "-l", label_selector,
            f"--since={since_seconds}s",
            "--tail=500",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )

            if result.returncode != 0:
                logger.warning(
                    "kubectl_logs_failed",
                    namespace=namespace,
                    selector=label_selector,
                    stderr=result.stderr[:500],
                )
                return []

            lines = result.stdout.splitlines()
            logger.info(
                "k8s_logs_collected",
                namespace=namespace,
                selector=label_selector,
                line_count=len(lines),
            )
            return lines

        except subprocess.TimeoutExpired:
            logger.error("kubectl_logs_timeout", namespace=namespace)
            return []
        except FileNotFoundError:
            logger.error("kubectl_not_found")
            return []
