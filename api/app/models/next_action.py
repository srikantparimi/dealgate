"""Next action per opportunity (S19 slice 1 A5).

Data model lands in slice 1; the editable UI + audit path arrives in slice 2.
Statuses are enum-checked in the migration; keep the app-side validator a
str-in-set assertion so runtime failures produce a clear log.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


VALID_NEXT_ACTION_STATUSES: frozenset[str] = frozenset(
    {"open", "in_progress", "blocked", "complete"}
)


class NextAction(Base):
    __tablename__ = "next_action"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','in_progress','blocked','complete')",
            name="ck_next_action_status",
        ),
        Index("ix_next_action_opportunity_status", "opportunity_id", "status"),
        Index("ix_next_action_owner_due", "owner_user_id", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
