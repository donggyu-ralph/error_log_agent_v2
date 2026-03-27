"""File system tools for ReAct agent."""
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)


def _get_project_root() -> str:
    settings = get_settings()
    return settings.target_projects[0].root_path if settings.target_projects else ""


@tool
def read_source_code(file_path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read source code from a file. Use relative paths like 'src/main.py'.
    Optionally specify start_line and end_line to read a specific range."""
    root = Path(_get_project_root())
    # Normalize path
    if file_path.startswith("/app/"):
        file_path = file_path[5:]
    full_path = root / file_path
    if not full_path.exists():
        full_path = root / file_path.lstrip("/")
    if not full_path.exists():
        return f"File not found: {file_path}"
    if full_path.stat().st_size > 100_000:
        return f"File too large: {file_path} ({full_path.stat().st_size} bytes)"

    try:
        lines = full_path.read_text(encoding="utf-8").splitlines()
        if end_line > 0:
            lines = lines[max(0, start_line - 1):end_line]
        elif start_line > 1:
            lines = lines[start_line - 1:]
        numbered = [f"{i + start_line}: {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered[:200])
    except Exception as e:
        return f"Error reading {file_path}: {e}"


@tool
def search_related_files(keyword: str) -> str:
    """Search for files containing a keyword in the project. Returns matching file paths and line numbers."""
    root = Path(_get_project_root())
    if not root.exists():
        return "Project root not found"

    settings = get_settings()
    exclude = settings.target_projects[0].exclude_paths if settings.target_projects else []

    results = []
    for py_file in root.rglob("*.py"):
        rel = str(py_file.relative_to(root))
        if any(rel.startswith(exc) for exc in exclude):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                if keyword.lower() in line.lower():
                    results.append(f"{rel}:{i}: {line.strip()[:100]}")
        except Exception:
            continue

    if not results:
        return f"No files found containing '{keyword}'"
    return "\n".join(results[:30])


@tool
def list_project_files(directory: str = "src") -> str:
    """List Python files in a project directory."""
    root = Path(_get_project_root()) / directory
    if not root.exists():
        return f"Directory not found: {directory}"

    files = []
    for py_file in sorted(root.rglob("*.py")):
        rel = str(py_file.relative_to(Path(_get_project_root())))
        size = py_file.stat().st_size
        files.append(f"{rel} ({size} bytes)")

    return "\n".join(files) if files else "No Python files found"


@tool
def get_git_history(count: int = 10) -> str:
    """Get recent git commit history."""
    import subprocess
    root = _get_project_root()
    try:
        result = subprocess.run(
            ["git", "-C", root, "log", f"--oneline", f"-{count}"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout if result.returncode == 0 else f"Git error: {result.stderr[:200]}"
    except Exception as e:
        return f"Error: {e}"
