"""Slack Bolt app with Socket Mode."""
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from src.config.settings import get_settings
from src.config.logging_config import get_logger

logger = get_logger(__name__)

_app: AsyncApp | None = None
_handler: AsyncSocketModeHandler | None = None


def get_slack_app() -> AsyncApp:
    """Get or create the Slack Bolt app."""
    global _app
    if _app is None:
        settings = get_settings()
        _app = AsyncApp(
            token=settings.slack.bot_token,
            signing_secret=settings.slack.signing_secret,
        )
        # Register handlers
        from src.slack.handlers import register_handlers
        register_handlers(_app)
    return _app


async def start_slack_bot() -> None:
    """Start the Slack bot in Socket Mode."""
    global _handler
    settings = get_settings()

    if not settings.slack.enabled:
        logger.info("slack_disabled")
        return

    app = get_slack_app()
    _handler = AsyncSocketModeHandler(app, settings.slack.app_token)

    logger.info("slack_bot_starting")
    await _handler.start_async()


async def stop_slack_bot() -> None:
    """Stop the Slack bot."""
    global _handler
    if _handler:
        await _handler.close_async()
        logger.info("slack_bot_stopped")
