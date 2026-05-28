"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.dependencies import SessionExpired
from app.services import session as session_svc
from app.routes import auth, journal, files, voice, settings, emotion
from app.services import stt as stt_svc
from app.services import emotion_text as emotion_svc
from app.services import emotion_video as video_svc

_CSP = (
    "default-src 'self'; "
    # blob: required for AudioWorklet processor loaded via URL.createObjectURL()
    "script-src 'self' 'unsafe-inline' blob: https://cdn.tailwindcss.com https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self' ws://localhost:* ws://127.0.0.1:*; "
    "frame-ancestors 'none';"
)


class SecurityHeadersMiddleware:
    """
    Raw ASGI middleware: adds security headers to every HTTP response (R104).
    Explicitly passes WebSocket and lifespan scopes through unchanged —
    BaseHTTPMiddleware is avoided because it breaks WebSocket connections.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            # WebSocket upgrade and lifespan events pass through unmodified
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"content-security-policy", _CSP.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


# Ranked model preferences: first match wins
_OLLAMA_MODEL_PREFERENCE = ["phi3", "llama3.2", "llama3.1", "llama3", "mistral", "tinyllama"]


def _detect_and_set_ollama_model(url: str, current_model: str) -> None:
    """
    At startup, verify the configured Ollama model is pulled.
    If not, auto-select the best available model and update settings.yaml.
    """
    import httpx
    import yaml

    try:
        r = httpx.get(f"{url}/api/tags", timeout=3.0)
        if r.status_code != 200:
            return
        models = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return  # Ollama not running — handled elsewhere

    if not models:
        return

    # Current model is available — nothing to do
    if any(current_model in m for m in models):
        return

    # Pick best available by preference ranking
    selected = None
    for pref in _OLLAMA_MODEL_PREFERENCE:
        match = next((m for m in models if pref in m.lower()), None)
        if match:
            selected = match
            break
    if selected is None:
        selected = models[0]

    # Persist the selection to settings.yaml
    settings_path = Path("settings.yaml")
    try:
        data: dict = {}
        if settings_path.exists():
            with open(settings_path) as f:
                data = yaml.safe_load(f) or {}
        data["ollama_model"] = selected
        with open(settings_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        get_settings.cache_clear()
        print(
            f"[ollama] Model '{current_model}' not found in pulled models. "
            f"Auto-selected '{selected}'. Available: {models}"
        )
    except Exception as e:
        print(f"[ollama] Warning: could not update settings.yaml: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    cfg = get_settings()

    # Initialize session manager
    session_svc.init_session_manager(cfg.secret_key)

    # Note: init_db() and entries_dir creation happen at unlock time (not startup),
    # so the app root never needs to know where the journal lives.


    # Auto-detect best available Ollama model (awaited: fast network check, must complete before serving)
    await asyncio.get_event_loop().run_in_executor(
        None, _detect_and_set_ollama_model, cfg.ollama_url, cfg.ollama_model
    )

    # Re-read settings in case model was updated
    cfg = get_settings()

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

app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(journal.router)
app.include_router(files.router)
app.include_router(voice.router)
app.include_router(settings.router)
app.include_router(emotion.router)

from app.templating import templates


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
