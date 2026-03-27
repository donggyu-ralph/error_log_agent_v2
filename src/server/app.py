"""FastAPI application with lifespan management."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config.settings import get_settings
from src.config.logging_config import setup_logging, get_logger
from src.db.manager import DBManager
from src.server.routes import router, set_db
from src.server.scheduler import start_scheduler, stop_scheduler, set_scheduler_db
from src.slack.bot import start_slack_bot, stop_slack_bot
from src.auth.routes import router as auth_router
from src.auth.manager import UserManager
from src.auth.deps import set_user_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    settings = get_settings()
    setup_logging()
    logger = get_logger(__name__)

    logger.info("starting_agent", name=settings.agent_name, version=settings.agent_version)

    # Initialize DB
    db = DBManager(settings.database)
    await db.initialize()
    set_db(db)
    set_scheduler_db(db)

    # Initialize auth
    user_mgr = UserManager(db.conn)
    await user_mgr.initialize()
    set_user_manager(user_mgr)

    # Start scheduler
    start_scheduler()

    # Start Slack bot (in background)
    if settings.slack.enabled:
        asyncio.create_task(start_slack_bot())

    logger.info("agent_started")
    yield

    # Shutdown
    logger.info("shutting_down_agent")
    stop_scheduler()
    await stop_slack_bot()
    await db.close()
    logger.info("agent_stopped")


settings = get_settings()

app = FastAPI(
    title=settings.agent_name,
    version=settings.agent_version,
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.agent_name, "version": settings.agent_version}


app.include_router(auth_router)
app.include_router(router)

# Serve React frontend static files
_frontend_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        """Serve React SPA - fallback to index.html for client-side routing."""
        file_path = _frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dir / "index.html")
