"""K8s operations tools for ReAct agent."""
import subprocess

from langchain_core.tools import tool


@tool
def read_k8s_logs(namespace: str = "pipeline", label: str = "app=data-pipeline",
                  since: str = "5m", tail: int = 50) -> str:
    """Read recent K8s Pod logs. Useful for checking current error state."""
    try:
        result = subprocess.run(
            ["kubectl", "logs", "-n", namespace, "-l", label,
             f"--since={since}", f"--tail={tail}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return f"kubectl error: {result.stderr[:200]}"
        return result.stdout[-3000:] if result.stdout else "No logs found"
    except Exception as e:
        return f"Error: {e}"


@tool
def get_pod_status(namespace: str = "pipeline") -> str:
    """Get current Pod status in a namespace."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "wide"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr[:200]}"
    except Exception as e:
        return f"Error: {e}"
