"""``gm_model_template`` — reusable delivery-model shape (S7 wave 2).

Blueprint §7 rule: templates NEVER carry cost values — the Builder
looks up cost bands from the active rate card whenever a Delivery user
seeds a new opportunity from a template.

``template_json`` shape:

    {
      "phases": [
        {"name": ..., "order": 0, "sow_deliverable_ref": ..., "description": ...},
        ...
      ],
      "resource_lines": [
        {
          "phase_name": "Discovery" | null,
          "role": ..., "seniority": ..., "location": "US" | "India",
          "allocation_pct": "1", "hours_billable": "40",
          "hourly_bill_rate": "0"
        },
        ...
      ],
      "cost_lines": [
        {"phase_name": ..., "category": ..., "amount": "0", "location": ..., "note": ...},
        ...
      ]
    }

The ``phase_name`` field on each row is the join key when seeding — the
template is deliberately not FK-linked to a specific gm_model_phase id
so a template can be applied to any opportunity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class GmModelTemplate(Base):
    __tablename__ = "gm_model_template"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    engagement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    template_json: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


__all__ = ["GmModelTemplate"]
