"""``commercial_draft`` — S22 click-through root-cause fix.

One mutable working draft of the Staffing & GM commercial inputs per
opportunity, persisted server-side so the plan survives reloads and is
visible on every surface (workspace tab AND the Confirm page). This is
deliberately NOT a GM version: rule 4 versions stay immutable and are
still created only by the explicit Save-version action; the draft is
the whiteboard in front of them. Human-entered working state only — AI
proposals still require an explicit apply before they land here, and
``costs_confirmed`` inside a draft carries no approval weight until a
version is saved.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class CommercialDraft(Base):
    __tablename__ = "commercial_draft"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id", ondelete="CASCADE"), primary_key=True
    )
    # Soft ref, matching gm_model.sow_version_id: the draft follows the
    # opportunity even when a SOW version is superseded.
    sow_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    inputs: Mapped[dict] = mapped_column(JsonB, nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
