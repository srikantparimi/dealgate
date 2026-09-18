"""Notification outbox + per-user delivery settings (S2-E3).

Two tables:

- `notification` — the transactional outbox. One row per (user, channel) that
  a `queue_notification` call fans out to. The worker (Agent N) drains rows in
  status ``pending`` and marks them ``sent`` / ``failed`` / ``suppressed``.
- `notification_setting` — per user, per category, per channel opt-in flag.
  Missing rows default to enabled at the service layer so brand new users
  receive everything until they opt out.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_md: Mapped[str] = mapped_column(String(4000), nullable=False)
    related_entity: Mapped[str | None] = mapped_column(String(64))
    related_entity_id: Mapped[str | None] = mapped_column(String(128))
    # Values: pending | sent | failed | suppressed.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    # In-app read receipt. Only meaningful when channel = 'inapp'.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationSetting(Base):
    __tablename__ = "notification_setting"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "category",
            "channel",
            name="uq_notification_setting_user_category_channel",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
