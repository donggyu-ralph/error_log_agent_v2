"""Log collection node."""
from src.agent.state import AgentState
from src.config.settings import get_settings
from src.config.logging_config import get_logger
from src.log_collector.k8s_collector import K8sLogCollector
from src.log_collector.file_collector import RemoteFileCollector
from src.log_collector.parser import parse_log_lines
from src.log_collector.filter import filter_errors, deduplicate

logger = get_logger(__name__)

_k8s_collector = K8sLogCollector()
_file_collector = RemoteFileCollector()
_seen_signatures: set[str] = set()


async def collect_logs_node(state: AgentState) -> dict:
    """Collect logs from all configured sources."""
    settings = get_settings()
    all_errors = []

    for source in settings.log_collector.sources:
        if source.get("type") == "k8s_pod":
            lines = await _k8s_collector.collect(
                namespace=source["namespace"],
                label_selector=source["label_selector"],
                since_seconds=source.get("since_seconds", 120),
            )
            errors = parse_log_lines(
                lines,
                source="k8s_pod",
                namespace=source["namespace"],
                service_name=source.get("label_selector", "").split("=")[-1],
            )
            all_errors.extend(errors)

        elif source.get("type") == "remote_file":
            lines = await _file_collector.collect(
                host=source["host"],
                user=source["user"],
                log_path=source["log_path"],
            )
            errors = parse_log_lines(
                lines,
                source="file_log",
                service_name=source.get("host", "remote"),
            )
            all_errors.extend(errors)

    # Filter and deduplicate
    filtered = filter_errors(all_errors, settings.log_collector.log_levels)
    unique = deduplicate(filtered, _seen_signatures)

    logger.info(
        "logs_collected",
        total_errors=len(all_errors),
        filtered=len(filtered),
        unique=len(unique),
    )

    return {
        "error_logs": [e.model_dump() for e in unique],
    }
