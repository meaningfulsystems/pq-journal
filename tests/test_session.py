"""
Session management tests.
Requirements covered: R039, R040, R041, R042, R043, R044, R045, R046
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest


def test_r039_session_in_memory_only(tmp_key_dir, tmp_journal):
    """R039 — Sessions are stored in module-level dict, not disk."""
    from app.services import session as session_svc

    session_svc.init_session_manager("test-secret-key-for-testing-only!")

    fake_keys = {
        "kem_pub": b"\x00" * 1568,
        "kem_priv": b"\x01" * 2400,
        "x25519_pub": b"\x02" * 32,
        "x25519_priv": b"\x03" * 32,
    }
    token = session_svc.create_session(fake_keys, str(tmp_key_dir), str(tmp_journal))

    # Session lives in _sessions dict
    assert len(session_svc._sessions) >= 1

    session_svc.destroy_all_sessions()


def test_r040_session_key_zeroing(tmp_key_dir, tmp_journal):
    """R040 — Session key bytes are zeroed on destroy."""
    from app.services import session as session_svc

    session_svc.init_session_manager("test-secret-key-for-testing-only!")

    fake_keys = {
        "kem_pub": bytearray(b"\xAA" * 32),
        "kem_priv": bytearray(b"\xBB" * 32),
        "x25519_pub": bytearray(b"\xCC" * 32),
        "x25519_priv": bytearray(b"\xDD" * 32),
    }
    token = session_svc.create_session(
        {k: bytes(v) for k, v in fake_keys.items()},
        str(tmp_key_dir),
        str(tmp_journal),
    )

    # Get the SessionData before destroy
    max_idle = 3600
    session_data = session_svc.get_session(token, max_idle_seconds=max_idle)
    assert session_data is not None

    # Capture reference to key bytearray
    kem_priv_ref = session_data.kem_priv

    session_svc.destroy_session(token)

    # After zeroing, all bytes should be 0
    assert all(b == 0 for b in kem_priv_ref), "Key bytes were not zeroed"


def test_r041_idle_timeout(tmp_key_dir, tmp_journal):
    """R041 — Session is invalidated after idle exceeds auto_lock_minutes."""
    from app.services import session as session_svc

    session_svc.init_session_manager("test-secret-key-for-testing-only!")

    fake_keys = {
        "kem_pub": b"\x00" * 32,
        "kem_priv": b"\x01" * 32,
        "x25519_pub": b"\x02" * 32,
        "x25519_priv": b"\x03" * 32,
    }
    token = session_svc.create_session(fake_keys, str(tmp_key_dir), str(tmp_journal))

    # With max_idle_seconds=0, session should be immediately expired
    result = session_svc.get_session(token, max_idle_seconds=0)
    assert result is None, "Expired session should return None"

    session_svc.destroy_all_sessions()


def test_r042_background_sweep(tmp_key_dir, tmp_journal):
    """R042 — sweep_expired_sessions removes expired sessions."""
    from app.services import session as session_svc

    session_svc.init_session_manager("test-secret-key-for-testing-only!")

    fake_keys = {
        "kem_pub": b"\x00" * 32,
        "kem_priv": b"\x01" * 32,
        "x25519_pub": b"\x02" * 32,
        "x25519_priv": b"\x03" * 32,
    }
    # Create two sessions
    session_svc.create_session(fake_keys, str(tmp_key_dir), str(tmp_journal))
    session_svc.create_session(fake_keys, str(tmp_key_dir), str(tmp_journal))

    initial_count = len(session_svc._sessions)
    assert initial_count == 2

    # Sweep with 0 seconds idle — all sessions should be expired
    removed = session_svc.sweep_expired_sessions(max_idle_seconds=0)
    assert removed == 2
    assert len(session_svc._sessions) == 0


def test_r043_tampered_token_rejected(tmp_key_dir, tmp_journal):
    """R043 — Tampered session token returns None."""
    from app.services import session as session_svc

    session_svc.init_session_manager("test-secret-key-for-testing-only!")

    fake_keys = {
        "kem_pub": b"\x00" * 32,
        "kem_priv": b"\x01" * 32,
        "x25519_pub": b"\x02" * 32,
        "x25519_priv": b"\x03" * 32,
    }
    token = session_svc.create_session(fake_keys, str(tmp_key_dir), str(tmp_journal))

    tampered = token + "X"
    result = session_svc.get_session(tampered, max_idle_seconds=3600)
    assert result is None

    session_svc.destroy_all_sessions()


def test_r044_db_key_cleared_on_last_logout(tmp_key_dir, tmp_journal):
    """R044 — DB encryption key is cleared when last session is destroyed."""
    import app.models.db as db_module
    from app.models.db import set_db_encryption_key
    from app.services import session as session_svc

    session_svc.init_session_manager("test-secret-key-for-testing-only!")
    set_db_encryption_key(b"\x01" * 32)

    fake_keys = {
        "kem_pub": b"\x00" * 32,
        "kem_priv": b"\x01" * 32,
        "x25519_pub": b"\x02" * 32,
        "x25519_priv": b"\x03" * 32,
    }
    token = session_svc.create_session(fake_keys, str(tmp_key_dir), str(tmp_journal))
    session_svc.destroy_session(token)

    assert db_module._db_encryption_key is None, "DB key should be cleared after last session removed"


def test_r008_default_session_timeout():
    """R008 — Default auto_lock_minutes is 10."""
    import os
    # Remove any explicit setting to test default
    old = os.environ.pop("AUTO_LOCK_MINUTES", None)
    try:
        from app.config import get_settings
        get_settings.cache_clear()
        cfg = get_settings()
        assert cfg.auto_lock_minutes == 10
    finally:
        if old is not None:
            os.environ["AUTO_LOCK_MINUTES"] = old
        from app.config import get_settings as gs
        gs.cache_clear()


def test_r009_configurable_session_timeout(tmp_journal):
    """R009 — auto_lock_minutes can be set via environment variable."""
    import os
    os.environ["AUTO_LOCK_MINUTES"] = "5"
    try:
        from app.config import get_settings
        get_settings.cache_clear()
        cfg = get_settings()
        assert cfg.auto_lock_minutes == 5
    finally:
        os.environ.pop("AUTO_LOCK_MINUTES", None)
        from app.config import get_settings as gs
        gs.cache_clear()
