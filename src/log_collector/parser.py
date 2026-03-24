"""Python traceback parser for log lines."""
import ast
import re
from typing import Optional

from src.models.log_entry import ErrorInfo
from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Standard log line: 2026-03-23 14:30:45 - service-name - ERROR - message
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d+)?)\s+-\s+(\S+)\s+-\s+(ERROR|CRITICAL)\s+-\s+(.+)$"
)

# Traceback block
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

# Error type patterns in messages
MESSAGE_ERROR_TYPE_PATTERN = re.compile(
    r"(\w+(?:\.\w+)*(?:Error|Exception|Timeout))\s*:"
)


def _parse_structlog_message(raw_message: str) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Parse structlog dict-formatted message into human-readable parts.

    Returns: (clean_message, error_type, file_path_hint, traceback_text)
    """
    try:
        data = ast.literal_eval(raw_message)
        if isinstance(data, dict):
            # structlog uses 'event' for message, 'error' for error string
            event_msg = data.get("event", "")
            error_msg = data.get("error", "")
            exception_text = data.get("exception", "")
            stage = data.get("stage", "")
            pipeline_id = data.get("pipeline_id", "")

            # The main error text - prefer event, then error
            main_text = event_msg or error_msg

            # Extract error type from exception traceback first
            error_type = None
            file_path = None
            traceback_text = None

            if exception_text:
                traceback_text = exception_text
                # Get error type from last line of traceback
                type_match = ERROR_TYPE_PATTERN.search(exception_text)
                if type_match:
                    error_type = type_match.group(1)
                # Get file path
                file_refs = list(FILE_REF_PATTERN.finditer(exception_text))
                if file_refs:
                    project_refs = [r for r in file_refs if "site-packages" not in r.group(1)]
                    ref = project_refs[-1] if project_refs else file_refs[-1]
                    file_path = f"{ref.group(1)}:{ref.group(2)}"

            # Fallback: extract error type from message
            if not error_type:
                for text in [main_text, error_msg]:
                    if text:
                        m = MESSAGE_ERROR_TYPE_PATTERN.search(text)
                        if m:
                            error_type = m.group(1)
                            break

            # Build clean message
            clean = main_text.split("\nFor more information")[0].strip()
            if not clean:
                clean = error_msg.split("\nFor more information")[0].strip()

            return clean, error_type, file_path, traceback_text
    except (ValueError, SyntaxError):
        pass

    return raw_message, None, None, None


def parse_log_lines(
    lines: list[str],
    source: str = "k8s_pod",
    pod_name: Optional[str] = None,
    namespace: Optional[str] = None,
    service_name: Optional[str] = None,
) -> list[ErrorInfo]:
    """Parse log lines and extract error entries with tracebacks."""
    errors = []

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
                project_refs = [
                    ref for ref in file_refs
                    if "site-packages" not in ref.group(1) and "/usr/" not in ref.group(1)
                ]
                last_ref = project_refs[-1] if project_refs else file_refs[-1]
                file_path = last_ref.group(1)
                line_number = int(last_ref.group(2))
                function_name = last_ref.group(3)

            # Extract error type from traceback
            type_match = ERROR_TYPE_PATTERN.search(traceback_text)
            if type_match:
                error_type = type_match.group(1)

        # Parse structlog dict messages
        clean_message = message
        if message.startswith("{") or message.startswith("{'"):
            clean_message, parsed_type, parsed_path, parsed_tb = _parse_structlog_message(message)
            if not error_type and parsed_type:
                error_type = parsed_type
            if not traceback_text and parsed_tb:
                traceback_text = parsed_tb
                # Re-extract file info from structlog traceback
                file_refs = list(FILE_REF_PATTERN.finditer(parsed_tb))
                if file_refs:
                    project_refs = [r for r in file_refs if "site-packages" not in r.group(1) and "/usr/" not in r.group(1)]
                    ref = project_refs[-1] if project_refs else file_refs[-1]
                    file_path = ref.group(1)
                    line_number = int(ref.group(2))
                    function_name = ref.group(3)

        # Try to extract error type from message
        if not error_type:
            type_match = MESSAGE_ERROR_TYPE_PATTERN.search(clean_message)
            if type_match:
                error_type = type_match.group(1)

        # Extract file path from logger name if not found
        if not file_path and logger_name.startswith("src."):
            file_path = logger_name.replace(".", "/") + ".py"

        svc = service_name or logger_name

        errors.append(ErrorInfo(
            timestamp=timestamp,
            level=level,
            message=clean_message,
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
