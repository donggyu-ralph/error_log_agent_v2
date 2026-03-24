"""Post-deployment monitoring node."""
import asyncio
import subprocess

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def monitor_node(state: AgentState) -> dict:
    """Monitor production after deployment for recurring errors."""
    deployment = state.get("deployment")
    if not deployment:
        return {"post_fix_status": "monitor_skip"}

    settings = get_settings()
    ns = deployment["production_namespace"]
    dep_name = deployment["production_deployment"]

    # Monitor for 60 seconds
    monitor_seconds = settings.deployer.staging_verify_seconds
    error_found = False

    # Wait a bit for the new pods to start processing
    await asyncio.sleep(10)

    # Check logs for the original error type
    original_errors = state.get("error_logs", [])
    original_types = {e.get("error_type") for e in original_errors if e.get("error_type")}

    result = subprocess.run(
        ["kubectl", "logs", "-l", f"app={dep_name}", "-n", ns,
         f"--since={monitor_seconds}s", "--tail=200"],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if "ERROR" in line or "CRITICAL" in line:
                # Check if it's the same error type
                for err_type in original_types:
                    if err_type in line:
                        error_found = True
                        break

    if error_found:
        logger.warning("error_recurring_after_fix", namespace=ns)
        iteration = state.get("iteration_count", 0) + 1
        return {
            "post_fix_status": "recurring",
            "iteration_count": iteration,
        }

    logger.info("monitoring_passed", namespace=ns)
    return {"post_fix_status": "resolved"}
