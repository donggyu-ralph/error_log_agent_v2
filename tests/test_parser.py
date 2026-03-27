"""Unit tests for log parser and filter."""
import pytest

from src.log_collector.parser import parse_log_lines, _parse_structlog_message
from src.log_collector.filter import filter_errors, deduplicate, compute_signature


# --- Standard Log Parsing ---

class TestStandardLogParsing:
    def test_parse_error_line(self):
        lines = [
            "2026-03-24 14:30:45 - data-pipeline - ERROR - Something went wrong",
        ]
        errors = parse_log_lines(lines, source="k8s_pod", service_name="test")
        assert len(errors) == 1
        assert errors[0].level == "ERROR"
        assert errors[0].message == "Something went wrong"
        assert errors[0].service_name == "test"

    def test_parse_critical_line(self):
        lines = [
            "2026-03-24 14:30:45 - svc - CRITICAL - Fatal error occurred",
        ]
        errors = parse_log_lines(lines, source="k8s_pod")
        assert len(errors) == 1
        assert errors[0].level == "CRITICAL"

    def test_skip_info_lines(self):
        lines = [
            "2026-03-24 14:30:45 - svc - INFO - All good",
            "2026-03-24 14:30:46 - svc - WARNING - Not great",
            "2026-03-24 14:30:47 - svc - DEBUG - Debug info",
        ]
        errors = parse_log_lines(lines)
        assert len(errors) == 0

    def test_parse_with_traceback(self):
        lines = [
            "2026-03-24 14:30:45 - svc - ERROR - Pipeline failed",
            "Traceback (most recent call last):",
            '  File "/app/src/main.py", line 42, in run',
            "    result = process(data)",
            '  File "/app/src/process.py", line 10, in process',
            "    raise ValueError('bad data')",
            "ValueError: bad data",
        ]
        errors = parse_log_lines(lines)
        assert len(errors) == 1
        assert errors[0].traceback is not None
        assert "ValueError" in errors[0].traceback
        assert errors[0].error_type == "ValueError"
        assert errors[0].file_path == "/app/src/process.py"
        assert errors[0].line_number == 10
        assert errors[0].function_name == "process"

    def test_parse_error_type_from_message(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - FileNotFoundError: config.json not found",
        ]
        errors = parse_log_lines(lines)
        assert len(errors) == 1
        assert errors[0].error_type == "FileNotFoundError"

    def test_parse_httpx_error(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - Request failed",
            "Traceback (most recent call last):",
            '  File "/app/src/services/qwen_client.py", line 39, in chat',
            "    response.raise_for_status()",
            "httpx.HTTPStatusError: Client error '400 Bad Request'",
        ]
        errors = parse_log_lines(lines)
        assert len(errors) == 1
        assert errors[0].error_type == "httpx.HTTPStatusError"
        assert errors[0].file_path == "/app/src/services/qwen_client.py"

    def test_prefer_project_files_over_site_packages(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - Error",
            "Traceback (most recent call last):",
            '  File "/usr/lib/python3.11/site-packages/httpx/_client.py", line 100, in send',
            "    return self._send(request)",
            '  File "/app/src/services/api.py", line 25, in call_api',
            "    resp = await client.get(url)",
            "httpx.ConnectError: Connection refused",
        ]
        errors = parse_log_lines(lines)
        assert errors[0].file_path == "/app/src/services/api.py"
        assert errors[0].line_number == 25

    def test_empty_lines(self):
        errors = parse_log_lines([])
        assert errors == []

    def test_non_matching_lines(self):
        lines = ["random text", "another line", ""]
        errors = parse_log_lines(lines)
        assert errors == []

    def test_timestamp_with_comma_millis(self):
        lines = [
            "2026-03-24 14:30:45,123 - svc - ERROR - Error with comma timestamp",
        ]
        errors = parse_log_lines(lines)
        assert len(errors) == 1
        assert errors[0].timestamp == "2026-03-24 14:30:45,123"


# --- Structlog Message Parsing ---

class TestStructlogParsing:
    def test_parse_structlog_with_event(self):
        raw = "{'event': 'Pipeline abc failed at upload: Analysis failed', 'logger': 'src.pipeline.manager', 'level': 'error', 'timestamp': '2026-03-24T04:40:59.827401Z'}"
        clean, error_type, file_path, tb = _parse_structlog_message(raw)
        assert "Pipeline abc failed" in clean
        assert tb is None

    def test_parse_structlog_with_exception(self):
        raw = """{'event': 'Pipeline failed', 'exception': 'Traceback (most recent call last):\\n  File "/app/src/main.py", line 10, in run\\n    raise ValueError("bad")\\nValueError: bad'}"""
        clean, error_type, file_path, tb = _parse_structlog_message(raw)
        assert error_type == "ValueError"
        assert tb is not None
        assert "Traceback" in tb

    def test_parse_structlog_with_error_key(self):
        raw = "{'error': 'httpx.ConnectError: Connection refused', 'event': 'pipeline_failed'}"
        clean, error_type, file_path, tb = _parse_structlog_message(raw)
        assert error_type == "httpx.ConnectError"

    def test_parse_non_structlog(self):
        raw = "just a plain message"
        clean, error_type, file_path, tb = _parse_structlog_message(raw)
        assert clean == raw
        assert error_type is None

    def test_parse_malformed_dict(self):
        raw = "{'broken: dict"
        clean, error_type, file_path, tb = _parse_structlog_message(raw)
        assert clean == raw


# --- Filter Tests ---

class TestFilter:
    def test_filter_error_level(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - Error 1",
            "2026-03-24 10:00:01 - svc - CRITICAL - Critical 1",
        ]
        errors = parse_log_lines(lines)
        filtered = filter_errors(errors, ["ERROR", "CRITICAL"])
        assert len(filtered) == 2

    def test_filter_only_error(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - Error 1",
            "2026-03-24 10:00:01 - svc - CRITICAL - Critical 1",
        ]
        errors = parse_log_lines(lines)
        filtered = filter_errors(errors, ["ERROR"])
        assert len(filtered) == 1
        assert filtered[0].level == "ERROR"

    def test_filter_adds_signature(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - test error",
        ]
        errors = parse_log_lines(lines)
        filtered = filter_errors(errors)
        assert filtered[0].signature is not None
        assert len(filtered[0].signature) == 32  # MD5 hex


# --- Deduplication Tests ---

class TestDedup:
    def test_deduplicate_identical(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - same error",
            "2026-03-24 10:00:01 - svc - ERROR - same error",
        ]
        errors = parse_log_lines(lines)
        filtered = filter_errors(errors)
        unique = deduplicate(filtered)
        assert len(unique) == 1

    def test_deduplicate_different(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - error one",
            "2026-03-24 10:00:01 - svc - ERROR - error two",
        ]
        errors = parse_log_lines(lines)
        filtered = filter_errors(errors)
        unique = deduplicate(filtered)
        assert len(unique) == 2

    def test_deduplicate_with_seen_set(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - known error",
        ]
        errors = parse_log_lines(lines)
        filtered = filter_errors(errors)
        sig = compute_signature(filtered[0])
        seen = {sig}
        unique = deduplicate(filtered, seen)
        assert len(unique) == 0  # Already seen

    def test_compute_signature_deterministic(self):
        lines = [
            "2026-03-24 10:00:00 - svc - ERROR - test error",
        ]
        errors = parse_log_lines(lines)
        sig1 = compute_signature(errors[0])
        sig2 = compute_signature(errors[0])
        assert sig1 == sig2
