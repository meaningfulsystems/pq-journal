"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.dependencies import SessionExpired
from app.models.db import init_db
from app.services import session as session_svc
from app.routes import auth, journal, files, voice, settings, emotion
from app.services import stt as stt_svc
from app.services import emotion_text as emotion_svc
from app.services import emotion_video as video_svc


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    cfg = get_settings()

    # Initialize session manager
    session_svc.init_session_manager(cfg.secret_key)

    # Initialize database
    await init_db()

    # Ensure entries directory exists
    cfg.entries_dir.mkdir(parents=True, exist_ok=True)

    # Initialize STT (non-blocking: model download happens on first transcription)
    asyncio.get_event_loop().run_in_executor(
        None, stt_svc.init_stt, cfg.stt_model, cfg.vosk_model_dir
    )

    # Initialize emotion services (non-blocking)
    asyncio.get_event_loop().run_in_executor(None, emotion_svc.init_emotion_classifier)
    asyncio.get_event_loop().run_in_executor(None, video_svc.init_fer)

    # Start background auto-lock sweeper
    sweeper_task = asyncio.create_task(_auto_lock_sweeper(cfg.auto_lock_minutes * 60))

    yield

    # Shutdown
    sweeper_task.cancel()
    session_svc.destroy_all_sessions()


async def _auto_lock_sweeper(max_idle_seconds: float) -> None:
    """Background task: remove expired sessions every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        removed = session_svc.sweep_expired_sessions(max_idle_seconds)
        if removed:
            print(f"[auto-lock] Removed {removed} expired session(s)")


app = FastAPI(
    title="PQ Journal",
    description="Post-quantum encrypted personal journal",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None,   # Disable Swagger UI in production
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(journal.router)
app.include_router(files.router)
app.include_router(voice.router)
app.include_router(settings.router)
app.include_router(emotion.router)

templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(SessionExpired)
async def session_expired_handler(request: Request, exc: SessionExpired):
    if exc.is_htmx:
        return JSONResponse(
            status_code=401,
            content={"detail": "Session expired"},
            headers={"HX-Redirect": "/unlock"},
        )
    return RedirectResponse("/unlock", status_code=302)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "message": "Page not found"},
        status_code=404,
    )


@app.exception_handler(500)
async def server_error(request: Request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "message": "Internal server error"},
        status_code=500,
    )
