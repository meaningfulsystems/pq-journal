"""Settings page routes."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings

from app.config import get_settings
from app.dependencies import require_unlocked
from app.services.session import SessionData
from app.services.stt import get_active_engine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])
templates = Jinja2Templates(directory="app/templates")


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
    _session: SessionData = Depends(require_unlocked),
):
    settings = get_settings()
    ollama_available = await _check_ollama(settings.ollama_url)
    prompt_count = _count_prompts(settings.prompts_path)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "stt_engine": get_active_engine(),
            "ollama_available": ollama_available,
            "prompts_path": settings.prompts_path,
            "prompt_count": prompt_count,
            "saved": saved,
        },
    )


@router.post("/settings")
async def save_settings(
    request: Request,
    _session: SessionData = Depends(require_unlocked),
    journal_dir: str = Form(...),
    auto_lock_minutes: int = Form(15),
    stt_model: str = Form("large-v3-turbo"),
    vosk_model_dir: str = Form(""),
    ollama_url: str = Form("http://localhost:11434"),
    ollama_model: str = Form("llama3.2:3b"),
    enable_webcam: str = Form(None),
):
    """Persist settings to settings.yaml."""
    settings_data = {
        "journal_dir": journal_dir,
        "auto_lock_minutes": auto_lock_minutes,
        "stt_model": stt_model,
        "ollama_url": ollama_url,
        "ollama_model": ollama_model,
        "enable_webcam": enable_webcam == "true",
    }
    if vosk_model_dir.strip():
        settings_data["vosk_model_dir"] = vosk_model_dir.strip()

    try:
        with open("settings.yaml", "w") as f:
            yaml.dump(settings_data, f, default_flow_style=False, allow_unicode=True)
        # Clear the cached settings so next request reloads
        get_settings.cache_clear()
    except Exception as e:
        logger.error(f"Failed to save settings.yaml: {e}")

    return RedirectResponse("/settings?saved=1", status_code=303)
