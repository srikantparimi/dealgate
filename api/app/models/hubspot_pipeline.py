"""HubSpot pipeline + stage mirror tables (S19 slice 1 A1–A2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HubspotPipeline(Base):
    __tablename__ = "hubspot_pipeline"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class HubspotStage(Base):
    __tablename__ = "hubspot_stage"
    __table_args__ = (
        Index("ix_hubspot_stage_pipeline_order", "pipeline_id", "display_order"),
        UniqueConstraint("pipeline_id", "id", name="uq_hubspot_stage_pipeline_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("hubspot_pipeline.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    probability: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
