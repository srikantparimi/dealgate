"""Per-user UI preferences (S19 slice 1 A7).

Slice 1 uses `pipeline.view` to remember the Clients-vs-Opportunities
toggle. Key/value stays generic so slice 2's group-tab pins and slice 3
adds don't need another migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base

JsonB = JSON().with_variant(JSONB(), "postgresql")


class UserPreference(Base):
    __tablename__ = "user_preference"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "key", name="pk_user_preference"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Any] = mapped_column(JsonB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
