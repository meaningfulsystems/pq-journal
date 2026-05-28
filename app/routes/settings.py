"""Settings page routes."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.dependencies import require_unlocked
from app.services.session import SessionData
from app.services.stt import get_active_engine
from app.services.emotion_text import get_emotion_engine

from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])


async def _check_ollama(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(f"{url}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def _count_prompts(path: Path) -> int:
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        prompts = data.get("prompts", [])
        return len(prompts)
    except Exception:
        return 0


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    saved: bool = False,
    session: SessionData = Depends(require_unlocked),
):
    settings = get_settings()
    ollama_available = await _check_ollama(settings.ollama_url)
    prompt_count = _count_prompts(settings.prompts_path)

    hf_available = False
    try:
        import transformers  # noqa: F401
        hf_available = True
    except ImportError:
        pass

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "stt_engine": get_active_engine(),
            "emotion_engine": get_emotion_engine(),
            "hf_available": hf_available,
            "ollama_available": ollama_available,
            "prompts_path": settings.prompts_path,
            "prompt_count": prompt_count,
            "saved": saved,
            "key_dir": session.key_dir,
            "ai_mode_configured": settings.ai_mode_configured,
        },
    )


@router.post("/settings")
async def save_settings(
    request: Request,
    session: SessionData = Depends(require_unlocked),
    auto_lock_minutes: int = Form(10),
    stt_model: str = Form("large-v3-turbo"),
    vosk_model_dir: str = Form(""),
    ollama_url: str = Form("http://localhost:11434"),
    ollama_model: str = Form("llama3.2:3b"),
    emotion_window_seconds: int = Form(30),
    emotion_min_seconds: int = Form(20),
    emotion_min_words: int = Form(10),
    enable_webcam: str = Form(None),
    ai_mode: str = Form(None),
):
    """Persist settings to {journal_dir}/settings/settings.yaml."""
    cfg = get_settings()
    settings_data = {
        "auto_lock_minutes": auto_lock_minutes,
        "stt_model": stt_model,
        "ollama_url": ollama_url,
        "ollama_model": ollama_model,
        "emotion_window_seconds": max(emotion_min_seconds, emotion_window_seconds),
        "emotion_min_seconds": emotion_min_seconds,
        "emotion_min_words": emotion_min_words,
        "enable_webcam": enable_webcam == "true",
        "ai_mode": ai_mode == "true",
        "ai_mode_configured": True,
    }
    if vosk_model_dir.strip():
        settings_data["vosk_model_dir"] = vosk_model_dir.strip()

    try:
        settings_path = cfg.settings_path
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w") as f:
            yaml.dump(settings_data, f, default_flow_style=False, allow_unicode=True)
        for k, v in settings_data.items():
            os.environ[k.upper()] = str(v)
        get_settings.cache_clear()
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")

    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/set-ai-mode")
async def set_ai_mode(
    request: Request,
    session: SessionData = Depends(require_unlocked),
    enable: str = Form(...),
):
    """First-run: record the user's AI mode choice and save it."""
    cfg = get_settings()
    enabled = enable == "true"

    existing: dict = {}
    try:
        if cfg.settings_path.exists():
            with open(cfg.settings_path) as f:
                existing = yaml.safe_load(f) or {}
    except Exception:
        pass

    existing["ai_mode"] = enabled
    existing["ai_mode_configured"] = True

    try:
        cfg.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg.settings_path, "w") as f:
            yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
        os.environ["AI_MODE"] = str(enabled)
        os.environ["AI_MODE_CONFIGURED"] = "True"
        get_settings.cache_clear()
    except Exception as e:
        logger.error(f"Failed to save ai_mode: {e}")

    if enabled:
        return RedirectResponse("/settings?saved=1&ai_just_enabled=1", status_code=303)
    return RedirectResponse("/journal", status_code=303)
