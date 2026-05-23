"""Authentication routes: unlock, lock, setup, key generation."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.dependencies import SESSION_COOKIE, get_session_data
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
    settings = get_settings()
    saved_key_dir = str(settings.key_dir) if settings.key_dir else ""
    return templates.TemplateResponse(
        "unlock.html",
        {
            "request": request,
            "drives": drives,
            "saved_key_dir": saved_key_dir,
            "error": None,
        },
    )


@router.post("/unlock", response_class=HTMLResponse)
async def do_unlock(
    request: Request,
    key_dir: str = Form(...),
    passphrase: str = Form(...),
):
    error = None
    try:
        if not key_dir_has_keys(key_dir):
            error = f"No key files found in: {key_dir}"
        else:
            keys = load_keys(key_dir, passphrase)
            token = session_svc.create_session(keys, key_dir)
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
    response = RedirectResponse("/unlock", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    drives = detect_removable_drives()
    return templates.TemplateResponse(
        "setup.html",
        {"request": request, "drives": drives, "result": None, "error": None},
    )


@router.post("/setup/generate", response_class=HTMLResponse)
async def generate_keys(
    request: Request,
    key_dir: str = Form(...),
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
            result = meta
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
        },
    )
