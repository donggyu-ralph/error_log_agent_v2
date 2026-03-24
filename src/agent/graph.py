"""LangGraph agent graph definition with PostgreSQL checkpointer."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.agent.state import AgentState
from src.agent.nodes.log_collector import collect_logs_node
from src.agent.nodes.code_analyzer import analyze_code_node
from src.agent.nodes.fix_planner import plan_fix_node
from src.agent.nodes.code_fixer import apply_fix_node
from src.agent.nodes.image_builder import build_image_node
from src.agent.nodes.k8s_deployer import (
    deploy_staging_node,
    verify_staging_node,
    deploy_production_node,
)
from src.agent.nodes.monitor import monitor_node
from src.agent.middleware import hitl_approval_middleware
from src.agent.edges import (
    has_errors,
    route_after_approval,
    check_staging,
    check_monitor,
)
from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Singleton checkpointer and graph
_checkpointer = None
_compiled_graph = None


def _create_checkpointer():
    """Create PostgreSQL checkpointer, fallback to MemorySaver."""
    global _checkpointer

    if _checkpointer is not None:
        return _checkpointer

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from src.config.settings import get_settings
        settings = get_settings()
        dsn = settings.database.dsn

        _checkpointer = PostgresSaver.from_conn_string(dsn)
        _checkpointer.setup()
        logger.info("checkpointer_initialized", type="postgres")
    except Exception as e:
        logger.warning("postgres_checkpointer_failed_using_memory", error=str(e))
        _checkpointer = MemorySaver()

    return _checkpointer


async def _send_slack_notification(state: dict):
    """Called by HITL middleware to send Slack approval request."""
    # This is a no-op here — actual Slack sending is done in scheduler
    # after detecting the interrupt. This keeps the middleware generic.
    pass


def _build_graph(checkpointer):
    """Build the LangGraph state machine."""
    graph = StateGraph(AgentState)

    # Create HITL middleware node
    approval_node = hitl_approval_middleware(
        on_request=_send_slack_notification,
        timeout_seconds=3600,
    )

    # Add nodes
    graph.add_node("collect_logs", collect_logs_node)
    graph.add_node("analyze_code", analyze_code_node)
    graph.add_node("plan_fix", plan_fix_node)
    graph.add_node("request_approval", approval_node)  # HITL middleware
    graph.add_node("apply_fix", apply_fix_node)
    graph.add_node("build_image", build_image_node)
    graph.add_node("deploy_staging", deploy_staging_node)
    graph.add_node("verify_staging", verify_staging_node)
    graph.add_node("deploy_production", deploy_production_node)
    graph.add_node("monitor", monitor_node)

    # Entry
    graph.set_entry_point("collect_logs")

    # collect_logs → has_errors?
    graph.add_conditional_edges(
        "collect_logs",
        has_errors,
        {"has_errors": "analyze_code", "no_errors": END},
    )

    # analyze → plan → approval (HITL interrupt)
    graph.add_edge("analyze_code", "plan_fix")
    graph.add_edge("plan_fix", "request_approval")

    # approval → route
    graph.add_conditional_edges(
        "request_approval",
        route_after_approval,
        {
            "approve": "apply_fix",
            "reject": END,
            "feedback": "analyze_code",
        },
    )

    # apply_fix → build → staging → verify
    graph.add_edge("apply_fix", "build_image")
    graph.add_edge("build_image", "deploy_staging")
    graph.add_edge("deploy_staging", "verify_staging")

    # verify → healthy/unhealthy
    graph.add_conditional_edges(
        "verify_staging",
        check_staging,
        {"healthy": "deploy_production", "unhealthy": END},
    )

    # production → monitor
    graph.add_edge("deploy_production", "monitor")

    # monitor → recurring/resolved
    graph.add_conditional_edges(
        "monitor",
        check_monitor,
        {"recurring": "analyze_code", "resolved": END},
    )

    return graph.compile(checkpointer=checkpointer)


def get_agent():
    """Get the compiled agent graph with persistent checkpointer."""
    global _compiled_graph

    if _compiled_graph is None:
        checkpointer = _create_checkpointer()
        _compiled_graph = _build_graph(checkpointer)
        logger.info("agent_graph_compiled")

    return _compiled_graph
