"""`adviser_estimate` — one row per AI-drafted opportunity estimate.

Rows are immutable: any change of scope creates a fresh row. The label
column carries the wording humans see in the UI and PDF-less export flow
(§15 risk mitigation — no export button, ever). Keeping it in the row keeps
it auditable if the wording is ever tuned.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


# Kept in lock-step with the migration server_default and the service's
# label emitter — tests assert the exact string.
DEFAULT_LABEL = "Indicative estimate, requires Delivery and Finance validation"


class AdviserEstimate(Base):
    __tablename__ = "adviser_estimate"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Raw form payload from the intake — kept verbatim so a reviewer can see
    # exactly what the drafter typed.
    inputs: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    # Structured output = scope interpretation + team + cost bands + min
    # prices. Deterministic pricing math lives in the service; the LLM only
    # supplies roles/hours.
    structured_output: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB, nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    label: Mapped[str] = mapped_column(
        String(255), nullable=False, default=DEFAULT_LABEL, server_default=DEFAULT_LABEL
    )
