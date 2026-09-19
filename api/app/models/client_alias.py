"""S10-01 — `client_alias` table.

The SOW client resolver (`app.services.client_resolver`) walks aliases
before falling through to a fuzzy name match, so a client historically
signed under "Acme, LLC" but referenced as "Acme" in a new SOW still
lines up on the first hit rather than nudging into the picker.

Aliases are additive-only. New rows are written when a picker chooses an
existing client for a SOW whose extracted legal name doesn't already
match, so subsequent uploads sail past the picker.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class ClientAlias(Base):
    __tablename__ = "client_alias"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    # One of "sow_upload" | "picker" | "manual" | "import". Free-form so
    # the service layer stays the single source of truth for the alphabet.
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["ClientAlias"]
