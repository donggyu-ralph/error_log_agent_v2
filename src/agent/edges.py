"""Conditional edge logic for the agent graph."""
from src.agent.state import AgentState


def has_errors(state: AgentState) -> str:
    """Check if any errors were found."""
    if state.get("error_logs"):
        return "has_errors"
    return "no_errors"


def route_after_approval(state: AgentState) -> str:
    """Route based on human feedback."""
    feedback = state.get("human_feedback", {})
    action = feedback.get("action", "reject") if feedback else "reject"

    if action == "approve":
        return "approve"
    elif action == "feedback":
        return "feedback"
    else:
        return "reject"


def check_staging(state: AgentState) -> str:
    """Check staging verification result."""
    result = state.get("staging_result", "unhealthy")
    if result == "healthy":
        return "healthy"
    return "unhealthy"


def check_monitor(state: AgentState) -> str:
    """Check post-deployment monitoring result."""
    status = state.get("post_fix_status", "resolved")
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)

    if status == "recurring" and iteration < max_iter:
        return "recurring"
    return "resolved"
