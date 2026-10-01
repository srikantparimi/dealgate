"""Next action per opportunity (S19 slice 1 A5, extended for S20 · W6).

S19 landed the core columns. S20 · W6 promotes ``next_action`` to a
structured task in line with the review's §"Actions and comments":
title, assignee, due, status, blocker, outcome, plus an append-only
history table ``next_action_event`` that captures every transition with
actor + timestamp + before/after payload.

Backwards compat notes
----------------------
- ``description`` stays for existing rows and clients (S19 slice 1 seed
  is still readable). New rows should populate ``title`` — the service
  layer mirrors ``title`` into ``description`` on create so the old
  Pipeline aggregate SQL (``_next_action_open_count_subq`` etc.) keeps
  working without a join to a new column.
- ``owner_user_id`` was the pre-S20 assignee. ``assignee_user_id`` is
  the new canonical column; the service falls back to
  ``owner_user_id`` when the row was written by pre-S20 code so
  existing pipeline queries do not need to change.
- ``approval_package_id`` (nullable) ties an action to an approval
  package. Completing a next-action linked to an approval package is
  refused by the service with 409 pointing at the approval endpoint
  (T16 requirement).

Statuses are enum-checked in the migration; keep the app-side validator
a str-in-set assertion so runtime failures produce a clear log.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


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
        Index("ix_next_action_assignee_due", "assignee_user_id", "due_date"),
        Index("ix_next_action_approval_package", "approval_package_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False
    )
    # S19: description was the free-text body. S20: kept for backcompat, but
    # ``title`` is the field new callers write. The service mirrors
    # ``title`` → ``description`` on create.
    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # S19 name; still populated by the service so the pipeline aggregate
    # SQL keeps working. New code reads ``assignee_user_id`` first.
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    blocker: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    # S20 · W6 · T16: linking a next-action to an approval package makes
    # completion route through the approval decision, not this task.
    approval_package_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_package.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NextActionEvent(Base):
    """Append-only history of every next-action transition.

    Every service call that mutates a ``NextAction`` writes exactly one
    row here in the same transaction, so the field-level history matches
    the ``audit_event`` chain but is queryable per action without
    scanning the whole chain.
    """

    __tablename__ = "next_action_event"
    __table_args__ = (
        Index("ix_next_action_event_action_ts", "next_action_id", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    next_action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("next_action.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # One of: 'created', 'status_change', 'reassigned', 'edited',
    # 'blocker_set', 'blocker_cleared', 'outcome_set'.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonB, nullable=True)
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
