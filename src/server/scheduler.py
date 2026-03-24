"""APScheduler configuration for periodic log collection."""
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None
_db = None


def set_scheduler_db(db):
    global _db
    _db = db


async def _run_agent_cycle():
    """Run one cycle of the error log agent.

    The graph will:
    1. Collect logs → detect errors
    2. Analyze → plan fix
    3. Hit interrupt() at request_approval → graph pauses
    4. We detect the pause, save state to DB, send Slack notification
    5. When human responds, Slack handler resumes the graph
    """
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
        # ainvoke will return when graph completes OR hits interrupt
        result = await agent.ainvoke(initial_state, config=config)

        error_logs = result.get("error_logs", [])
        error_count = len(error_logs)
        logger.info("agent_cycle_completed", thread_id=thread_id, errors_found=error_count)

        if error_count == 0:
            return

        # Save errors to DB
        if _db:
            for err in error_logs:
                try:
                    from src.models.log_entry import ErrorInfo
                    error_info = ErrorInfo(**err)
                    await _db.insert_error_log(error_info)
                    await _db.update_error_stats(error_info)
                except Exception as e:
                    logger.error("db_insert_error_failed", error=str(e))

        fix_plan = result.get("fix_plan")
        analysis = result.get("analysis", "")

        if not fix_plan:
            return

        # Save fix history
        fix_history_id = None
        if _db:
            try:
                fix_history_id = await _db.create_fix_history(
                    error_log_id=None,
                    thread_id=thread_id,
                    analysis=analysis,
                    fix_plan=fix_plan,
                )
            except Exception as e:
                logger.error("db_fix_history_failed", error=str(e))

        # Check if graph was interrupted (waiting for human approval)
        # When interrupt() is hit, ainvoke returns the state at that point
        # The graph is now paused and can be resumed with Command(resume=...)
        graph_state = agent.get_state(config)
        is_interrupted = bool(graph_state.next)  # next nodes exist = interrupted

        if is_interrupted:
            logger.info("graph_interrupted_for_approval", thread_id=thread_id)

            # Send Slack notification
            await _send_slack_report(
                thread_id=thread_id,
                error_logs=error_logs,
                analysis=analysis,
                fix_plan=fix_plan,
                fix_history_id=fix_history_id,
            )
        else:
            logger.info("graph_completed_without_approval", thread_id=thread_id)

    except Exception as e:
        logger.error("agent_cycle_failed", thread_id=thread_id, error=str(e))


async def _send_slack_report(thread_id, error_logs, analysis, fix_plan, fix_history_id=None):
    """Send error report to Slack with approval buttons."""
    try:
        from src.slack.bot import get_slack_app
        from src.slack.message_builder import build_error_report

        settings = get_settings()
        app = get_slack_app()

        blocks = build_error_report(
            thread_id=thread_id,
            error_logs=error_logs,
            analysis=analysis,
            fix_plan=fix_plan,
        )

        await app.client.chat_postMessage(
            channel=settings.slack.channel,
            blocks=blocks,
            text=f"에러 감지: {error_logs[0].get('error_type', 'Unknown')}",
        )

        logger.info("slack_report_sent", thread_id=thread_id)

    except Exception as e:
        logger.error("slack_send_failed", thread_id=thread_id, error=str(e))


def start_scheduler() -> AsyncIOScheduler:
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
    logger.info("scheduler_started", interval=settings.log_collector.interval_seconds)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
