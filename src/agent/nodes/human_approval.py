"""Human approval node using LangGraph interrupt."""
from langgraph.types import interrupt

from src.agent.state import AgentState
from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def request_approval_node(state: AgentState) -> dict:
    """Send fix plan to Slack and wait for human approval via interrupt."""
    fix_plan = state.get("fix_plan", {})
    error_logs = state.get("error_logs", [])
    thread_id = state.get("thread_id", "")

    logger.info(
        "requesting_human_approval",
        thread_id=thread_id,
        fix_summary=fix_plan.get("summary", "")[:100],
    )

    # Interrupt the graph and wait for human input
    # The Slack bot will resume the graph with the user's decision
    feedback = interrupt({
        "type": "approval_request",
        "thread_id": thread_id,
        "fix_plan": fix_plan,
        "error_logs": error_logs,
        "message": "Slack을 통해 사용자 승인을 기다리는 중입니다.",
    })

    # feedback is injected when the graph is resumed
    logger.info(
        "human_feedback_received",
        thread_id=thread_id,
        action=feedback.get("action", "unknown"),
    )

    return {"human_feedback": feedback}
