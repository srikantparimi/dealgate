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

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, UniqueConstraint, func
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


__all__ = ["ForecastPeriod"]
