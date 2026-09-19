"""``function_owner`` — accountable user per function per business unit.

See ``alembic/versions/20260920_0027_function_owner.py`` for the schema
and :mod:`app.services.approvers` for the resolver + fallback rules.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {"delivery", "hr", "finance", "legal"}
)


class FunctionOwner(Base):
    __tablename__ = "function_owner"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    function: Mapped[str] = mapped_column(String(32), nullable=False)
    business_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "function IN ('delivery', 'hr', 'finance', 'legal')",
            name="ck_function_owner_function",
        ),
    )


__all__ = ["ALLOWED_FUNCTIONS", "FunctionOwner"]
