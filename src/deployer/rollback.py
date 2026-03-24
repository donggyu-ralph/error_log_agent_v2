"""Rollback utilities for K8s deployments."""
import subprocess

from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def rollback_deployment(namespace: str, deployment: str, previous_image: str = None) -> bool:
    """Rollback a deployment to previous version."""
    if previous_image:
        # Rollback to specific image
        result = subprocess.run(
            ["kubectl", "set", "image", f"deployment/{deployment}",
             f"{deployment}={previous_image}", "-n", namespace],
            capture_output=True, text=True, timeout=60,
        )
    else:
        # Use kubectl rollout undo
        result = subprocess.run(
            ["kubectl", "rollout", "undo", f"deployment/{deployment}", "-n", namespace],
            capture_output=True, text=True, timeout=60,
        )

    if result.returncode != 0:
        logger.error("rollback_failed", namespace=namespace, stderr=result.stderr[:500])
        return False

    logger.info("rollback_completed", namespace=namespace, deployment=deployment)
    return True
