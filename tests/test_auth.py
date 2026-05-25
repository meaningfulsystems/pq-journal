"""
Authentication route tests.
Requirements covered: R004, R005, R017, R018, R019, R020, R021, R023, R024,
                      R025, R027, R086, R087, R092
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_r004_startup_without_journal_path(anon_client: AsyncClient):
    """R004 — App starts and serves /unlock without pre-configured journal path."""
    response = await anon_client.get("/unlock")
    assert response.status_code == 200
    assert "Journal Directory" in response.text


@pytest.mark.asyncio
async def test_r005_404_no_stack_trace(anon_client: AsyncClient):
    """R005 — 404 response is a clean HTML page without stack traces."""
    response = await anon_client.get("/nonexistent-route-xyz")
    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "File " not in response.text


@pytest.mark.asyncio
async def test_r025_root_unauthenticated_redirects_to_unlock(anon_client: AsyncClient):
    """R025 — GET / redirects unauthenticated user to /unlock."""
    response = await anon_client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/unlock" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_r025_root_authenticated_redirects_to_journal(client: AsyncClient):
    """R025 — GET / redirects authenticated user to /journal."""
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/journal" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_r017_passphrase_too_short(anon_client: AsyncClient, tmp_key_dir, tmp_journal):
    """R017 — Setup rejects passphrases shorter than 12 characters."""
    response = await anon_client.post(
        "/setup/generate",
        data={
            "key_dir": str(tmp_key_dir),
            "journal_dir": str(tmp_journal),
            "passphrase": "short",
            "passphrase_confirm": "short",
        },
    )
    assert response.status_code == 200
    assert "12" in response.text or "characters" in response.text.lower()


@pytest.mark.asyncio
async def test_r018_passphrase_mismatch(anon_client: AsyncClient, tmp_key_dir, tmp_journal):
    """R018 — Setup rejects mismatched passphrases."""
    response = await anon_client.post(
        "/setup/generate",
        data={
            "key_dir": str(tmp_key_dir),
            "journal_dir": str(tmp_journal),
            "passphrase": "long-enough-passphrase",
            "passphrase_confirm": "different-passphrase",
        },
    )
    assert response.status_code == 200
    assert "match" in response.text.lower()


@pytest.mark.asyncio
async def test_r019_unlock_requires_journal_dir(anon_client: AsyncClient, tmp_key_dir):
    """R019 — Unlock rejects request with blank journal_dir."""
    response = await anon_client.post(
        "/unlock",
        data={
            "journal_dir": "",
            "key_dir": str(tmp_key_dir),
            "passphrase": "some-passphrase",
        },
    )
    # Should return error (422 from FastAPI or 400 from route handler)
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_r020_unlock_empty_key_dir_error(anon_client: AsyncClient, tmp_key_dir, tmp_journal):
    """R020 — Unlock returns error when no key files found."""
    response = await anon_client.post(
        "/unlock",
        data={
            "journal_dir": str(tmp_journal),
            "key_dir": str(tmp_key_dir),  # empty dir
            "passphrase": "test-passphrase",
        },
    )
    assert response.status_code == 400
    assert "No key files" in response.text


@pytest.mark.asyncio
async def test_r023_session_cookie_attributes(anon_client: AsyncClient, tmp_key_dir, tmp_journal):
    """R023 — Successful unlock sets HttpOnly, SameSite=Strict cookie with 24h max-age."""
    from unittest.mock import patch

    # Mock key loading to simulate successful auth
    fake_keys = {
        "kem_pub": b"\x00" * 1568,
        "kem_priv": b"\x01" * 2400,
        "x25519_pub": b"\x02" * 32,
        "x25519_priv": b"\x03" * 32,
    }

    with patch("app.routes.auth.key_dir_has_keys", return_value=True), \
         patch("app.routes.auth.load_keys", return_value=fake_keys), \
         patch("app.routes.auth.init_db"):
        response = await anon_client.post(
            "/unlock",
            data={
                "journal_dir": str(tmp_journal),
                "key_dir": str(tmp_key_dir),
                "passphrase": "test-passphrase",
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    cookie_header = response.headers.get("set-cookie", "")
    assert "pqj_session" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=strict" in cookie_header.lower()
    assert "max-age=86400" in cookie_header.lower()


@pytest.mark.asyncio
async def test_r024_lock_clears_session(client: AsyncClient):
    """R024 — POST /lock destroys session and deletes cookie."""
    response = await client.post("/lock", follow_redirects=False)
    assert response.status_code == 302
    assert "/unlock" in response.headers.get("location", "")

    # After lock, cookie should be cleared
    cookie_header = response.headers.get("set-cookie", "")
    assert "pqj_session" in cookie_header
    # Max-age=0 or explicit delete sets to empty
    assert "max-age=0" in cookie_header.lower() or '=""' in cookie_header


@pytest.mark.asyncio
async def test_r086_no_swagger_ui(anon_client: AsyncClient):
    """R086 — Swagger UI is disabled."""
    response = await anon_client.get("/docs")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_r086_no_redoc(anon_client: AsyncClient):
    """R086 — ReDoc is disabled."""
    response = await anon_client.get("/redoc")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_r087_journal_routes_require_auth(anon_client: AsyncClient):
    """R087 — Journal routes require authentication."""
    protected_routes = ["/journal", "/settings", "/journal/new"]
    for route in protected_routes:
        response = await anon_client.get(route, follow_redirects=False)
        assert response.status_code in (302, 401), f"{route} should require auth"
        if response.status_code == 302:
            assert "/unlock" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_r092_debug_default_off():
    """R092 — enable_debug defaults to False."""
    import os
    old = os.environ.pop("ENABLE_DEBUG", None)
    try:
        from app.config import get_settings
        get_settings.cache_clear()
        cfg = get_settings()
        assert cfg.enable_debug is False
    finally:
        if old is not None:
            os.environ["ENABLE_DEBUG"] = old
        from app.config import get_settings as gs
        gs.cache_clear()


@pytest.mark.asyncio
async def test_r027_setup_default_journal_path(anon_client: AsyncClient):
    """R027 — Setup page pre-populates journal dir with ~/MeaningfulJournal."""
    from pathlib import Path
    response = await anon_client.get("/setup")
    assert response.status_code == 200
    assert "MeaningfulJournal" in response.text
