"""Server-side file browser for key directory selection."""
from __future__ import annotations

import platform
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.key_store import browse_directory, detect_removable_drives

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/drives")
async def list_drives() -> JSONResponse:
    """Return detected removable drives (USB, etc.)."""
    drives = detect_removable_drives()
    return JSONResponse({"drives": drives})


@router.get("/browse")
async def browse(path: str = "") -> JSONResponse:
    """Browse server filesystem for key directory selection."""
    if not path:
        path = _default_start_path()
    result = browse_directory(path)
    return JSONResponse(result)


@router.get("/home")
async def home_dir() -> JSONResponse:
    """Return the user's home directory path."""
    return JSONResponse({"path": str(Path.home())})


def _default_start_path() -> str:
    if platform.system() == "Windows":
        return "C:\\"
    return str(Path.home())
