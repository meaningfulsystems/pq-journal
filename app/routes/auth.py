"""Authentication routes: unlock, lock, setup, key generation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.dependencies import SESSION_COOKIE, get_session_data
from app.models.db import clear_db_encryption_key, derive_db_key, init_db, set_db_encryption_key
from app.services import session as session_svc
from app.services.key_store import (
    detect_removable_drives,
    generate_and_save_keys,
    key_dir_has_keys,
    load_keys,
)
from app.services.session import SessionData

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


def _apply_journal_settings(journal_dir: str) -> None:
    """
    Set JOURNAL_DIR env var and load any saved settings from the journal's settings dir.
    Called at unlock time so settings are journal-specific and no paths leak into app root.
    """
    os.environ["JOURNAL_DIR"] = journal_dir
    settings_file = Path(journal_dir) / "settings" / "settings.yaml"
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                data = yaml.safe_load(f) or {}
            for k, v in data.items():
                os.environ[k.upper()] = str(v)
        except Exception:
            pass
    get_settings.cache_clear()


@router.get("/", response_class=HTMLResponse)
async def root(session: Optional[SessionData] = Depends(get_session_data)):
    if session:
        return RedirectResponse("/journal", status_code=302)
    return RedirectResponse("/unlock", status_code=302)


@router.get("/unlock", response_class=HTMLResponse)
async def unlock_page(
    request: Request,
    session: Optional[SessionData] = Depends(get_session_data),
):
    if session:
        return RedirectResponse("/journal", status_code=302)
    drives = detect_removable_drives()
    return templates.TemplateResponse(
        "unlock.html",
        {
            "request": request,
            "drives": drives,
            "saved_journal_dir": "",
            "saved_key_dir": "",
            "error": None,
        },
    )


@router.post("/unlock", response_class=HTMLResponse)
async def do_unlock(
    request: Request,
    journal_dir: str = Form(...),
    key_dir: str = Form(...),
    passphrase: str = Form(...),
):
    error = None
    try:
        journal_dir = journal_dir.strip()
        key_dir = key_dir.strip()

        if not journal_dir:
            error = "Journal directory is required"
        elif not key_dir_has_keys(key_dir):
            error = f"No key files found in: {key_dir}"
        else:
            keys = load_keys(key_dir, passphrase)

            # Apply journal dir: sets JOURNAL_DIR env var, loads journal settings, clears cache
            _apply_journal_settings(journal_dir)
            cfg = get_settings()

            # Initialize journal directory and database (deferred to login time)
            cfg.entries_dir.mkdir(parents=True, exist_ok=True)
            await init_db()

            token = session_svc.create_session(keys, key_dir, journal_dir)
            set_db_encryption_key(derive_db_key(keys["kem_priv"], keys["x25519_priv"]))

            response = RedirectResponse("/journal", status_code=302)
            response.set_cookie(
                key=SESSION_COOKIE,
                value=token,
                httponly=True,
                samesite="strict",
                secure=False,  # localhost HTTP — acceptable
                max_age=86400,
            )
            return response
    except ValueError as e:
        error = str(e)
    except Exception as e:
        error = f"Unlock failed: {e}"

    drives = detect_removable_drives()
    return templates.TemplateResponse(
        "unlock.html",
        {
            "request": request,
            "drives": drives,
            "saved_journal_dir": journal_dir,
            "saved_key_dir": key_dir,
            "error": error,
        },
        status_code=400,
    )


@router.post("/lock")
async def lock(request: Request):
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        session_svc.destroy_session(cookie)
    clear_db_encryption_key()
    response = RedirectResponse("/unlock", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    drives = detect_removable_drives()
    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "drives": drives,
            "result": None,
            "error": None,
            "default_journal_dir": str(Path.home() / "MeaningfulJournal"),
        },
    )


@router.post("/setup/generate", response_class=HTMLResponse)
async def generate_keys(
    request: Request,
    key_dir: str = Form(...),
    journal_dir: str = Form(default=""),
    passphrase: str = Form(...),
    passphrase_confirm: str = Form(...),
):
    error = None
    result = None

    if passphrase != passphrase_confirm:
        error = "Passphrases do not match"
    elif len(passphrase) < 12:
        error = "Passphrase must be at least 12 characters"
    elif not key_dir.strip():
        error = "Key directory is required"
    else:
        try:
            meta = generate_and_save_keys(key_dir.strip(), passphrase)
            result = {**meta, "key_dir": key_dir.strip()}
            # Save initial settings inside the journal dir (not in app root)
            if journal_dir.strip():
                journal_path = Path(journal_dir.strip())
                settings_dir = journal_path / "settings"
                settings_dir.mkdir(parents=True, exist_ok=True)
                settings_data = {
                    "auto_lock_minutes": 10,
                    "stt_model": "large-v3-turbo",
                    "ollama_url": "http://localhost:11434",
                    "ollama_model": "llama3.2:3b",
                    "emotion_window_seconds": 30,
                    "emotion_min_seconds": 20,
                    "emotion_min_words": 10,
                    "enable_webcam": False,
                    "enable_debug": False,
                }
                with open(settings_dir / "settings.yaml", "w") as f:
                    yaml.dump(settings_data, f, default_flow_style=False)
        except Exception as e:
            error = f"Key generation failed: {e}"

    drives = detect_removable_drives()
    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "drives": drives,
            "result": result,
            "error": error,
            "default_journal_dir": journal_dir or str(Path.home() / "MeaningfulJournal"),
        },
    )
