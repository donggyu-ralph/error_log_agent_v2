"""Metrics middleware for LangGraph nodes."""
import time
from collections import defaultdict

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# In-memory metrics store
_metrics: dict[str, dict] = defaultdict(lambda: {
    "total_calls": 0,
    "success_count": 0,
    "failure_count": 0,
    "total_duration_s": 0.0,
    "last_error": None,
})


def get_node_metrics() -> dict:
    """Get current node execution metrics."""
    return dict(_metrics)


def reset_metrics():
    """Reset all metrics."""
    _metrics.clear()


class metrics_middleware:
    """Collect execution metrics per node."""

    @staticmethod
    async def before(context: dict):
        node_name = context["node_name"]
        _metrics[node_name]["total_calls"] += 1

    @staticmethod
    async def after(context: dict):
        node_name = context["node_name"]
        elapsed = time.monotonic() - context["start_time"]
        _metrics[node_name]["success_count"] += 1
        _metrics[node_name]["total_duration_s"] += elapsed

    @staticmethod
    async def on_error(context: dict):
        node_name = context["node_name"]
        elapsed = time.monotonic() - context["start_time"]
        _metrics[node_name]["failure_count"] += 1
        _metrics[node_name]["total_duration_s"] += elapsed
        _metrics[node_name]["last_error"] = str(context["error"])[:200]
        return None
