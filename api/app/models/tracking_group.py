"""Tracking groups + members (S20 · W6).

Manual watchlists and dynamic groups derived from saved filters. Both
share the same table: ``filter_json`` present → dynamic; NULL →
manual. Manual groups store their membership in
``tracking_group_member``; dynamic groups compute membership on read
against the same filter contract W2 uses in the pipeline query
(``contracts.md`` §4).

Visibility
----------
- ``private`` — only the owner can see or modify.
- ``team``    — every user can list and read, but only the owner can
  edit or delete. (S20 does not add a fine-grained grant table; team
  visibility means "everyone with access to /pipeline can see it".)

Member kind
-----------
- ``client``      — members are ``client.id`` uuids.
- ``opportunity`` — members are ``opportunity.id`` uuids.

Both kinds filter the same ``/pipeline`` base query — the service
converts the members (manual) or the filter (dynamic) into predicates
in the same shape W2 already consumes.
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
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


VALID_GROUP_VISIBILITIES: frozenset[str] = frozenset({"private", "team"})
VALID_GROUP_MEMBER_KINDS: frozenset[str] = frozenset({"client", "opportunity"})


class TrackingGroup(Base):
    __tablename__ = "tracking_group"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private','team')",
            name="ck_tracking_group_visibility",
        ),
        CheckConstraint(
            "member_kind IN ('client','opportunity')",
            name="ck_tracking_group_member_kind",
        ),
        Index("ix_tracking_group_owner", "owner_id"),
        Index("ix_tracking_group_visibility", "visibility"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private"
    )
    member_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Presence = dynamic; NULL = manual. Filter shape matches contracts §4.
    filter_json: Mapped[dict[str, Any] | None] = mapped_column(JsonB, nullable=True)
    # Client-kind dynamic groups may opt to include future deals of a
    # membership client (review §"Groups and saved views").
    include_future_deals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
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
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TrackingGroupMember(Base):
    """Manual-group membership row.

    Dynamic groups leave this table empty and rely on
    ``TrackingGroup.filter_json`` to derive membership on read.
    """

    __tablename__ = "tracking_group_member"
    __table_args__ = (
        PrimaryKeyConstraint("group_id", "member_id", name="pk_tracking_group_member"),
        Index("ix_tracking_group_member_group", "group_id"),
        Index("ix_tracking_group_member_member", "member_id"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tracking_group.id", ondelete="CASCADE"), nullable=False
    )
    # Untyped uuid: interpret against ``TrackingGroup.member_kind``.
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
