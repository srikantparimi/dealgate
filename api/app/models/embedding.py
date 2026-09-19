"""`sow_embedding` — one row per ~500-char chunk of a confirmed SOW.

The vector column is `VECTOR(1536)` on Postgres (via pgvector) and a
portable JSON string on SQLite so tests can round-trip the shape without
needing the extension. See migration 0023 for the DDL split and
:mod:`app.services.embeddings` for the read/write API.

Rule 4 (CLAUDE.md): rows are immutable — a re-embed of the same
(sow_version_id, chunk_index) is idempotent, achieved via the unique
constraint and an upsert-friendly service that skips existing rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.db.vector import Vector


class SowEmbedding(Base):
    __tablename__ = "sow_embedding"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sow_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sow_version.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Postgres: pgvector VECTOR(1536); SQLite: JSON-serialised list[float].
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "sow_version_id", "chunk_index", name="uq_sow_embedding_version_chunk"
        ),
    )
