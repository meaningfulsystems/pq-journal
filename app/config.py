from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core paths — journal_dir is set via JOURNAL_DIR env var at login time
    journal_dir: Path = Path.home() / "MeaningfulJournal"

    # Security
    secret_key: str = ""  # Auto-generated at startup if not set via env var
    auto_lock_minutes: int = 10

    # STT
    stt_model: str = "large-v3-turbo"  # faster-whisper model name
    vosk_model_dir: Optional[Path] = None

    # LLM (Ollama)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    # Emotion summary timing
    emotion_window_seconds: int = 30   # recurring interval between live summaries
    emotion_min_seconds: int = 20      # floor — never fire faster than this
    emotion_min_words: int = 10        # skip LLM call if transcript has fewer words

    # Features
    enable_webcam: bool = False
    enable_debug: bool = False

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def entries_dir(self) -> Path:
        return self.journal_dir / "entries"

    @property
    def db_path(self) -> Path:
        return self.journal_dir / ".db" / "journal.sqlite"

    @property
    def settings_path(self) -> Path:
        """Where journal-specific settings are persisted."""
        return self.journal_dir / "settings" / "settings.yaml"

    @property
    def prompts_path(self) -> Path:
        user_prompts = self.journal_dir / "prompts.yaml"
        if user_prompts.exists():
            return user_prompts
        return Path(__file__).parent.parent / "data" / "prompts.yaml"

    @property
    def emotion_matrix_path(self) -> Path:
        return Path(__file__).parent.parent / "data" / "emotion_matrix.json"


def _load_yaml_settings() -> dict:
    """
    Load settings YAML. Journal-specific settings (in {journal_dir}/settings/settings.yaml)
    take priority over the app-root settings.yaml fallback. No path information is stored
    in the app root — journal_dir is always provided at login.
    """
    candidates = []

    # Journal-specific settings (highest priority — only available after login)
    journal_dir_env = os.environ.get("JOURNAL_DIR")
    if journal_dir_env:
        candidates.append(Path(journal_dir_env) / "settings" / "settings.yaml")

    # App-root fallback (non-sensitive startup settings: ollama_url, stt_model, etc.)
    candidates.extend([
        Path("settings.yaml"),
        Path.home() / ".pq-journal" / "settings.yaml",
    ])

    for candidate in candidates:
        if candidate.exists():
            try:
                with open(candidate) as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
    return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    yaml_data = _load_yaml_settings()
    # Env vars override YAML; YAML overrides defaults
    for k, v in yaml_data.items():
        if k.upper() not in os.environ:
            os.environ[k.upper()] = str(v)
    settings = Settings()
    if not settings.secret_key:
        # Generate a random key for this process run — not persistent across restarts
        import secrets
        settings.secret_key = secrets.token_hex(32)
        # Key is ephemeral — sessions invalidate on restart, which is intentional
    return settings
