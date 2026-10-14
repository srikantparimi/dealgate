"""S22 portfolio & forecast ledger.

One ledger: every person on every engagement is an ``allocation`` row with a
start, an end, a bill rate and a cost. A leaver is an end date; a re-hire is
a new row; a rate change after the row has started supersedes it (new row,
``superseded_by`` on the old one) — history is never rewritten.

Tables (directive S22 P1-2, columns per docs/reference/openapi-forecast.yaml):

- ``engagement``        — the sheet's project block.
- ``resource``          — a person (name, location, employment type, seniority).
- ``allocation``        — one row per person per engagement window.
- ``engagement_cost``   — additional costs (one-time / monthly, billed or absorbed).
- ``calendar_location`` — burden % by employment type + resource floor, per location.
- ``holiday``           — weekday holidays per location.
- ``cost_rate_card``    — our cost/hour by seniority × location × employment type.
- ``forecast_policy``   — hours/day + project GM floor (single row).
- ``forecast_run``      — cached ``Forecast`` JSON keyed by a hash of its inputs.

Every money / percentage column is :class:`app.db.decimal.ExactNumeric`
(NUMERIC on Postgres, exact-string on SQLite) so the engine's Decimal
arithmetic round-trips to the cent (CLAUDE.md rule 2). Nothing here
computes: the only producer of forecast numbers is
:mod:`app.services.forecast`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB
from app.db.decimal import ExactNumeric

ENGAGEMENT_TYPES: tuple[str, ...] = (
    "fixed_cost",
    "assessment",
    "msp",
    "time_and_materials",
    "staff_augmentation",
)
EMPLOYMENT_TYPES: tuple[str, ...] = ("w2_employee", "contractor_1099")
COST_FREQUENCIES: tuple[str, ...] = ("one_time", "monthly")
SENIORITIES: tuple[str, ...] = ("Junior", "Mid", "Senior", "Principal")
BUSINESS_UNITS: tuple[str, ...] = ("ST21", "IT Avalon", "Retro Rabbit")
RATE_BASES: tuple[str, ...] = ("hourly", "daily", "monthly")


class Engagement(Base):
    __tablename__ = "engagement"
    __table_args__ = (
        CheckConstraint(
            "type IN ('fixed_cost','assessment','msp','time_and_materials','staff_augmentation')",
            name="ck_engagement_type",
        ),
        CheckConstraint(
            "business_unit IN ('ST21','IT Avalon','Retro Rabbit')",
            name="ck_engagement_business_unit",
        ),
        Index("ix_engagement_client_window", "client_id", "start", "end"),
        Index("ix_engagement_business_unit", "business_unit", "closed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("client.id", ondelete="CASCADE"), nullable=False
    )
    # Set when the engagement was created from a Closed-Won HubSpot deal.
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("opportunity.id", ondelete="SET NULL"), nullable=True
    )
    hubspot_deal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    start: Mapped[date] = mapped_column(Date, nullable=False)
    end: Mapped[date] = mapped_column(Date, nullable=False)
    total_price: Mapped[Decimal | None] = mapped_column(ExactNumeric, nullable=True)
    monthly_fee: Mapped[Decimal | None] = mapped_column(ExactNumeric, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD", server_default="USD")
    additional_costs_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    same_dates_for_all: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # S22 P5: the company reports across three business units; owners are the
    # model's free-text names (not user ids); closed rows stay for history and
    # are excluded from the portfolio.
    business_unit: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ST21", server_default="ST21"
    )
    sales_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Resource(Base):
    __tablename__ = "resource"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    seniority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Allocation(Base):
    __tablename__ = "allocation"
    __table_args__ = (
        Index("ix_allocation_engagement_window", "engagement_id", "start", "end"),
        Index("ix_allocation_resource_window", "resource_id", "start", "end"),
        Index("ix_allocation_superseded_by", "superseded_by"),
        CheckConstraint("rate_basis IN ('hourly','daily','monthly')", name="ck_allocation_rate_basis"),
        UniqueConstraint("engagement_id", "import_key", name="uq_allocation_import_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("resource.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    seniority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    assignment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utilization: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)
    bill_rate: Mapped[Decimal | None] = mapped_column(ExactNumeric, nullable=True)
    # NULL = pre-fill from the cost rate card at compute time.
    cost_per_hour: Mapped[Decimal | None] = mapped_column(ExactNumeric, nullable=True)
    # NULL = the engagement window (engine semantics).
    start: Mapped[date | None] = mapped_column(Date, nullable=True)
    end: Mapped[date | None] = mapped_column(Date, nullable=True)
    hours_override: Mapped[Decimal | None] = mapped_column(ExactNumeric, nullable=True)
    # S22 P5: what bill_rate is per (engine semantics) and the named person
    # when known (resource/role stays the planning label).
    rate_basis: Mapped[str] = mapped_column(
        String(16), nullable=False, default="hourly", server_default="hourly"
    )
    person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # S22 P5 final: the forecast-model importer's identity for this row
    # ("{assignment_key}:{row_key}:{segment}"); matched on re-import. NULL for
    # rows the app creates. Unique per engagement where set.
    import_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("allocation.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AllocationActual(Base):
    """What really happened in a month for one allocation (timesheets / invoices).

    ``hours`` are net (leave already deducted); ``revenue`` is billed. One row
    per allocation-month; ``PUT /allocations/{id}/actuals`` replaces the set.
    The engine turns these into ``MonthLine.actual_*`` and ``billing_loss``.
    """

    __tablename__ = "allocation_actual"
    __table_args__ = (
        UniqueConstraint("allocation_id", "month", name="uq_allocation_actual_month"),
        Index("ix_allocation_actual_allocation", "allocation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    allocation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("allocation.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    hours: Mapped[Decimal | None] = mapped_column(ExactNumeric, nullable=True)
    revenue: Mapped[Decimal | None] = mapped_column(ExactNumeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EngagementCost(Base):
    __tablename__ = "engagement_cost"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)
    frequency: Mapped[str] = mapped_column(
        String(16), nullable=False, default="one_time", server_default="one_time"
    )
    billed_to_client: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CalendarLocation(Base):
    __tablename__ = "calendar_location"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    burden_pct_w2: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)
    burden_pct_1099: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)
    resource_floor_pct: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Holiday(Base):
    __tablename__ = "holiday"
    __table_args__ = (UniqueConstraint("location_id", "day", name="uq_holiday_location_day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("calendar_location.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)


class CostRateCard(Base):
    __tablename__ = "cost_rate_card"
    __table_args__ = (
        UniqueConstraint(
            "seniority", "location_id", "employment_type", name="uq_cost_rate_card_cell"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    seniority: Mapped[str] = mapped_column(String(32), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("calendar_location.id", ondelete="CASCADE"), nullable=False
    )
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cost_per_hour: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)


class ForecastPolicy(Base):
    """Single row: the engine's hours/day and project GM floor."""

    __tablename__ = "forecast_policy"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    hours_per_day: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)
    project_floor_pct: Mapped[Decimal] = mapped_column(ExactNumeric, nullable=False)
    billing_loss_threshold_amount: Mapped[Decimal | None] = mapped_column(
        ExactNumeric, nullable=True
    )
    renewal_likely_probability: Mapped[Decimal | None] = mapped_column(
        ExactNumeric, nullable=True
    )
    renewal_unlikely_probability: Mapped[Decimal | None] = mapped_column(
        ExactNumeric, nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ForecastRun(Base):
    """A serialised ``Forecast`` for one engagement, keyed by its inputs.

    ``input_hash`` covers the engagement row, every current allocation,
    every cost and the whole calendar — a change to any of them yields a
    new hash, so a stale run is simply never looked up again. Rows are
    append-only (CLAUDE.md rule 4): the latest row for a hash is the cache.
    """

    __tablename__ = "forecast_run"
    __table_args__ = (Index("ix_forecast_run_lookup", "engagement_id", "input_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "Allocation",
    "AllocationActual",
    "BUSINESS_UNITS",
    "RATE_BASES",
    "CalendarLocation",
    "COST_FREQUENCIES",
    "CostRateCard",
    "EMPLOYMENT_TYPES",
    "ENGAGEMENT_TYPES",
    "Engagement",
    "EngagementCost",
    "ForecastPolicy",
    "ForecastRun",
    "Holiday",
    "Resource",
    "SENIORITIES",
]
