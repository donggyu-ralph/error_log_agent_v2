"""Fix planning node."""
from langchain_openai import ChatOpenAI

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def plan_fix_node(state: AgentState) -> dict:
    """Generate a fix plan based on analysis."""
    settings = get_settings()
    analysis = state.get("analysis", "")
    error_logs = state.get("error_logs", [])
    source_context = state.get("source_code_context", {})

    # Build relevant code context
    code_context = ""
    for fp, content in list(source_context.items())[:5]:
        code_context += f"\n--- {fp} ---\n{content[:2000]}\n"

    error_info = ""
    for err in error_logs[:3]:
        error_info += f"- {err.get('error_type', 'Unknown')}: {err.get('message', '')}\n"
        if err.get("traceback"):
            error_info += f"  Traceback: {err['traceback'][:500]}\n"

    # Include feedback if re-planning
    feedback_context = ""
    feedback = state.get("human_feedback")
    if feedback and feedback.get("action") == "feedback":
        feedback_context = f"\n## 사용자 피드백\n{feedback.get('message', '')}\n위 피드백을 반영하여 수정 계획을 재수립하세요.\n"

    prompt = f"""당신은 코드 수정 계획을 수립하는 전문가입니다.

## 에러 정보
{error_info}

## 분석 결과
{analysis}

## 소스 코드
{code_context}
{feedback_context}
## 수정 계획 생성
다음 JSON 형식으로 수정 계획을 생성하세요:
{{
    "summary": "수정 요약 (1-2문장)",
    "root_cause": "근본 원인",
    "fix_description": "수정 내용 상세 설명",
    "target_files": [
        {{
            "file_path": "수정 대상 파일 경로",
            "changes_description": "변경 내용 설명",
            "diff_preview": "예상 diff (unified format)"
        }}
    ],
    "estimated_risk": "low|medium|high",
    "requires_restart": true|false
}}

제약 사항:
- 최대 5개 파일만 수정
- 인프라 파일 (k8s/, Dockerfile) 수정 불가
- 100줄 이내 변경
"""

    llm = ChatOpenAI(model=settings.llm.model, temperature=settings.llm.temperature, max_tokens=settings.llm.max_tokens)
    response = await llm.ainvoke(prompt)

    # Parse response
    import json
    import re

    raw = response.content
    fix_plan = None

    # Try direct JSON parse
    try:
        fix_plan = json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    if fix_plan is None:
        json_match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if json_match:
            try:
                fix_plan = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

    # Try finding JSON object pattern
    if fix_plan is None:
        json_match = re.search(r'\{[^{}]*"summary"[^{}]*\}', raw, re.DOTALL)
        if json_match:
            try:
                fix_plan = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    # Fallback: use raw text
    if fix_plan is None:
        fix_plan = {
            "summary": raw[:200],
            "root_cause": "LLM 응답 파싱 실패 - 원문 참조",
            "fix_description": raw,
            "target_files": [],
            "estimated_risk": "medium",
            "requires_restart": False,
        }

    logger.info("fix_plan_created", summary=fix_plan.get("summary", "")[:100])

    return {"fix_plan": fix_plan}
