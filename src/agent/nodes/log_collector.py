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


async def _get_sources() -> list[dict]:
    """Get monitoring sources from DB + config.yaml fallback."""
    sources = []

    # 1. Try DB first (Services tab)
    try:
        from src.server.scheduler import _db
        if _db:
            services = await _db.list_monitored_services()
            for svc in services:
                if not svc.get("enabled", True):
                    continue
                if svc.get("source_type") == "k8s_pod":
                    sources.append({
                        "type": "k8s_pod",
                        "namespace": svc.get("namespace", ""),
                        "label_selector": svc.get("label_selector", ""),
                        "since_seconds": 120,
                        "service_name": svc.get("name", ""),
                    })
                elif svc.get("source_type") == "remote_file":
                    sources.append({
                        "type": "remote_file",
                        "host": svc.get("log_path", "").split(":")[0] if ":" in svc.get("log_path", "") else "",
                        "user": "sam",
                        "log_path": svc.get("log_path", "").split(":")[-1] if ":" in svc.get("log_path", "") else svc.get("log_path", ""),
                        "service_name": svc.get("name", ""),
                    })

            if sources:
                logger.info("sources_from_db", count=len(sources))
                return sources
    except Exception as e:
        logger.warning("db_sources_failed_using_config", error=str(e))

    # 2. Fallback to config.yaml
    settings = get_settings()
    for source in settings.log_collector.sources:
        sources.append(source)

    logger.info("sources_from_config", count=len(sources))
    return sources


async def collect_logs_node(state: AgentState) -> dict:
    """Collect logs from all configured sources (DB + config fallback)."""
    settings = get_settings()
    all_errors = []

    sources = await _get_sources()

    for source in sources:
        if source.get("type") == "k8s_pod":
            lines = await _k8s_collector.collect(
                namespace=source["namespace"],
                label_selector=source["label_selector"],
                since_seconds=source.get("since_seconds", 120),
            )
            svc_name = source.get("service_name") or source.get("label_selector", "").split("=")[-1]
            errors = parse_log_lines(
                lines,
                source="k8s_pod",
                namespace=source["namespace"],
                service_name=svc_name,
            )
            all_errors.extend(errors)

        elif source.get("type") == "remote_file":
            lines = await _file_collector.collect(
                host=source["host"],
                user=source["user"],
                log_path=source["log_path"],
            )
            svc_name = source.get("service_name") or source.get("host", "remote")
            errors = parse_log_lines(
                lines,
                source="file_log",
                service_name=svc_name,
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
        sources=len(sources),
    )

    return {
        "error_logs": [e.model_dump() for e in unique],
    }
