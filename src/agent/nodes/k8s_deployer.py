"""K8s staging and production deployment nodes."""
import asyncio
import subprocess

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)


def _kubectl(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a kubectl command."""
    cmd = ["kubectl"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


async def deploy_staging_node(state: AgentState) -> dict:
    """Deploy to staging namespace."""
    return await asyncio.to_thread(_deploy_staging_sync, state)


def _deploy_staging_sync(state: AgentState) -> dict:
    deployment = state.get("deployment")
    if not deployment:
        return {"staging_result": "unhealthy"}

    ns = deployment["staging_namespace"]
    dep_name = deployment["staging_deployment"]
    image = deployment["harbor_image"]

    # Ensure staging namespace exists
    _kubectl(["create", "namespace", ns, "--dry-run=client", "-o", "yaml"])
    result = _kubectl(["get", "namespace", ns])
    if result.returncode != 0:
        _kubectl(["create", "namespace", ns])
        logger.info("staging_namespace_created", namespace=ns)

    # Copy deployment from production to staging
    prod_ns = deployment["production_namespace"]
    get_result = _kubectl([
        "get", "deployment", dep_name,
        "-n", prod_ns,
        "-o", "json",
    ])

    if get_result.returncode != 0:
        logger.error("prod_deployment_not_found", deployment=dep_name, namespace=prod_ns)
        return {"staging_result": "unhealthy"}

    import json
    deploy_spec = json.loads(get_result.stdout)

    # Modify for staging
    deploy_spec["metadata"]["namespace"] = ns
    deploy_spec["metadata"].pop("resourceVersion", None)
    deploy_spec["metadata"].pop("uid", None)
    deploy_spec["metadata"].pop("creationTimestamp", None)

    # Update image
    for container in deploy_spec["spec"]["template"]["spec"]["containers"]:
        container["image"] = image

    # Apply to staging
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(deploy_spec, f)
        f.flush()
        apply_result = _kubectl(["apply", "-f", f.name])

    if apply_result.returncode != 0:
        logger.error("staging_deploy_failed", stderr=apply_result.stderr[:500])
        return {"staging_result": "unhealthy"}

    # Wait for rollout
    settings = get_settings()
    timeout = settings.deployer.staging_timeout_seconds
    rollout = _kubectl([
        "rollout", "status", f"deployment/{dep_name}",
        "-n", ns,
        f"--timeout={timeout}s",
    ], timeout=timeout + 10)

    if rollout.returncode != 0:
        logger.error("staging_rollout_failed", stderr=rollout.stderr[:500])
        return {"staging_result": "timeout"}

    logger.info("staging_deployed", namespace=ns, image=image)
    return {}


async def verify_staging_node(state: AgentState) -> dict:
    """Verify staging deployment is healthy."""
    return await asyncio.to_thread(_verify_staging_sync, state)


def _verify_staging_sync(state: AgentState) -> dict:
    deployment = state.get("deployment")
    if not deployment:
        return {"staging_result": "unhealthy"}

    settings = get_settings()
    ns = deployment["staging_namespace"]
    dep_name = deployment["staging_deployment"]
    verify_seconds = settings.deployer.staging_verify_seconds

    import asyncio
    import time

    # Check health endpoint
    # Get the staging service ClusterIP
    svc_result = _kubectl(["get", "svc", dep_name, "-n", ns, "-o", "jsonpath={.spec.clusterIP}"])
    if svc_result.returncode != 0:
        logger.warning("staging_svc_not_found", namespace=ns)

    # Monitor for errors during verify period
    start = time.monotonic()
    error_count = 0

    while time.monotonic() - start < verify_seconds:
        # Check pod logs for errors
        log_result = _kubectl([
            "logs", "-l", f"app={dep_name}",
            "-n", ns,
            "--since=10s",
            "--tail=50",
        ])
        if log_result.returncode == 0:
            for line in log_result.stdout.splitlines():
                if "ERROR" in line or "CRITICAL" in line:
                    error_count += 1

        # Check pod status
        pod_result = _kubectl(["get", "pods", "-l", f"app={dep_name}", "-n", ns, "-o", "json"])
        if pod_result.returncode == 0:
            import json
            pods = json.loads(pod_result.stdout)
            for pod in pods.get("items", []):
                phase = pod.get("status", {}).get("phase")
                if phase not in ("Running", "Succeeded"):
                    logger.warning("staging_pod_unhealthy", phase=phase)
                    return {"staging_result": "unhealthy"}

        import time; time.sleep(10)

    if error_count > 0:
        logger.warning("staging_errors_detected", count=error_count)
        return {"staging_result": "unhealthy"}

    logger.info("staging_verification_passed", namespace=ns)
    return {"staging_result": "healthy"}


async def deploy_production_node(state: AgentState) -> dict:
    """Deploy to production namespace."""
    return await asyncio.to_thread(_deploy_production_sync, state)


def _deploy_production_sync(state: AgentState) -> dict:
    deployment = state.get("deployment")
    if not deployment:
        return {"post_fix_status": "deploy_failed"}

    ns = deployment["production_namespace"]
    dep_name = deployment["production_deployment"]
    image = deployment["harbor_image"]

    # Backup current image for rollback
    current = _kubectl([
        "get", "deployment", dep_name,
        "-n", ns,
        "-o", "jsonpath={.spec.template.spec.containers[0].image}",
    ])
    previous_image = current.stdout.strip() if current.returncode == 0 else None

    # Update production image
    result = _kubectl([
        "set", "image",
        f"deployment/{dep_name}",
        f"{dep_name}={image}",
        "-n", ns,
    ])

    if result.returncode != 0:
        logger.error("production_deploy_failed", stderr=result.stderr[:500])
        return {"post_fix_status": "deploy_failed"}

    # Wait for rollout
    settings = get_settings()
    timeout = settings.deployer.production_rollout_timeout
    rollout = _kubectl([
        "rollout", "status", f"deployment/{dep_name}",
        "-n", ns,
        f"--timeout={timeout}s",
    ], timeout=timeout + 10)

    if rollout.returncode != 0:
        logger.error("production_rollout_failed")
        # Auto-rollback
        if settings.deployer.auto_rollback and previous_image:
            logger.info("auto_rollback_triggered", previous_image=previous_image)
            _kubectl(["set", "image", f"deployment/{dep_name}", f"{dep_name}={previous_image}", "-n", ns])
        return {"post_fix_status": "rollback"}

    # Update deployment info with previous image
    deployment["previous_image"] = previous_image

    logger.info("production_deployed", namespace=ns, image=image)
    return {
        "deployment": deployment,
        "post_fix_status": "deployed",
    }
