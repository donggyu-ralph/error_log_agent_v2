"""HITL (Human-in-the-Loop) Middleware for LangGraph.

Provides a reusable middleware pattern for human approval workflows.
Uses LangGraph's interrupt() to pause the graph and wait for external input.

Usage in graph:
    graph.add_node("approval", hitl_approval_middleware(
        on_request=send_slack_notification,
        timeout_seconds=3600,
    ))

The middleware:
1. Calls on_request() to notify the human (e.g., Slack message)
2. Calls interrupt() to pause the graph
3. Graph state is saved to PostgreSQL checkpoint
4. When human responds, graph.ainvoke(Command(resume=feedback)) resumes
5. Middleware returns the human's feedback to the next node
"""
from typing import Callable, Optional
from langgraph.types import interrupt

from src.config.logging_config import get_logger

logger = get_logger(__name__)


def hitl_approval_middleware(
    on_request: Optional[Callable] = None,
    timeout_seconds: int = 3600,
):
    """Create a HITL approval node that can be inserted into any LangGraph graph.

    Args:
        on_request: Async callback called before interrupt.
                    Receives (state) and should notify the human (e.g., Slack).
        timeout_seconds: Max wait time for human response.

    Returns:
        An async node function for LangGraph.
    """

    async def _hitl_node(state: dict) -> dict:
        thread_id = state.get("thread_id", "unknown")

        logger.info("hitl_requesting_approval", thread_id=thread_id)

        # Notify human (e.g., send Slack message)
        if on_request:
            try:
                await on_request(state)
            except Exception as e:
                logger.error("hitl_notification_failed", error=str(e))

        # Interrupt the graph — state is checkpointed
        # When resumed via Command(resume=feedback), feedback is returned here
        feedback = interrupt({
            "type": "approval_request",
            "thread_id": thread_id,
            "timeout_seconds": timeout_seconds,
        })

        logger.info(
            "hitl_feedback_received",
            thread_id=thread_id,
            action=feedback.get("action", "unknown") if isinstance(feedback, dict) else str(feedback),
        )

        return {"human_feedback": feedback}

    return _hitl_node
