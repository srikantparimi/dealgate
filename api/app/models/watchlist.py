"""S20 W6 Session 4 · per-user watchlist for deals and clients.

A user stars a deal or a client. The star exposes:
- Command center "Watching" count (queried by kind).
- A `filter=watching` axis on the Pipeline filter bar.
- A per-row `is_watched` indicator on the row envelope.

Never sent to HubSpot — this is local governance state.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


WATCH_KINDS: frozenset[str] = frozenset({"opportunity", "client"})


class WatchedItem(Base):
    __tablename__ = "watched_item"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "kind", "item_id", name="uq_watched_item_user_kind_item"
        ),
        CheckConstraint(
            "kind in ('opportunity','client')", name="ck_watched_item_kind"
        ),
        Index("ix_watched_item_user_kind", "user_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
