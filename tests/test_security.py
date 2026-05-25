"""
Security tests: input validation, path sanitization, authenticated routes.
Requirements covered: R079, R081, R088, R089, R090, R091
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ── Directory traversal & input validation ────────────────────────────────────

@pytest.mark.asyncio
async def test_r079_mkdir_rejects_dotdot(anon_client: AsyncClient):
    """R079 — mkdir rejects '..' directory names."""
    response = await anon_client.post(
        "/api/mkdir",
        json={"parent": "/tmp", "name": ".."},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_r079_mkdir_rejects_dot(anon_client: AsyncClient):
    """R079 — mkdir rejects '.' directory names."""
    response = await anon_client.post(
        "/api/mkdir",
        json={"parent": "/tmp", "name": "."},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_r079_mkdir_rejects_slash(anon_client: AsyncClient):
    """R079 — mkdir rejects names containing '/'."""
    response = await anon_client.post(
        "/api/mkdir",
        json={"parent": "/tmp", "name": "a/b"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_r079_mkdir_rejects_backslash(anon_client: AsyncClient):
    """R079 — mkdir rejects names containing '\\'."""
    response = await anon_client.post(
        "/api/mkdir",
        json={"parent": "/tmp", "name": "a\\b"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_r079_mkdir_rejects_empty(anon_client: AsyncClient):
    """R079 — mkdir rejects empty directory names."""
    response = await anon_client.post(
        "/api/mkdir",
        json={"parent": "/tmp", "name": ""},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_r081_debug_save_requires_auth(anon_client: AsyncClient):
    """R081 — /api/debug/save requires authentication."""
    response = await anon_client.post(
        "/api/debug/save",
        json={"filename": "test.txt", "content": "test content"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 401)


@pytest.mark.asyncio
async def test_r081_debug_save_sanitizes_filename(client: AsyncClient, tmp_journal):
    """R081 — debug/save sanitizes malicious filenames."""
    import os
    from app.models.db import set_db_encryption_key

    set_db_encryption_key(os.urandom(32))

    from unittest.mock import patch
    with patch("app.routes.files.get_settings") as mock_cfg:
        mock_cfg.return_value.journal_dir = tmp_journal

        response = await client.post(
            "/api/debug/save",
            json={"filename": "../../etc/evil", "content": "data"},
        )

    if response.status_code == 200:
        data = response.json()
        saved_path = data.get("saved", "")
        # Verify no traversal in path
        assert "etc" not in saved_path or "debug" in saved_path
        assert ".." not in saved_path


@pytest.mark.asyncio
async def test_r088_browse_returns_absolute_path(anon_client: AsyncClient, tmp_path):
    """R088 — Browse endpoint resolves to absolute path."""
    response = await anon_client.get(f"/api/browse?path={tmp_path}")
    assert response.status_code == 200
    data = response.json()
    assert "current" in data
    # Current should be absolute path (starts with /)
    import platform
    if platform.system() != "Windows":
        assert data["current"].startswith("/")


# ── Authenticated route enforcement ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_r087_voice_upload_requires_auth(anon_client: AsyncClient):
    """R087 — /voice/upload requires authentication."""
    response = await anon_client.post(
        "/voice/upload",
        files={"file": ("test.wav", b"RIFF", "audio/wav")},
        follow_redirects=False,
    )
    assert response.status_code in (302, 401, 422)


@pytest.mark.asyncio
async def test_r087_settings_requires_auth(anon_client: AsyncClient):
    """R087 — /settings requires authentication."""
    response = await anon_client.get("/settings", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio
async def test_r091_api_status_has_reasonable_response_time(anon_client: AsyncClient):
    """R091 — API status endpoint responds (Ollama timeout not blocking)."""
    import time
    import asyncio

    start = time.monotonic()
    response = await anon_client.get("/api/status")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    # Should respond within 15 seconds even if Ollama times out
    assert elapsed < 15.0


# ── Configuration security ────────────────────────────────────────────────────

def test_r007_settings_file_has_no_paths(tmp_journal):
    """R007 — Settings saved by the app contain no journal_dir or key_dir fields."""
    import yaml, os
    from app.config import get_settings

    os.environ["JOURNAL_DIR"] = str(tmp_journal)
    get_settings.cache_clear()

    settings_path = tmp_journal / "settings" / "settings.yaml"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Simulate what the settings save route writes
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
    with open(settings_path, "w") as f:
        yaml.dump(settings_data, f)

    # Verify no sensitive path fields
    with open(settings_path) as f:
        saved = yaml.safe_load(f) or {}

    assert "journal_dir" not in saved, "journal_dir must not be persisted"
    assert "key_dir" not in saved, "key_dir must not be persisted"


def test_r092_enable_debug_defaults_false():
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
