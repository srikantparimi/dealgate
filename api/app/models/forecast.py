"""S6 E9 — ``forecast_period`` mapper.

One immutable row per (gm_model_id, week_ending) capturing the Delivery
lead's weekly remaining-hours snapshot plus the forecast revenue / cost /
GM computed via the ratified ``app.gm`` library.

Rule 4 (CLAUDE.md): the row is set-once; the service layer refuses PATCH.
The UNIQUE (gm_model_id, week_ending) constraint enforces "one snapshot
per week" at the DB level so a second POST for the same week surfaces as
a 409 (see ``app.services.forecast.update_forecast``).

Money is ``Decimal`` (rule 2): totals are NUMERIC(14,2); GM ratios are
NUMERIC(6,4). GM columns are nullable — a component with zero revenue
has an undefined GM (matches the pure library's ``None``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class ForecastPeriod(Base):
    __tablename__ = "forecast_period"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gm_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gm_model.id"), nullable=False
    )
    week_ending: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_lines_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonB, nullable=False
    )
    forecast_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    forecast_cost_us: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    forecast_cost_india: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    forecast_gm_us: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    forecast_gm_india: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "gm_model_id", "week_ending", name="uq_forecast_period_gm_week"
        ),
    )


class ForecastPlan(Base):
    __tablename__ = "forecast_plan"
    __table_args__ = (UniqueConstraint("tenant_id", "environment", "request_key", name="uq_forecast_plan_request"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("client.id", ondelete="CASCADE"), nullable=False)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("opportunity.id", ondelete="SET NULL"))
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ForecastPlanVersion(Base):
    __tablename__ = "forecast_plan_version"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_forecast_plan_version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("forecast_plan.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    probability: Mapped[Decimal | None] = mapped_column(Numeric())
    probability_source: Mapped[str | None] = mapped_column(String(2000))
    assumptions: Mapped[list] = mapped_column(JsonB, nullable=False)
    component_inputs: Mapped[dict] = mapped_column(JsonB, nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JsonB, nullable=False)
    scenario_group: Mapped[str | None] = mapped_column(String(255))
    selected: Mapped[bool] = mapped_column(nullable=False, default=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric())
    fx_version: Mapped[str | None] = mapped_column(String(128))
    fx_date: Mapped[date | None] = mapped_column(Date)
    change_reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ForecastSchedule(Base):
    __tablename__ = "forecast_schedule"
    plan_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("forecast_plan_version.id", ondelete="CASCADE"), primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JsonB, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ForecastJob(Base):
    __tablename__ = "forecast_job"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    plan_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("forecast_plan_version.id", ondelete="CASCADE"), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ForecastConversion(Base):
    __tablename__ = "forecast_conversion"
    __table_args__ = (UniqueConstraint("plan_id", "gm_model_id", name="uq_forecast_conversion_source"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("forecast_plan.id", ondelete="CASCADE"), nullable=False)
    gm_model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("gm_model.id", ondelete="SET NULL"))
    scope_fraction: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = ["ForecastPeriod", "ForecastPlan", "ForecastPlanVersion", "ForecastSchedule", "ForecastJob", "ForecastConversion"]
