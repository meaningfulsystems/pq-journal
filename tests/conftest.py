"""
Shared pytest fixtures for PQ Journal test suite.
All tests run against in-process state — no live Ollama, STT models, or filesystem
changes outside of tmp_path. Tests that require running services are marked with
appropriate pytest marks and can be skipped in CI.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

# ── Path helpers ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def tmp_journal(tmp_path: Path) -> Path:
    """Create a temporary journal directory with required subdirs."""
    journal = tmp_path / "journal"
    journal.mkdir()
    (journal / "entries").mkdir()
    (journal / ".db").mkdir()
    (journal / "settings").mkdir()
    return journal


@pytest.fixture
def tmp_key_dir(tmp_path: Path) -> Path:
    """Create a temporary key directory."""
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    return key_dir


# ── Settings / Environment ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_env(tmp_journal: Path):
    """
    Ensure JOURNAL_DIR is set to tmp_journal for each test, and settings cache
    is cleared before and after each test to prevent state leakage.
    """
    old = os.environ.get("JOURNAL_DIR")
    os.environ["JOURNAL_DIR"] = str(tmp_journal)

    # Clear any cached settings
    try:
        from app.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass

    yield

    if old is None:
        os.environ.pop("JOURNAL_DIR", None)
    else:
        os.environ["JOURNAL_DIR"] = old

    try:
        from app.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass


# ── Crypto fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def key_pair() -> dict:
    """
    Generate a fresh ML-KEM-1024 + X25519 keypair for crypto tests.
    Requires liboqs to be installed; test is skipped otherwise.
    """
    try:
        from app.services.key_store import generate_and_save_keys
    except ImportError:
        pytest.skip("liboqs not available")
    return None  # keys are generated inside individual tests using the fixture below


@pytest.fixture
def generated_keys(tmp_key_dir: Path) -> tuple[dict, Path, str]:
    """
    Generate keys and save to tmp_key_dir. Returns (meta, key_dir, passphrase).
    """
    try:
        from app.services.key_store import generate_and_save_keys, load_keys
    except ImportError:
        pytest.skip("liboqs not available")

    passphrase = "test-passphrase-secure"
    meta = generate_and_save_keys(str(tmp_key_dir), passphrase)
    return meta, tmp_key_dir, passphrase


# ── Session fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def session_manager():
    """Initialize the session manager with a test secret key."""
    from app.services import session as session_svc
    session_svc.init_session_manager("test-secret-key-32-characters-long!")
    yield session_svc
    session_svc.destroy_all_sessions()


@pytest.fixture
def mock_session(session_manager, tmp_journal: Path, tmp_key_dir: Path):
    """
    Create a mock session with fake (non-functional) key bytes.
    Suitable for testing routes that only check session existence.
    """
    from app.services import session as session_svc

    fake_keys = {
        "kem_pub": b"\x00" * 1568,
        "kem_priv": b"\x01" * 2400,
        "x25519_pub": b"\x02" * 32,
        "x25519_priv": b"\x03" * 32,
    }
    token = session_svc.create_session(
        fake_keys,
        key_dir=str(tmp_key_dir),
        journal_dir=str(tmp_journal),
    )
    return token


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(mock_session: str) -> AsyncGenerator[AsyncClient, None]:
    """
    Async test client with an authenticated session cookie.
    Database is initialized with tmp_journal.
    """
    from app.models.db import init_db
    from app.main import app

    await init_db()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        ac.cookies.set("pqj_session", mock_session)
        yield ac


@pytest_asyncio.fixture
async def anon_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client without any session cookie."""
    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# ── Markers ───────────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "requires_ollama: test requires running Ollama instance")
    config.addinivalue_line("markers", "requires_whisper: test requires faster-whisper installed")
    config.addinivalue_line("markers", "requires_hf: test requires HuggingFace transformers installed")
    config.addinivalue_line("markers", "requires_liboqs: test requires liboqs installed")
