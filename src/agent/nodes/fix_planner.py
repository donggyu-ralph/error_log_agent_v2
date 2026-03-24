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

중요: 반드시 순수 JSON만 출력하세요. 마크다운 코드블록(```)으로 감싸지 마세요.
파일 경로는 "src/"로 시작하는 상대 경로를 사용하세요. "/app/" 같은 절대 경로를 사용하지 마세요.

{{
    "summary": "수정 요약 (1-2문장)",
    "root_cause": "근본 원인",
    "fix_description": "수정 내용 상세 설명",
    "target_files": [
        {{
            "file_path": "src/경로/파일.py",
            "changes_description": "변경 내용 설명",
            "diff_preview": "예상 diff"
        }}
    ],
    "estimated_risk": "low|medium|high",
    "requires_restart": false
}}

제약 사항:
- 최대 5개 파일만 수정
- 인프라 파일 (k8s/, Dockerfile) 수정 불가
- file_path는 반드시 "src/"로 시작하는 상대 경로
"""

    llm = ChatOpenAI(
        model=settings.llm.model,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    response = await llm.ainvoke(prompt)

    # Parse response
    import json
    import re

    raw = response.content
    fix_plan = None

    def _try_parse(text: str) -> dict | None:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None

    # Try direct JSON parse
    fix_plan = _try_parse(raw)

    # Try extracting from markdown code block (greedy to get the full JSON)
    if fix_plan is None:
        # Find all code blocks and try each
        for match in re.finditer(r"```(?:json)?\s*\n?([\s\S]*?)```", raw):
            parsed = _try_parse(match.group(1).strip())
            if parsed and isinstance(parsed, dict):
                # Prefer the one with target_files
                if parsed.get("target_files"):
                    fix_plan = parsed
                    break
                elif fix_plan is None:
                    fix_plan = parsed

    # Try finding the largest JSON object in the text
    if fix_plan is None or not fix_plan.get("target_files"):
        # Find JSON by matching braces
        brace_depth = 0
        start = None
        for i, ch in enumerate(raw):
            if ch == '{':
                if brace_depth == 0:
                    start = i
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0 and start is not None:
                    candidate = _try_parse(raw[start:i+1])
                    if candidate and isinstance(candidate, dict) and candidate.get("target_files"):
                        fix_plan = candidate
                        break
                    start = None

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
