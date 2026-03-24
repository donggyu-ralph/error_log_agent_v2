"""Code analysis node: reads source code and analyzes errors."""
import os
from pathlib import Path

from langchain_openai import ChatOpenAI

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)


def _read_source_files(project_root: str, error_logs: list[dict], exclude_paths: list[str]) -> dict[str, str]:
    """Read relevant source files based on error locations."""
    root = Path(project_root)
    context = {}

    # Collect file paths from errors
    target_files = set()
    for err in error_logs:
        fp = err.get("file_path")
        if fp:
            target_files.add(fp)

    # If no specific files, read all Python files in src/
    if not target_files:
        for py_file in root.rglob("*.py"):
            rel = str(py_file.relative_to(root))
            if not any(rel.startswith(exc) for exc in exclude_paths):
                target_files.add(rel)

    for fp in target_files:
        full_path = root / fp if not Path(fp).is_absolute() else Path(fp)
        if not full_path.exists():
            # Try relative to project root
            full_path = root / fp.lstrip("/")
        if full_path.exists() and full_path.stat().st_size < 100_000:
            try:
                context[str(fp)] = full_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("file_read_failed", file=fp, error=str(e))

    return context


async def analyze_code_node(state: AgentState) -> dict:
    """Analyze errors with source code context using LLM."""
    settings = get_settings()
    project = settings.target_projects[0] if settings.target_projects else None

    if not project:
        return {"analysis": "No target project configured.", "source_code_context": {}}

    # Read source files
    source_context = _read_source_files(
        project.root_path,
        state.get("error_logs", []),
        project.exclude_paths,
    )

    # Build analysis prompt
    error_summaries = []
    for err in state.get("error_logs", []):
        summary = f"- [{err.get('level')}] {err.get('error_type', 'Unknown')}: {err.get('message', '')}"
        if err.get("file_path"):
            summary += f"\n  Location: {err['file_path']}:{err.get('line_number', '?')}"
        if err.get("traceback"):
            summary += f"\n  Traceback:\n{err['traceback'][:1000]}"
        error_summaries.append(summary)

    code_snippets = []
    for fp, content in list(source_context.items())[:10]:
        code_snippets.append(f"--- {fp} ---\n{content[:3000]}")

    prompt = f"""당신은 Python 코드 분석 전문가입니다. 다음 에러 로그와 소스 코드를 분석하세요.

## 에러 로그
{chr(10).join(error_summaries)}

## 관련 소스 코드
{chr(10).join(code_snippets[:5])}

## 분석 요청
1. 에러의 근본 원인을 파악하세요.
2. 영향 받는 파일과 함수를 식별하세요.
3. 수정 방향을 제안하세요.
4. 심각도를 평가하세요 (low/medium/high/critical).

JSON 형식으로 응답하세요:
{{"root_cause": "...", "affected_files": [...], "suggested_fix": "...", "severity": "...", "confidence": 0.0-1.0}}
"""

    llm = ChatOpenAI(model=settings.llm.model, temperature=settings.llm.temperature, max_tokens=settings.llm.max_tokens)
    response = await llm.ainvoke(prompt)

    logger.info("code_analysis_completed", error_count=len(state.get("error_logs", [])))

    return {
        "analysis": response.content,
        "source_code_context": source_context,
    }
