"""APScheduler configuration for periodic log collection."""
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _run_agent_cycle():
    """Run one cycle of the error log agent."""
    from src.agent.graph import get_agent

    agent = get_agent()
    thread_id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "thread_id": thread_id,
        "error_logs": [],
        "source_code_context": {},
        "analysis": "",
        "fix_plan": None,
        "human_feedback": None,
        "git_branch": None,
        "git_commit_hash": None,
        "deployment": None,
        "staging_result": None,
        "post_fix_status": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "messages": [],
        "actually_modified_files": [],
    }

    try:
        result = await agent.ainvoke(initial_state, config=config)
        error_count = len(result.get("error_logs", []))
        logger.info("agent_cycle_completed", thread_id=thread_id, errors_found=error_count)

        # If errors found and approval needed, register for Slack callback
        if error_count > 0 and result.get("fix_plan"):
            from src.slack.handlers import register_pending_approval
            from src.slack.bot import get_slack_app
            from src.slack.message_builder import build_error_report

            settings = get_settings()
            app = get_slack_app()

            # Send error report to Slack
            blocks = build_error_report(
                thread_id=thread_id,
                error_logs=result.get("error_logs", []),
                analysis=result.get("analysis", ""),
                fix_plan=result.get("fix_plan", {}),
            )

            await app.client.chat_postMessage(
                channel=settings.slack.channel,
                blocks=blocks,
                text=f"에러 감지: {result['error_logs'][0].get('error_type', 'Unknown')}",
            )

            register_pending_approval(thread_id, {
                "graph": agent,
                "config": config,
                "deployment": result.get("deployment"),
            })

    except Exception as e:
        logger.error("agent_cycle_failed", thread_id=thread_id, error=str(e))


def start_scheduler() -> AsyncIOScheduler:
    """Start the periodic log collection scheduler."""
    global _scheduler
    settings = get_settings()

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_agent_cycle,
        "interval",
        seconds=settings.log_collector.interval_seconds,
        id="log_collection",
        name="Periodic log collection",
    )
    _scheduler.start()

    logger.info(
        "scheduler_started",
        interval=settings.log_collector.interval_seconds,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
