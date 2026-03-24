"""Python traceback parser for log lines."""
import re
from typing import Optional

from src.models.log_entry import ErrorInfo
from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Standard log line: 2026-03-23 14:30:45 - service-name - ERROR - message
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d+)?)\s+-\s+(\S+)\s+-\s+(ERROR|CRITICAL)\s+-\s+(.+)$"
)

# Traceback block: capture until a line that doesn't start with whitespace
# AND is not an exception line (i.e., not the final error line)
TRACEBACK_PATTERN = re.compile(
    r"Traceback \(most recent call last\):\n(?:[ \t]+.+\n)*\S[^\n]*",
    re.MULTILINE,
)

# File reference in traceback: File "path", line N, in func
FILE_REF_PATTERN = re.compile(
    r'File "([^"]+)", line (\d+), in (\S+)'
)

# Error type from last line of traceback: ExceptionType: message
ERROR_TYPE_PATTERN = re.compile(
    r"^(\w+(?:\.\w+)*(?:Error|Exception|Warning|Timeout))\s*:\s*(.+)$",
    re.MULTILINE,
)


def parse_log_lines(
    lines: list[str],
    source: str = "k8s_pod",
    pod_name: Optional[str] = None,
    namespace: Optional[str] = None,
    service_name: Optional[str] = None,
) -> list[ErrorInfo]:
    """Parse log lines and extract error entries with tracebacks."""
    errors = []
    full_text = "\n".join(lines)

    for i, line in enumerate(lines):
        match = LOG_PATTERN.match(line)
        if not match:
            continue

        timestamp, logger_name, level, message = match.groups()

        # Look for traceback after this line
        remaining = "\n".join(lines[i + 1:])
        traceback_text = None
        file_path = None
        line_number = None
        function_name = None
        error_type = None

        # Search for traceback in the next lines
        search_window = remaining[:5000]
        tb_matches = list(TRACEBACK_PATTERN.finditer(search_window))

        if tb_matches:
            traceback_text = tb_matches[0].group(0).strip()

            # Extract file references
            file_refs = list(FILE_REF_PATTERN.finditer(traceback_text))
            if file_refs:
                # Prefer project files over site-packages
                project_refs = [
                    ref for ref in file_refs
                    if "site-packages" not in ref.group(1) and "/usr/" not in ref.group(1)
                ]
                last_ref = project_refs[-1] if project_refs else file_refs[-1]
                file_path = last_ref.group(1)
                line_number = int(last_ref.group(2))
                function_name = last_ref.group(3)

            # Extract error type
            type_match = ERROR_TYPE_PATTERN.search(traceback_text)
            if type_match:
                error_type = type_match.group(1)

        # Try to extract error type from message if not found in traceback
        if not error_type:
            type_match = re.match(r"^(\w+(?:\.\w+)*(?:Error|Exception))\s*:", message)
            if type_match:
                error_type = type_match.group(1)

        svc = service_name or logger_name

        errors.append(ErrorInfo(
            timestamp=timestamp,
            level=level,
            message=message,
            traceback=traceback_text,
            file_path=file_path,
            line_number=line_number,
            function_name=function_name,
            error_type=error_type,
            source=source,
            pod_name=pod_name,
            namespace=namespace,
            service_name=svc,
        ))

    return errors
