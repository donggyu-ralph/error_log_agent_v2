"""LangGraph Agent State definition."""
from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class AgentState(TypedDict):
    thread_id: str
    error_logs: list[dict]  # list of ErrorInfo dicts
    source_code_context: dict[str, str]  # file_path -> content
    analysis: str
    fix_plan: Optional[dict]  # FixPlan dict
    human_feedback: Optional[dict]  # {"action": "approve"|"reject"|"feedback", "message": "..."}
    git_branch: Optional[str]
    git_commit_hash: Optional[str]
    deployment: Optional[dict]  # DeploymentInfo dict
    staging_result: Optional[str]  # "healthy" | "unhealthy" | "timeout"
    post_fix_status: Optional[str]
    iteration_count: int
    max_iterations: int
    messages: Annotated[list, add_messages]
    actually_modified_files: list[str]
    error_history: list[dict]  # Node errors: [{node, error_type, message, timestamp}]
