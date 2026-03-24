"""Docker image build + Harbor push via dynamic build Pod."""
import asyncio
import json
import subprocess
import tempfile
import time

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)

BUILD_POD_TEMPLATE = """
apiVersion: v1
kind: Pod
metadata:
  name: {pod_name}
  namespace: {namespace}
spec:
  nodeName: {node_name}
  restartPolicy: Never
  containers:
  - name: builder
    image: docker:27-cli
    command: ["sleep", "600"]
    securityContext:
      privileged: true
    volumeMounts:
    - name: docker-sock
      mountPath: /var/run/docker.sock
  volumes:
  - name: docker-sock
    hostPath:
      path: /var/run/docker.sock
"""


def _kubectl(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["kubectl"] + args, capture_output=True, text=True, timeout=timeout)


def _find_build_node() -> str:
    """Find a node that has Docker installed (prefer server-00 with Harbor)."""
    return "atdev-server-00"


async def build_image_node(state: AgentState) -> dict:
    """Build Docker image using a dynamic build Pod and push to Harbor."""
    return await asyncio.to_thread(_build_image_sync, state)


def _build_image_sync(state: AgentState) -> dict:
    """Synchronous image build (runs in thread to avoid blocking event loop)."""
    settings = get_settings()
    project = settings.target_projects[0]
    commit_hash = state.get("git_commit_hash", "")
    modified_files = state.get("actually_modified_files", [])

    if not commit_hash:
        logger.warning("no_commit_hash_for_build")
        return {"deployment": None}

    tag = commit_hash[:8]
    harbor_host = settings.harbor.url.replace("http://", "").replace("https://", "")
    image_full = f"{harbor_host}/{project.harbor.project}/{project.harbor.image_name}:{tag}"

    pod_name = f"build-{tag}"
    namespace = project.k8s.namespace
    node_name = _find_build_node()
    project_root = project.root_path

    try:
        # 1. Create tar of the modified source
        logger.info("creating_build_tar", project_root=project_root)
        tar_path = f"/tmp/build-{tag}.tar.gz"
        tar_result = subprocess.run(
            ["tar", "czf", tar_path, "--exclude=__pycache__", "--exclude=.git",
             "-C", str(project_root), "."],
            capture_output=True, text=True, timeout=30,
        )
        if tar_result.returncode != 0:
            logger.error("tar_creation_failed", stderr=tar_result.stderr[:300])
            return {"deployment": None}

        # 2. Create build Pod
        logger.info("creating_build_pod", pod_name=pod_name, node=node_name)
        pod_yaml = BUILD_POD_TEMPLATE.format(
            pod_name=pod_name, namespace=namespace, node_name=node_name,
        )
        apply_result = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=pod_yaml, capture_output=True, text=True, timeout=30,
        )
        if apply_result.returncode != 0:
            logger.error("build_pod_creation_failed", stderr=apply_result.stderr[:300])
            return {"deployment": None}

        # 3. Wait for Pod to be ready
        wait_result = _kubectl([
            "wait", "--for=condition=Ready", f"pod/{pod_name}",
            "-n", namespace, "--timeout=120s",
        ], timeout=130)
        if wait_result.returncode != 0:
            logger.error("build_pod_not_ready", stderr=wait_result.stderr[:300])
            _kubectl(["delete", "pod", pod_name, "-n", namespace])
            return {"deployment": None}

        # 4. Copy tar to build Pod
        cp_result = _kubectl([
            "cp", tar_path, f"{namespace}/{pod_name}:/tmp/source.tar.gz",
        ], timeout=60)
        if cp_result.returncode != 0:
            logger.error("tar_copy_failed", stderr=cp_result.stderr[:300])
            _kubectl(["delete", "pod", pod_name, "-n", namespace])
            return {"deployment": None}

        # 5. Build and push inside the Pod
        harbor_user = settings.harbor.user
        harbor_password = settings.harbor.password
        build_script = (
            f"mkdir -p /tmp/build && cd /tmp/build && tar xzf /tmp/source.tar.gz && "
            f"echo '{harbor_password}' | docker login {harbor_host} -u {harbor_user} --password-stdin 2>/dev/null && "
            f"docker build -t {image_full} . && "
            f"docker push {image_full} && "
            f"echo BUILD_SUCCESS"
        )

        logger.info("building_image", image=image_full)
        exec_result = _kubectl([
            "exec", "-n", namespace, pod_name, "--",
            "sh", "-c", build_script,
        ], timeout=300)

        if exec_result.returncode != 0 or "BUILD_SUCCESS" not in exec_result.stdout:
            logger.error("image_build_failed",
                         stdout=exec_result.stdout[-500:],
                         stderr=exec_result.stderr[-500:])
            _kubectl(["delete", "pod", pod_name, "-n", namespace])
            return {"deployment": None}

        logger.info("image_built_and_pushed", image=image_full)

        # 6. Cleanup build Pod
        _kubectl(["delete", "pod", pod_name, "-n", namespace])

        # Cleanup local tar
        subprocess.run(["rm", "-f", tar_path], capture_output=True)

        deployment = {
            "staging_namespace": project.k8s.staging_namespace,
            "staging_deployment": project.k8s.deployment,
            "production_namespace": project.k8s.namespace,
            "production_deployment": project.k8s.deployment,
            "image_tag": tag,
            "harbor_image": image_full,
        }

        return {"deployment": deployment}

    except subprocess.TimeoutExpired:
        logger.error("image_build_timeout")
        _kubectl(["delete", "pod", pod_name, "-n", namespace, "--ignore-not-found"])
        return {"deployment": None}
    except Exception as e:
        logger.error("image_build_error", error=str(e))
        _kubectl(["delete", "pod", pod_name, "-n", namespace, "--ignore-not-found"])
        return {"deployment": None}
