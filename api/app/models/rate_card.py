"""`rate_card_version` + `rate_card_row` — Finance planning cost bands.

S2-E4: Rate cards are immutable versions tied to an ``effective_from`` date.
Publishing a new set of rows always creates a new version; existing versions
never mutate. GM calculations record which ``rate_card_version_id`` they used
so results remain reproducible after Finance changes bands.

See build-guide §7. Money is ``NUMERIC(14,2)`` (see CLAUDE.md rule 2 —
Decimal all the way).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class RateCardVersion(Base):
    __tablename__ = "rate_card_version"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    rows: Mapped[list["RateCardRow"]] = relationship(
        "RateCardRow",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="RateCardRow.role, RateCardRow.seniority, RateCardRow.location",
    )


class RateCardRow(Base):
    __tablename__ = "rate_card_row"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rate_card_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rate_card_version.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    seniority: Mapped[str] = mapped_column(String(64), nullable=False)
    # Location matches gm.types.Location — "US" | "India".
    location: Mapped[str] = mapped_column(String(16), nullable=False)
    cost_low: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cost_base: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cost_high: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    version: Mapped[RateCardVersion] = relationship("RateCardVersion", back_populates="rows")
