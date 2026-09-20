"""`client_rate_card` + `client_rate_card_row` — per-client bill rates.

S9 wave 1. Per ``docs/directives/sow-first.md``: **client rate cards, HR
cost bands and margin policy are three different tables**. This module
owns the bill-rate side (revenue) — the HR cost bands still live in
``app.models.rate_card`` (rename to ``cost_band`` deferred to a follow-up
refactor).

Rows are immutable versions tied to ``effective_from``. A published
``ClientRateCard`` is never mutated; Finance publishes a new one to change
rates. ``source`` records whether the card came from an MSA import,
manual entry or a bulk import — ``source_document_id`` back-links to the
MSA (or other) source file where relevant so the confirm screen can show
provenance per CLAUDE.md rule 10.

Money is ``NUMERIC(10,4)`` per the story (bill rates need finer resolution
than cost bands).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class ClientRateCard(Base):
    __tablename__ = "client_rate_card"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=False, index=True
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # 'msa' | 'manual' | 'import' — enforced via CheckConstraint below.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    # UUID of an uploaded source file (MSA/PDF) in the SOW/agreements bucket.
    # Nullable because manual publishes have no document.
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    rows: Mapped[list["ClientRateCardRow"]] = relationship(
        "ClientRateCardRow",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="ClientRateCardRow.role, ClientRateCardRow.seniority, ClientRateCardRow.location",
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('msa','manual','import')",
            name="ck_client_rate_card_source",
        ),
    )


class ClientRateCardRow(Base):
    __tablename__ = "client_rate_card_row"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_rate_card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("client_rate_card.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    seniority: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[str] = mapped_column(String(16), nullable=False)
    bill_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    unit: Mapped[str] = mapped_column(String(8), nullable=False, default="hourly")
    effective_period: Mapped[str | None] = mapped_column(String(64), nullable=True)

    card: Mapped[ClientRateCard] = relationship("ClientRateCard", back_populates="rows")

    __table_args__ = (
        CheckConstraint(
            "location IN ('US','India')",
            name="ck_client_rate_card_row_location",
        ),
        CheckConstraint(
            "unit IN ('hourly','daily','monthly')",
            name="ck_client_rate_card_row_unit",
        ),
    )


__all__ = ["ClientRateCard", "ClientRateCardRow"]
