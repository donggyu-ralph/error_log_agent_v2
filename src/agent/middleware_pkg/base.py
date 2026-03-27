"""Middleware base: decorator pattern for LangGraph nodes."""
import functools
import time
from typing import Callable, Any

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Registry of middleware functions
_middleware_chain: list[Callable] = []


def node_middleware(middleware_fn: Callable) -> Callable:
    """Register a middleware function."""
    _middleware_chain.append(middleware_fn)
    return middleware_fn


def with_middleware(*middlewares):
    """Decorator to wrap a LangGraph node with middleware chain.

    Usage:
        @with_middleware(logging_middleware, error_handling_middleware, metrics_middleware)
        async def my_node(state):
            ...
    """
    def decorator(node_fn):
        @functools.wraps(node_fn)
        async def wrapper(state: dict) -> dict:
            context = {
                "node_name": node_fn.__name__,
                "start_time": time.monotonic(),
                "state": state,
            }

            # Execute middleware chain: before → node → after
            for mw in middlewares:
                before_fn = getattr(mw, 'before', None) or (mw if callable(mw) else None)
                if before_fn and hasattr(mw, 'before'):
                    await mw.before(context)

            try:
                result = await node_fn(state)
                context["result"] = result
                context["success"] = True

                for mw in reversed(middlewares):
                    if hasattr(mw, 'after'):
                        await mw.after(context)

                return result

            except Exception as e:
                context["error"] = e
                context["success"] = False

                for mw in reversed(middlewares):
                    if hasattr(mw, 'on_error'):
                        recovery = await mw.on_error(context)
                        if recovery is not None:
                            return recovery

                raise

        return wrapper
    return decorator
