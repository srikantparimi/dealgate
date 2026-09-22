"""Workspace category choices; historical cost lines keep their own labels."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class DirectCostSettings(Base):
    __tablename__ = "direct_cost_settings"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    categories: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
