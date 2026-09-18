"""SOW models — one ``Sow`` per opportunity, immutable ``SowVersion`` rows.

See ``alembic/versions/20260918_0006_sow.py`` for the schema and
``app.services.sow_extract`` for the write API.

Rule 4 (CLAUDE.md): SOW versions are immutable. The service layer never
issues ``UPDATE`` against ``sow_version`` for the extracted fields JSONB
as a whole — it treats it as an evolving column that only humans confirming
each field are allowed to touch. The row itself (upload timestamp, file
pointer, uploader) is set-once.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class Sow(Base):
    __tablename__ = "sow"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SowVersion(Base):
    __tablename__ = "sow_version"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sow.id"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id")
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    file_s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # Nullable until the extract job runs. Shape: see
    # ``app.integrations.bedrock_sow_extract.EXTRACTED_FIELDS``.
    extracted_fields: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    extract_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    extract_model: Mapped[str | None] = mapped_column(String(128))
    extract_prompt_version: Mapped[str | None] = mapped_column(String(32))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engagement_type_suggested: Mapped[str | None] = mapped_column(String(64))
    engagement_type_confirmed: Mapped[str | None] = mapped_column(String(64))
