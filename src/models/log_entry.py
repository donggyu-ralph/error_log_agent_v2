"""Log entry models."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ErrorInfo(BaseModel):
    timestamp: str
    level: str  # ERROR, CRITICAL
    message: str
    traceback: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    error_type: Optional[str] = None
    source: str  # "k8s_pod" | "file_log"
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    container: Optional[str] = None
    service_name: Optional[str] = None
    signature: Optional[str] = None  # MD5 for dedup
