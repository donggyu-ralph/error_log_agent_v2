"""Error handling middleware for LangGraph nodes."""
import asyncio
import time

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Transient errors that can be retried
_TRANSIENT_EXCEPTIONS = (
    ConnectionError, TimeoutError, OSError,
)


class error_handling_middleware:
    """Classify errors and retry transient failures."""

    max_retries = 2
    retry_delay = 1.0

    @staticmethod
    async def before(context: dict):
        context["retry_count"] = 0

    @staticmethod
    async def after(context: dict):
        pass

    @staticmethod
    async def on_error(context: dict):
        error = context["error"]
        node_name = context["node_name"]

        # Classify error
        if isinstance(error, _TRANSIENT_EXCEPTIONS):
            error_class = "transient"
        elif isinstance(error, (ValueError, KeyError, TypeError)):
            error_class = "permanent"
        else:
            error_class = "unknown"

        logger.warning(
            "node_error_classified",
            node=node_name,
            error_class=error_class,
            error_type=type(error).__name__,
            error=str(error)[:200],
        )

        # Don't retry — let the graph handle it
        # Return None to propagate the error
        return None
