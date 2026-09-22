"""``gm_model`` + ``resource_line`` + ``cost_line`` — S3 E6.

Immutable GM model versions per opportunity. The base columns (id, engagement_type,
resource line role/seniority/location/dates, billable_hours, hourly_bill_rate,
hourly_loaded_cost, revenue_us/india) are owned by the S6 legacy-import
migration (``20260918_0009_legacy.py``); this Sprint 3 story adds the
Builder-specific columns via ``20260918_0007_gm_model.py``.

Rule 4 (CLAUDE.md): GM model versions are immutable. Every Save from the
Builder creates a new ``gm_model`` row plus its ``resource_line`` +
``cost_line`` children.

Money is ``Decimal`` / ``NUMERIC`` (rule 2). ``person_name`` is nullable —
NULL means "to hire" (HR pipeline). ``hourly_cost`` is nullable — NULL
means Delivery still owes Finance the validated cost.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class GmModel(Base):
    __tablename__ = "gm_model"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Legacy-owned base columns.
    sow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sow.id"), nullable=True
    )
    engagement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # S3 E6 additions.
    # Nullable FK because legacy imports may not carry an opportunity link.
    # The Builder always populates it; only legacy rows may be NULL.
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("opportunity.id"), nullable=True
    )
    # Soft ref — see the migration for why we don't hard-FK sow_version.
    sow_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    delivery_pattern: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contingency_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    warranty_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_us: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    revenue_india: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    direct_costs_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    resource_lines: Mapped[list["ResourceLine"]] = relationship(
        "ResourceLine",
        back_populates="gm_model",
        cascade="all, delete-orphan",
        # Order by created_at then id so the client always sees the rows in
        # the order they were saved. IDs are random UUIDs so ordering by id
        # alone would shuffle every version (and break "index N" warnings).
        order_by="ResourceLine.created_at, ResourceLine.id",
    )
    cost_lines: Mapped[list["CostLine"]] = relationship(
        "CostLine",
        back_populates="gm_model",
        cascade="all, delete-orphan",
        order_by="CostLine.id",
    )


class ResourceLine(Base):
    __tablename__ = "resource_line"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gm_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gm_model.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    seniority: Mapped[str] = mapped_column(String(64), nullable=False)
    # Enforced at the DB by the legacy migration's CHECK ('US','India').
    location: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    allocation_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    # Legacy-owned column names: billable_hours + hourly_loaded_cost.
    billable_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    hourly_bill_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    # Loaded cost from the legacy import path — populated to the Builder's
    # ``hourly_cost`` when the Builder saves. Kept NOT NULL for compatibility;
    # the Builder writes 0 with an explicit "unvalidated" marker in ``hourly_cost``.
    hourly_loaded_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
    revenue_us: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    revenue_india: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # S3 E6 additions.
    person_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Nullable — NULL flags "cost not yet validated" (blueprint §2 forbids
    # treating a missing cost as zero). The Builder mirrors this into
    # ``hourly_loaded_cost`` at save time (or 0 when null) purely to satisfy
    # the legacy NOT NULL constraint; the real "did we know the cost?"
    # signal is ``hourly_cost``.
    hourly_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    validated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    gm_model: Mapped[GmModel] = relationship("GmModel", back_populates="resource_lines")


class CostLine(Base):
    __tablename__ = "cost_line"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gm_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gm_model.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    location: Mapped[str] = mapped_column(String(16), nullable=False, default="US")
    basis: Mapped[str] = mapped_column(String(24), nullable=False, default="amount")
    basis_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    reimbursable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provenance: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    gm_model: Mapped[GmModel] = relationship("GmModel", back_populates="cost_lines")
