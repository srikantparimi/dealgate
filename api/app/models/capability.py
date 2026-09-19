"""`capability_catalog` — curated list of DealGate delivery capabilities.

Delivery Lead / SystemAdmin can add and edit entries; every other
governance role reads. Rows are mutable (curator can refine the
description or tags), and a description edit triggers a re-embed via the
router so vector search stays consistent with the human-authored text.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator, Uuid

from app.db.base import Base
from app.db.vector import Vector


class StringArray(TypeDecorator):  # type: ignore[type-arg]
    """Postgres ``TEXT[]`` on real DB, JSON list on SQLite.

    Matches the `tags TEXT[]` acceptance contract while keeping the
    SQLite-backed test path working.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String()))
        return dialect.type_descriptor(JSON())


class CapabilityCatalog(Base):
    __tablename__ = "capability_catalog"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    curated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
