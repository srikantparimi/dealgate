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
    gm_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("gm_model.id", ondelete="SET NULL"), nullable=True
    )
    resource_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("resource_line.id", ondelete="SET NULL"), nullable=True
    )
    original_gm_model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    original_resource_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    source_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class FinancialImportBatch(Base):
    __tablename__ = "financial_import_batch"
    __table_args__ = (UniqueConstraint("tenant_id", "environment", "source_system", "request_key", name="uq_financial_import_request"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    errors: Mapped[list[dict] | None] = mapped_column(JsonB)
    test_fixture: Mapped[bool] = mapped_column(nullable=False, default=False)


class FinancialActual(Base):
    __tablename__ = "financial_actual"
    __table_args__ = (UniqueConstraint("tenant_id", "environment", "source_system", "source_id", "revision", name="uq_financial_actual_revision"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("financial_import_batch.id"), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("client.id", ondelete="SET NULL"))
    original_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    gm_model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("gm_model.id", ondelete="SET NULL"))
    original_gm_model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    measure: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_date: Mapped[date] = mapped_column(Date, nullable=False)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric())
    fx_version: Mapped[str | None] = mapped_column(String(128))
    fx_date: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    coverage: Mapped[dict | None] = mapped_column(JsonB)
    test_fixture: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = ["ActualImportBatch", "ActualPeriod", "FinancialImportBatch", "FinancialActual"]
