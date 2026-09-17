from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class Opportunity(Base):
    __tablename__ = "opportunity"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    hubspot_deal_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))
    engagement_type: Mapped[str | None] = mapped_column(String(64))
    sales_stage: Mapped[str | None] = mapped_column(String(64))
    # governance_status is the DealGate-owned state (Intake → Coverage → SOWDraft → ...).
    governance_status: Mapped[str] = mapped_column(String(64), nullable=False, default="Intake")
    next_client_action: Mapped[str | None] = mapped_column(String(255))
    next_client_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
