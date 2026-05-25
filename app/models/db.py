from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import String, Integer, Text, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── DB-level field encryption ─────────────────────────────────────────────────
# Key is set at unlock time and cleared on lock. Never persisted.

_db_encryption_key: Optional[bytes] = None


def derive_db_key(kem_priv: bytes, x25519_priv: bytes) -> bytes:
    """Derive a stable 32-byte AES key from the session private keys."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"pq-journal-db-v1",
    ).derive(kem_priv + x25519_priv)


def set_db_encryption_key(key: bytes) -> None:
    global _db_encryption_key
    _db_encryption_key = key


def clear_db_encryption_key() -> None:
    global _db_encryption_key
    _db_encryption_key = None


class EncryptedText(TypeDecorator):
    """
    Transparent AES-256-GCM encryption for SQLAlchemy Text columns.
    Encrypted value stored as base64(12-byte nonce || ciphertext || 16-byte tag).
    Falls back to returning raw value for legacy plaintext rows.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if _db_encryption_key is None:
            raise RuntimeError("DB encryption key not set — unlock first")
        nonce = os.urandom(12)
        ct_with_tag = AESGCM(_db_encryption_key).encrypt(nonce, value.encode("utf-8"), None)
        return base64.b64encode(nonce + ct_with_tag).decode("ascii")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if _db_encryption_key is None:
            return None
        try:
            raw = base64.b64decode(value)
            if len(raw) < 29:          # 12 nonce + 1 byte min ct + 16 tag
                return value           # legacy plaintext — return as-is
            nonce, ct_with_tag = raw[:12], raw[12:]
            return AESGCM(_db_encryption_key).decrypt(nonce, ct_with_tag, None).decode("utf-8")
        except Exception:
            return value               # legacy plaintext fallback

_engine = None
_session_factory = None


class Base(DeclarativeBase):
    pass


class JournalEntry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(EncryptedText, nullable=False, default="Untitled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tags: Mapped[str] = mapped_column(EncryptedText, nullable=False, default="[]")
    emotion_label: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    emotion_scores: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)  # UUID — not sensitive
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def tags_list(self) -> list[str]:
        try:
            return json.loads(self.tags)
        except Exception:
            return []

    @property
    def emotion_scores_dict(self) -> dict:
        try:
            return json.loads(self.emotion_scores) if self.emotion_scores else {}
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "tags": self.tags_list,
            "emotion_label": self.emotion_label,
            "emotion_scores": self.emotion_scores_dict,
            "file_name": self.file_name,
            "word_count": self.word_count,
        }


async def init_db() -> None:
    """Create tables and ensure the database directory exists. Safe to call on each login."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()

    settings = get_settings()
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session
