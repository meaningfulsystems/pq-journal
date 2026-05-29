"""
In-memory session management.
Private key bytes are never written to disk after unlock.
Sessions auto-expire after configurable inactivity.
"""
from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass, field
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


@dataclass
class SessionData:
    kem_pub: bytearray
    kem_priv: bytearray
    x25519_pub: bytearray
    x25519_priv: bytearray
    key_dir: str
    journal_dir: str
    last_activity: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def is_expired(self, max_idle_seconds: float) -> bool:
        return (time.monotonic() - self.last_activity) > max_idle_seconds

    def zero_keys(self) -> None:
        """Overwrite key bytes in memory before deletion."""
        for ba in (self.kem_pub, self.kem_priv, self.x25519_pub, self.x25519_priv):
            if ba:
                ctypes.memset((ctypes.c_char * len(ba)).from_buffer(ba), 0, len(ba))

    def as_key_dict(self) -> dict:
        return {
            "kem_pub": bytes(self.kem_pub),
            "kem_priv": bytes(self.kem_priv),
            "x25519_pub": bytes(self.x25519_pub),
            "x25519_priv": bytes(self.x25519_priv),
        }


# Module-level session store — never persisted
_sessions: dict[str, SessionData] = {}
_serializer: Optional[URLSafeTimedSerializer] = None


def init_session_manager(secret_key: str) -> None:
    global _serializer
    _serializer = URLSafeTimedSerializer(secret_key, salt="pq-journal-session")


def create_session(keys: dict, key_dir: str, journal_dir: str) -> str:
    """
    Create a new session from decrypted key bytes.
    Returns a signed session token (stored in cookie).
    """
    if _serializer is None:
        raise RuntimeError("Session manager not initialized")

    session_id = _make_session_id()
    _sessions[session_id] = SessionData(
        kem_pub=bytearray(keys["kem_pub"]),
        kem_priv=bytearray(keys["kem_priv"]),
        x25519_pub=bytearray(keys["x25519_pub"]),
        x25519_priv=bytearray(keys["x25519_priv"]),
        key_dir=key_dir,
        journal_dir=journal_dir,
    )
    return _serializer.dumps(session_id)


def get_session(token: str, max_idle_seconds: float = 900) -> Optional[SessionData]:
    """
    Validate token and return session data, or None if invalid/expired.
    Touches last_activity on success.
    """
    if _serializer is None:
        return None
    try:
        session_id = _serializer.loads(token, max_age=86400)  # token valid for 24h max
    except (BadSignature, SignatureExpired):
        return None

    session = _sessions.get(session_id)
    if session is None:
        return None
    if session.is_expired(max_idle_seconds):
        destroy_session(token)
        return None
    session.touch()
    return session


def peek_session(token: str, max_idle_seconds: float = 900) -> Optional[SessionData]:
    """
    Validate token and return session data without updating last_activity.
    Use for heartbeat/ping endpoints that should not reset the idle timer.
    """
    if _serializer is None:
        return None
    try:
        session_id = _serializer.loads(token, max_age=86400)
    except (BadSignature, SignatureExpired):
        return None
    session = _sessions.get(session_id)
    if session is None:
        return None
    if session.is_expired(max_idle_seconds):
        destroy_session(token)
        return None
    return session


def destroy_session(token: str) -> None:
    """Destroy session and zero key bytes."""
    if _serializer is None:
        return
    try:
        session_id = _serializer.loads(token, max_age=86400 * 7)
    except Exception:
        # Try to find by brute-force if token is malformed but session exists
        return
    _remove_session(session_id)


def destroy_all_sessions() -> None:
    for session_id in list(_sessions.keys()):
        _remove_session(session_id)


def get_session_idle_times() -> list[tuple[str, float]]:
    """Return [(session_id_prefix, idle_seconds)] for all active sessions."""
    now = time.monotonic()
    return [(sid[:8], now - s.last_activity) for sid, s in _sessions.items()]


def sweep_expired_sessions(max_idle_seconds: float) -> int:
    """Remove expired sessions. Returns count removed."""
    expired = [sid for sid, s in _sessions.items() if s.is_expired(max_idle_seconds)]
    for sid in expired:
        _remove_session(sid)
    return len(expired)


def _remove_session(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if session:
        session.zero_keys()
    if not _sessions:
        # Last session gone — clear the DB encryption key from memory
        try:
            from app.models.db import clear_db_encryption_key
            clear_db_encryption_key()
        except Exception:
            pass


def _make_session_id() -> str:
    import secrets
    return secrets.token_hex(32)
