from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core paths
    journal_dir: Path = Path.home() / "MeaningfulJournal"
    key_dir: Optional[Path] = None  # Set at unlock time via session; fallback from settings

    # Security
    secret_key: str = ""  # Must be set in .env
    auto_lock_minutes: int = 15

    # STT
    stt_model: str = "large-v3-turbo"  # faster-whisper model name
    vosk_model_dir: Optional[Path] = None

    # LLM (Ollama)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    # Features
    enable_webcam: bool = False

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def entries_dir(self) -> Path:
        return self.journal_dir / "entries"

    @property
    def db_path(self) -> Path:
        return self.journal_dir / ".db" / "journal.sqlite"

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
    for candidate in [Path("settings.yaml"), Path.home() / ".pq-journal" / "settings.yaml"]:
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
        # Production: set SECRET_KEY in .env
        import secrets
        settings.secret_key = secrets.token_hex(32)
    return settings
