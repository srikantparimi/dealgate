"""S6 E9 actuals-import models.

Two tables (see migration ``20260918_0019_actuals.py``):

- :class:`ActualImportBatch` — one row per uploaded CSV. Lifecycle:
  ``uploading`` -> ``validated`` -> ``committed`` (happy path) or
  ``failed`` (rejected, whole-file, per §2).
- :class:`ActualPeriod` — one row per (resource_line, period_month).
  ``UNIQUE (resource_line_id, period_month)`` supports upsert on re-import.

Money is ``Decimal`` / ``NUMERIC`` end-to-end (CLAUDE.md rule 2).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class ActualImportBatch(Base):
    __tablename__ = "actual_import_batch"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    # uploading -> validated -> committed | failed (see CHECK in migration 0019).
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uploading"
    )


class ActualPeriod(Base):
    __tablename__ = "actual_period"
    __table_args__ = (
        UniqueConstraint(
            "resource_line_id", "period_month", name="uq_actual_period_line_month"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gm_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gm_model.id"), nullable=False
    )
    resource_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("resource_line.id"), nullable=False
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    actual_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    actual_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    imported_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("actual_import_batch.id"), nullable=True
    )


__all__ = ["ActualImportBatch", "ActualPeriod"]
