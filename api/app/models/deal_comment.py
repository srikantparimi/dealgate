"""Deal comments (S20 · W6).

Two sources feed this table:

- ``internal`` — comments written from DealGate through the API. These
  are the ones a user can create, edit, pin or unpin, and delete
  (soft-delete via ``deleted_at``).
- ``hubspot_note`` — a mirror of HubSpot notes attached to the deal.
  W1 writes these during the intake sync (see ``services/hubspot_sync``);
  W6 provides the read surface only. Editing a ``hubspot_note`` row is
  refused at the service layer with 409.

Pinning is a boolean; W6 accepts at most a small number of pinned
comments per deal but does not enforce a cap in the schema — the UI
surfaces the newest pinned entry.

Latest comment surfacing
------------------------
W2's list surfaces need "latest visible comment + author + time"
alongside the deal row. The service exposes ``latest_visible_comment``
that skips soft-deleted rows and respects the caller's read
permissions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


VALID_COMMENT_SOURCES: frozenset[str] = frozenset({"internal", "hubspot_note"})


class DealComment(Base):
    __tablename__ = "deal_comment"
    __table_args__ = (
        CheckConstraint(
            "source IN ('internal','hubspot_note')",
            name="ck_deal_comment_source",
        ),
        Index("ix_deal_comment_opportunity_created", "opportunity_id", "created_at"),
        Index("ix_deal_comment_pinned", "opportunity_id", "pinned"),
        Index("ix_deal_comment_hubspot_note", "hubspot_note_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    # HubSpot notes carry an author name we cannot resolve locally.
    author_name_fallback: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="internal"
    )
    # HubSpot Note engagement id — only set when source='hubspot_note'.
    # Unique so W1's sync stays idempotent.
    hubspot_note_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Soft-delete: keep the row for history but drop it from the
    # latest-comment surface. Only internal comments can be deleted.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
