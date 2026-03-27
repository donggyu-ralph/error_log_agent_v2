"""Logging middleware for LangGraph nodes."""
import time

from src.config.logging_config import get_logger

logger = get_logger(__name__)


class logging_middleware:
    """Log node execution: start, end, duration, errors."""

    @staticmethod
    async def before(context: dict):
        node_name = context["node_name"]
        logger.info(f"node_started", node=node_name)

    @staticmethod
    async def after(context: dict):
        node_name = context["node_name"]
        elapsed = time.monotonic() - context["start_time"]
        logger.info(f"node_completed", node=node_name, elapsed_s=round(elapsed, 2))

    @staticmethod
    async def on_error(context: dict):
        node_name = context["node_name"]
        error = context["error"]
        elapsed = time.monotonic() - context["start_time"]
        logger.error(f"node_failed", node=node_name, error=str(error)[:300], elapsed_s=round(elapsed, 2))
        return None  # Don't recover, let it propagate
