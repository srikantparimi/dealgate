"""Saved views (S20 · W6).

Seven built-in views seeded at first login per user:

- ``my_opportunities``  — deals owned by (or assigned to) the caller.
- ``my_actions``        — deals with an open next-action assigned to me.
- ``waiting_on_others`` — deals where my open next-action is blocked.
- ``closing_soon``      — deals with close_date in the next 30 days.
- ``no_next_action``    — deals with no open next-action row.
- ``stale_contact``     — deals with no last_activity_at in 30 days.
- ``my_approvals``      — deals with an open approval assigned to me.

Users can add additional views by ``POST /saved-views`` — same shape,
``key`` becomes ``custom`` and ``name`` is user-supplied.

Visibility mirrors ``tracking_group.visibility``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


BUILTIN_VIEW_KEYS: tuple[str, ...] = (
    "my_opportunities",
    "my_actions",
    "waiting_on_others",
    "closing_soon",
    "no_next_action",
    "stale_contact",
    "my_approvals",
)

VALID_VIEW_VISIBILITIES: frozenset[str] = frozenset({"private", "team"})


class SavedView(Base):
    __tablename__ = "saved_view"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private','team')",
            name="ck_saved_view_visibility",
        ),
        # A user cannot end up with two built-ins of the same key. Custom
        # views have key='custom' and are not deduplicated.
        UniqueConstraint(
            "owner_id",
            "key",
            "is_builtin",
            name="uq_saved_view_owner_key_builtin",
        ),
        Index("ix_saved_view_owner", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    # For built-ins this is the built-in key; for user-defined views
    # this is ``custom``.
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    filter_json: Mapped[dict[str, Any]] = mapped_column(
        JsonB, nullable=False, default=dict
    )
    sort_json: Mapped[dict[str, Any] | None] = mapped_column(JsonB, nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private"
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
