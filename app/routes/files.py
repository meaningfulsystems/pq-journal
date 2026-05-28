"""Server-side file browser for key directory selection."""
from __future__ import annotations

import platform
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.dependencies import require_unlocked
from app.services.key_store import browse_directory, detect_removable_drives
from app.services.session import SessionData

router = APIRouter(prefix="/api", tags=["files"])


def _check_origin(request: Request) -> None:
    """
    Reject cross-origin requests to pre-authentication filesystem endpoints.

    Browsers always set Origin on cross-origin requests. A request from
    https://evil.com to http://localhost:8000 carries Origin: https://evil.com,
    which will not match. Requests with no Origin header (curl, direct API
    calls) are permitted — only browser cross-origin requests are blocked.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return  # non-browser / direct API call — allow

    from app.config import get_settings
    cfg = get_settings()
    expected_origins = {
        f"http://{cfg.host}:{cfg.port}",
        f"http://localhost:{cfg.port}",
        f"http://127.0.0.1:{cfg.port}",
    }
    if origin not in expected_origins:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")


@router.get("/drives")
async def list_drives(request: Request) -> JSONResponse:
    """Return detected removable drives (USB, etc.)."""
    _check_origin(request)
    drives = detect_removable_drives()
    return JSONResponse({"drives": drives})


@router.get("/browse")
async def browse(request: Request, path: str = "") -> JSONResponse:
    """Browse server filesystem for key directory selection."""
    _check_origin(request)
    if not path:
        path = _default_start_path()
    result = browse_directory(path)
    return JSONResponse(result)


@router.get("/home")
async def home_dir(request: Request) -> JSONResponse:
    """Return the user's home directory path."""
    _check_origin(request)
    return JSONResponse({"path": str(Path.home())})


class MkdirRequest(BaseModel):
    parent: str
    name: str


@router.post("/mkdir")
async def make_directory(request: Request, body: MkdirRequest) -> JSONResponse:
    """Create a new subdirectory inside parent and return the new path."""
    _check_origin(request)
    name = body.name.strip()
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return JSONResponse({"error": "Invalid directory name"}, status_code=400)
    try:
        new_dir = Path(body.parent).resolve() / name
        new_dir.mkdir(parents=False, exist_ok=False)
        return JSONResponse({"path": str(new_dir)})
    except FileExistsError:
        return JSONResponse({"error": "Directory already exists"}, status_code=400)
    except PermissionError:
        return JSONResponse({"error": "Permission denied"}, status_code=403)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)



@router.get("/ping")
async def ping(session: SessionData = Depends(require_unlocked)) -> JSONResponse:
    """Heartbeat endpoint — returns 200 while session is valid, 401 when expired."""
    return JSONResponse({"ok": True})


@router.get("/status")
async def get_status(_session: SessionData = Depends(require_unlocked)) -> JSONResponse:
    """Return active engine status for display in the UI."""
    from app.services.stt import get_active_engine
    from app.services.emotion_text import get_emotion_engine
    from app.services.emotion_video import get_fer_engine
    from app.config import get_settings
    import httpx

    cfg = get_settings()

    ollama_available = False
    llm_ok = False
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(f"{cfg.ollama_url}/api/tags")
            ollama_available = r.status_code == 200
    except Exception:
        pass

    if ollama_available:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(
                    f"{cfg.ollama_url}/api/generate",
                    json={
                        "model": cfg.ollama_model,
                        "prompt": "Reply with one word: ok",
                        "stream": False,
                        "options": {"num_predict": 5},
                    },
                )
                if r.status_code == 200 and r.json().get("response", "").strip():
                    llm_ok = True
        except Exception:
            pass

    hf_available = False
    try:
        import transformers  # noqa: F401
        hf_available = True
    except ImportError:
        pass

    return JSONResponse({
        "stt_engine": get_active_engine(),
        "emotion_engine": get_emotion_engine(),
        "fer_engine": get_fer_engine(),
        "ollama_available": ollama_available,
        "llm_ok": llm_ok,
        "hf_available": hf_available,
        "ollama_model": cfg.ollama_model,
        "emotion_window_seconds": cfg.emotion_window_seconds,
        "emotion_min_seconds": cfg.emotion_min_seconds,
        "emotion_min_words": cfg.emotion_min_words,
        "ai_mode": cfg.ai_mode,
    })


def _default_start_path() -> str:
    if platform.system() == "Windows":
        return "C:\\"
    return str(Path.home())
