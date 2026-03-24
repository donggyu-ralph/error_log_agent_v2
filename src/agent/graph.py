"""LangGraph agent graph definition."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.agent.state import AgentState
from src.agent.nodes.log_collector import collect_logs_node
from src.agent.nodes.code_analyzer import analyze_code_node
from src.agent.nodes.fix_planner import plan_fix_node
from src.agent.nodes.human_approval import request_approval_node
from src.agent.nodes.code_fixer import apply_fix_node
from src.agent.nodes.image_builder import build_image_node
from src.agent.nodes.k8s_deployer import (
    deploy_staging_node,
    verify_staging_node,
    deploy_production_node,
)
from src.agent.nodes.monitor import monitor_node
from src.agent.edges import (
    has_errors,
    route_after_approval,
    check_staging,
    check_monitor,
)


def build_agent_graph(checkpointer=None):
    """Build and compile the LangGraph agent."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("collect_logs", collect_logs_node)
    graph.add_node("analyze_code", analyze_code_node)
    graph.add_node("plan_fix", plan_fix_node)
    graph.add_node("request_approval", request_approval_node)
    graph.add_node("apply_fix", apply_fix_node)
    graph.add_node("build_image", build_image_node)
    graph.add_node("deploy_staging", deploy_staging_node)
    graph.add_node("verify_staging", verify_staging_node)
    graph.add_node("deploy_production", deploy_production_node)
    graph.add_node("monitor", monitor_node)

    # Set entry point
    graph.set_entry_point("collect_logs")

    # Edges: collect_logs → has_errors?
    graph.add_conditional_edges(
        "collect_logs",
        has_errors,
        {
            "has_errors": "analyze_code",
            "no_errors": END,
        },
    )

    # analyze → plan → approval
    graph.add_edge("analyze_code", "plan_fix")
    graph.add_edge("plan_fix", "request_approval")

    # approval → route (approve/reject/feedback)
    graph.add_conditional_edges(
        "request_approval",
        route_after_approval,
        {
            "approve": "apply_fix",
            "reject": END,
            "feedback": "analyze_code",  # Re-analyze with feedback
        },
    )

    # apply_fix → build_image → deploy_staging → verify_staging
    graph.add_edge("apply_fix", "build_image")
    graph.add_edge("build_image", "deploy_staging")
    graph.add_edge("deploy_staging", "verify_staging")

    # verify_staging → healthy/unhealthy
    graph.add_conditional_edges(
        "verify_staging",
        check_staging,
        {
            "healthy": "deploy_production",
            "unhealthy": END,  # Rollback already handled in verify
        },
    )

    # deploy_production → monitor
    graph.add_edge("deploy_production", "monitor")

    # monitor → recurring/resolved
    graph.add_conditional_edges(
        "monitor",
        check_monitor,
        {
            "recurring": "analyze_code",
            "resolved": END,
        },
    )

    # Compile with checkpointer for HITL support
    if checkpointer is None:
        checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)


# Default graph instance
def get_agent():
    """Get the compiled agent graph."""
    return build_agent_graph()
