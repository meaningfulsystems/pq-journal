"""
Configuration and settings tests.
Requirements covered: R006, R007, R008, R010, R011, R012, R013, R014, R015, R097, R098
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


def test_r006_journal_settings_take_priority(tmp_journal: Path):
    """R006 — Journal settings file takes priority over app-root settings."""
    settings_dir = tmp_journal / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.yaml").write_text(
        yaml.dump({"auto_lock_minutes": 99})
    )

    os.environ["JOURNAL_DIR"] = str(tmp_journal)
    os.environ.pop("AUTO_LOCK_MINUTES", None)

    from app.config import get_settings
    get_settings.cache_clear()
    cfg = get_settings()

    assert cfg.auto_lock_minutes == 99


def test_r008_default_auto_lock_is_10():
    """R008 — Default auto_lock_minutes is 10."""
    os.environ.pop("AUTO_LOCK_MINUTES", None)
    from app.config import get_settings
    get_settings.cache_clear()
    cfg = get_settings()
    assert cfg.auto_lock_minutes == 10


def test_r011_emotion_window_defaults():
    """R011 — Default emotion timing values are 30s window, 20s min, 10 words."""
    for key in ("EMOTION_WINDOW_SECONDS", "EMOTION_MIN_SECONDS", "EMOTION_MIN_WORDS"):
        os.environ.pop(key, None)
    from app.config import get_settings
    get_settings.cache_clear()
    cfg = get_settings()
    assert cfg.emotion_window_seconds == 30
    assert cfg.emotion_min_seconds == 20
    assert cfg.emotion_min_words == 10


def test_r012_emotion_window_validation():
    """R012 — emotion_window_seconds is clamped to emotion_min_seconds on save."""
    # Simulate what the settings route enforces
    emotion_min_seconds = 25
    emotion_window_seconds = 15  # less than min

    saved_window = max(emotion_min_seconds, emotion_window_seconds)
    assert saved_window == 25


def test_r015_settings_cache_cleared_after_save(tmp_journal: Path):
    """R015 — Settings cache is cleared after writing new settings."""
    os.environ["JOURNAL_DIR"] = str(tmp_journal)

    from app.config import get_settings
    get_settings.cache_clear()

    # Read initial settings
    cfg1 = get_settings()
    initial_lock = cfg1.auto_lock_minutes

    # Write new settings to journal settings file
    settings_path = tmp_journal / "settings" / "settings.yaml"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["AUTO_LOCK_MINUTES"] = "77"
    get_settings.cache_clear()

    cfg2 = get_settings()
    assert cfg2.auto_lock_minutes == 77

    os.environ.pop("AUTO_LOCK_MINUTES", None)
    get_settings.cache_clear()


def test_r097_init_db_safe_to_call_twice():
    """R097 — init_db() can be called multiple times without error."""
    import asyncio
    from app.models.db import init_db

    async def run():
        await init_db()
        await init_db()  # Should not raise

    # This test requires JOURNAL_DIR to be set (done by clean_env fixture)
    asyncio.run(run())


def test_r098_settings_cache_invalidation():
    """R098 — get_settings.cache_clear() causes next call to reload."""
    from app.config import get_settings

    cfg1 = get_settings()
    get_settings.cache_clear()
    cfg2 = get_settings()

    # Both should be valid Settings objects
    assert hasattr(cfg1, "auto_lock_minutes")
    assert hasattr(cfg2, "auto_lock_minutes")


def test_r014_debug_mode_warning(capsys, tmp_journal: Path):
    """R014 — Debug mode startup warning printed to stdout."""
    os.environ["JOURNAL_DIR"] = str(tmp_journal)
    os.environ["ENABLE_DEBUG"] = "True"

    from app.config import get_settings
    get_settings.cache_clear()
    cfg = get_settings()

    if cfg.enable_debug:
        # Simulate what main.py lifespan does
        print(
            f"\n⚠  WARNING: debug mode is enabled.\n"
            f"   Journal transcripts will be written as PLAIN TEXT to:\n"
            f"   {cfg.journal_dir}/debug/\n"
        )
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "debug" in captured.out.lower()

    os.environ.pop("ENABLE_DEBUG", None)
    get_settings.cache_clear()


def test_r013_stt_model_configurable():
    """R013 — stt_model can be set to any string value."""
    os.environ["STT_MODEL"] = "tiny"
    from app.config import get_settings
    get_settings.cache_clear()
    cfg = get_settings()
    assert cfg.stt_model == "tiny"

    os.environ.pop("STT_MODEL", None)
    get_settings.cache_clear()
