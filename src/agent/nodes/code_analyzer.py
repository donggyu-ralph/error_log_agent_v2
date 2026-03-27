"""Code analysis node using ReAct agent with tools."""
from pathlib import Path

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger
from src.tools.file_system import read_source_code, search_related_files, list_project_files, get_git_history
from src.tools.k8s_ops import read_k8s_logs, get_pod_status

logger = get_logger(__name__)

# Tools available to the analysis agent
ANALYSIS_TOOLS = [
    read_source_code,
    search_related_files,
    list_project_files,
    get_git_history,
    read_k8s_logs,
    get_pod_status,
]


def _build_analysis_prompt(error_logs: list[dict]) -> str:
    """Build the analysis system prompt with error context."""
    error_summaries = []
    for err in error_logs:
        summary = f"- [{err.get('level')}] {err.get('error_type', 'Unknown')}: {err.get('message', '')}"
        if err.get("file_path"):
            summary += f"\n  Location: {err['file_path']}:{err.get('line_number', '?')}"
        if err.get("traceback"):
            summary += f"\n  Traceback:\n{err['traceback'][:1500]}"
        error_summaries.append(summary)

    return f"""당신은 Python 코드 분석 전문가입니다. 아래 에러 로그를 분석하세요.

제공된 도구를 사용하여:
1. 에러와 관련된 소스 코드를 직접 읽으세요 (read_source_code)
2. 관련 파일을 검색하세요 (search_related_files)
3. 필요하면 프로젝트 구조를 확인하세요 (list_project_files)
4. 최근 변경 이력을 확인하세요 (get_git_history)
5. 현재 Pod 로그를 확인하세요 (read_k8s_logs)

## 에러 로그
{chr(10).join(error_summaries)}

## 분석 요청
에러의 근본 원인, 영향 범위, 수정 방향, 심각도를 파악하세요.

최종 응답은 반드시 JSON 형식으로:
{{"root_cause": "근본 원인", "affected_files": ["파일 목록"], "suggested_fix": "수정 방향", "severity": "low|medium|high|critical", "confidence": 0.0-1.0}}
"""


async def analyze_code_node(state: AgentState) -> dict:
    """Analyze errors using ReAct agent with tools for autonomous investigation."""
    settings = get_settings()
    project = settings.target_projects[0] if settings.target_projects else None

    if not project:
        return {"analysis": "No target project configured.", "source_code_context": {}}

    error_logs = state.get("error_logs", [])
    if not error_logs:
        return {"analysis": "No errors to analyze.", "source_code_context": {}}

    # Build ReAct agent
    llm = ChatOpenAI(
        model=settings.llm.model,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
    )

    react_agent = create_react_agent(
        model=llm,
        tools=ANALYSIS_TOOLS,
    )

    # Run the agent
    prompt = _build_analysis_prompt(error_logs)

    try:
        result = await react_agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
        )

        # Extract final response
        messages = result.get("messages", [])
        analysis = messages[-1].content if messages else "Analysis failed"

        logger.info("code_analysis_completed", error_count=len(error_logs))

        # Read source files for downstream nodes
        source_context = _read_source_files_simple(project.root_path, error_logs, project.exclude_paths)

        return {
            "analysis": analysis,
            "source_code_context": source_context,
        }

    except Exception as e:
        logger.error("react_agent_analysis_failed", error=str(e))
        # Fallback to simple LLM call
        return await _fallback_analysis(state, settings)


def _read_source_files_simple(project_root: str, error_logs: list[dict], exclude_paths: list[str]) -> dict[str, str]:
    """Read relevant source files for downstream nodes."""
    root = Path(project_root)
    context = {}

    target_files = set()
    for err in error_logs:
        fp = err.get("file_path")
        if fp:
            target_files.add(fp)

    if not target_files:
        for py_file in root.rglob("*.py"):
            rel = str(py_file.relative_to(root))
            if not any(rel.startswith(exc) for exc in exclude_paths):
                target_files.add(rel)

    for fp in target_files:
        full_path = root / fp if not Path(fp).is_absolute() else Path(fp)
        if not full_path.exists():
            full_path = root / fp.lstrip("/")
        if full_path.exists() and full_path.stat().st_size < 100_000:
            try:
                context[str(fp)] = full_path.read_text(encoding="utf-8")
            except Exception:
                pass

    return context


async def _fallback_analysis(state: AgentState, settings) -> dict:
    """Fallback: simple LLM analysis without tools."""
    error_logs = state.get("error_logs", [])
    prompt = _build_analysis_prompt(error_logs)

    llm = ChatOpenAI(model=settings.llm.model, temperature=settings.llm.temperature)
    response = await llm.ainvoke(prompt)

    logger.info("fallback_analysis_completed", error_count=len(error_logs))

    project = settings.target_projects[0]
    source_context = _read_source_files_simple(project.root_path, error_logs, project.exclude_paths)

    return {
        "analysis": response.content,
        "source_code_context": source_context,
    }
