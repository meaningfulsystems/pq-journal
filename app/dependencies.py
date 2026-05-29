from __future__ import annotations

from typing import AsyncGenerator, Optional

from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import get_db
from app.services import session as session_svc
from app.services.session import SessionData

SESSION_COOKIE = "pqj_session"


class SessionExpired(Exception):
    """Raised when a protected route is accessed without a valid session."""
    def __init__(self, is_htmx: bool = False):
        self.is_htmx = is_htmx


async def get_session_data(
    request: Request,
    pqj_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
) -> Optional[SessionData]:
    """Return session data if a valid session cookie is present, else None."""
    if not pqj_session:
        return None
    settings = get_settings()
    max_idle = settings.auto_lock_minutes * 60
    # Background recording calls (emotion analysis, status checks) must not
    # reset the idle timer — otherwise the session never expires during recording.
    if request.headers.get("X-Background") == "1":
        return session_svc.peek_session(pqj_session, max_idle_seconds=max_idle)
    return session_svc.get_session(pqj_session, max_idle_seconds=max_idle)


async def require_unlocked(
    request: Request,
    session: Optional[SessionData] = Depends(get_session_data),
) -> SessionData:
    """
    FastAPI dependency: require a valid unlocked session.
    Raises SessionExpired which is caught by the global exception handler.
    """
    if session is None:
        raise SessionExpired(is_htmx=bool(request.headers.get("HX-Request")))
    return session


async def get_db_session(db: AsyncSession = Depends(get_db)) -> AsyncGenerator[AsyncSession, None]:
    yield db
