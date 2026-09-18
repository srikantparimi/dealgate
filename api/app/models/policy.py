"""`policy_version` — Finance-owned margin floors + FX convention.

Blueprint §2 fixes the sensible defaults (US 35%, India 50%) as the sentinel
returned when no ``policy_version`` has been published yet. Once Finance
publishes a version, callers should look it up by effective date and freeze
the id on any GM snapshot they persist.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class PolicyVersion(Base):
    __tablename__ = "policy_version"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    us_floor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    india_floor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    fx_convention: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
