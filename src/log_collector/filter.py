"""Error log filtering and deduplication."""
import hashlib
from typing import Optional

from src.models.log_entry import ErrorInfo
from src.config.logging_config import get_logger

logger = get_logger(__name__)


def compute_signature(error: ErrorInfo) -> str:
    """Compute MD5 signature for deduplication."""
    key = f"{error.error_type or ''}:{error.message}:{error.file_path or ''}:{error.line_number or ''}"
    return hashlib.md5(key.encode()).hexdigest()


def filter_errors(
    errors: list[ErrorInfo],
    log_levels: list[str] = None,
) -> list[ErrorInfo]:
    """Filter errors by level and add signatures."""
    if log_levels is None:
        log_levels = ["ERROR", "CRITICAL"]

    filtered = []
    for error in errors:
        if error.level.upper() not in log_levels:
            continue
        error.signature = compute_signature(error)
        filtered.append(error)

    return filtered


def deduplicate(
    errors: list[ErrorInfo],
    seen_signatures: Optional[set[str]] = None,
) -> list[ErrorInfo]:
    """Remove duplicate errors based on signature."""
    if seen_signatures is None:
        seen_signatures = set()

    unique = []
    for error in errors:
        sig = error.signature or compute_signature(error)
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            error.signature = sig
            unique.append(error)

    dedup_count = len(errors) - len(unique)
    if dedup_count > 0:
        logger.info("errors_deduplicated", removed=dedup_count, remaining=len(unique))

    return unique
