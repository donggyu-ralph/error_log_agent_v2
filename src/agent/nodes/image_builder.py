"""Docker image build + Harbor push node."""
import subprocess

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def build_image_node(state: AgentState) -> dict:
    """Build Docker image and push to Harbor."""
    settings = get_settings()
    project = settings.target_projects[0]
    commit_hash = state.get("git_commit_hash", "")

    if not commit_hash:
        logger.error("no_commit_hash_for_build")
        return {"deployment": None}

    tag = commit_hash[:8]
    harbor_url = settings.harbor.url.rstrip("/")
    image_name = f"{harbor_url}/{project.harbor.project}/{project.harbor.image_name}:{tag}"

    # Method 1: Remote build via SSH to Harbor node (192.168.50.10)
    # The agent sends the git repo + branch info, and the build happens on the Harbor server
    harbor_host = harbor_url.replace("http://", "").replace("https://", "").split(":")[0]

    build_cmd = (
        f"cd {project.root_path} && "
        f"docker build -t {project.harbor.project}/{project.harbor.image_name}:{tag} . && "
        f"docker tag {project.harbor.project}/{project.harbor.image_name}:{tag} "
        f"{harbor_host}:{settings.harbor.url.split(':')[-1]}/{project.harbor.project}/{project.harbor.image_name}:{tag} && "
        f"docker push {harbor_host}:{settings.harbor.url.split(':')[-1]}/{project.harbor.project}/{project.harbor.image_name}:{tag}"
    )

    try:
        # For now, assume build runs where agent has Docker access
        # In K8s, this would be via SSH to the Harbor node or Kaniko
        result = subprocess.run(
            ["bash", "-c", build_cmd],
            capture_output=True, text=True, timeout=300,
        )

        if result.returncode != 0:
            logger.error("image_build_failed", stderr=result.stderr[:500])
            return {"deployment": None}

        logger.info("image_built_and_pushed", image=image_name)

    except subprocess.TimeoutExpired:
        logger.error("image_build_timeout")
        return {"deployment": None}

    deployment = {
        "staging_namespace": project.k8s.staging_namespace,
        "staging_deployment": project.k8s.deployment,
        "production_namespace": project.k8s.namespace,
        "production_deployment": project.k8s.deployment,
        "image_tag": tag,
        "harbor_image": image_name,
    }

    return {"deployment": deployment}
