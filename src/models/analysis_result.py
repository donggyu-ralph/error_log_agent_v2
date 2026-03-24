"""Analysis result model."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    error_type: str
    root_cause: str
    severity: str  # low, medium, high, critical
    affected_files: list[str] = []
    suggested_fix: str = ""
    web_search_results: list[dict[str, Any]] = []
    confidence: float = 0.0
