"""Code fix application node."""
import traceback as tb_module
from pathlib import Path
from typing import Optional

import git
from langchain_openai import ChatOpenAI

from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)


def _create_branch(project_root: str, branch_name: str) -> str:
    """Create a new git branch for the fix."""
    repo = git.Repo(project_root)
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()
    logger.info("git_branch_created", branch=branch_name)
    return branch_name


def _commit_changes(message: str, project_root: str, modified_files: list[str]) -> Optional[str]:
    """Commit only the actually modified files."""
    try:
        repo = git.Repo(project_root)
        project_path = Path(project_root).resolve()

        files_to_stage = []
        for f in modified_files:
            p = Path(f)
            if p.is_absolute():
                try:
                    files_to_stage.append(str(p.relative_to(project_path)))
                except ValueError:
                    files_to_stage.append(f)
            else:
                files_to_stage.append(f)

        if files_to_stage:
            repo.index.add(files_to_stage)
            commit = repo.index.commit(message)
            logger.info("git_commit_created", hash=commit.hexsha, files=files_to_stage)
            return commit.hexsha

        logger.warning("no_files_to_commit")
        return None
    except Exception as e:
        logger.error("git_commit_failed", error=str(e))
        return None


async def _apply_fix_to_file(
    file_path: str,
    content: str,
    changes_description: str,
    llm: ChatOpenAI,
    project_root: str,
) -> Optional[str]:
    """Use LLM to apply fix to a single file."""
    prompt = f"""다음 Python 파일의 코드를 수정하세요.

## 현재 코드
```python
{content}
```

## 수정 내용
{changes_description}

## 지시사항
- 수정된 전체 파일 내용만 출력하세요
- 코드 블록(```)으로 감싸지 마세요
- 기존 코드 스타일을 유지하세요
- 필요한 import만 추가하세요
"""
    response = await llm.ainvoke(prompt)
    fixed = response.content.strip()

    # Remove code block markers if present
    if fixed.startswith("```"):
        lines = fixed.split("\n")
        lines = lines[1:]  # Remove opening ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        fixed = "\n".join(lines)

    return fixed


async def apply_fix_node(state: AgentState) -> dict:
    """Apply the fix plan: create branch, modify files, commit."""
    settings = get_settings()
    project = settings.target_projects[0]
    fix_plan = state.get("fix_plan", {})
    source_context = state.get("source_code_context", {})
    error_logs = state.get("error_logs", [])

    project_root = project.root_path

    # Create branch
    error_type = error_logs[0].get("error_type", "unknown") if error_logs else "unknown"
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch_name = f"fix/agent-{error_type.lower().replace('.', '-')}-{timestamp}"

    try:
        _create_branch(project_root, branch_name)
    except Exception as e:
        logger.error("branch_creation_failed", error=str(e))
        return {
            "git_branch": None,
            "git_commit_hash": None,
            "actually_modified_files": [],
        }

    llm = ChatOpenAI(model=settings.llm.model, temperature=0.0, max_tokens=settings.llm.max_tokens)

    actually_modified_files = []
    for target in fix_plan.get("target_files", []):
        fp = target["file_path"]

        # Skip protected paths
        if any(fp.startswith(exc) for exc in project.exclude_paths):
            logger.warning("skipping_protected_file", file=fp)
            continue

        content = source_context.get(fp, "")
        if not content:
            full_path = Path(project_root) / fp
            if full_path.exists():
                content = full_path.read_text(encoding="utf-8")

        if not content:
            logger.warning("file_not_found_for_fix", file=fp)
            continue

        fixed_content = await _apply_fix_to_file(
            fp, content, target["changes_description"], llm, project_root,
        )

        if fixed_content and fixed_content != content:
            full_path = Path(project_root) / fp
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(fixed_content, encoding="utf-8")
            actually_modified_files.append(fp)
            logger.info("file_fixed", file=fp)

    # Commit
    commit_hash = None
    if actually_modified_files:
        commit_msg = f"fix: {fix_plan.get('summary', 'Auto-fix by error-log-agent')}"
        commit_hash = _commit_changes(commit_msg, project_root, actually_modified_files)

    return {
        "git_branch": branch_name,
        "git_commit_hash": commit_hash,
        "actually_modified_files": actually_modified_files,
    }
