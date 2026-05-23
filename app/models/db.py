from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlalchemy import String, Integer, Text, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

_engine = None
_session_factory = None


class Base(DeclarativeBase):
    pass


class JournalEntry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="Untitled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    emotion_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emotion_scores: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict
    file_name: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. "<uuid>.pqj"
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
    """Create tables and ensure the database directory exists."""
    global _engine, _session_factory
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
