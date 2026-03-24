"""Fix plan model."""
from typing import Optional

from pydantic import BaseModel


class TargetFile(BaseModel):
    file_path: str
    changes_description: str
    diff_preview: Optional[str] = None


class FixPlan(BaseModel):
    summary: str
    root_cause: str
    fix_description: str
    target_files: list[TargetFile] = []
    estimated_risk: str = "low"  # low, medium, high
    requires_restart: bool = False
