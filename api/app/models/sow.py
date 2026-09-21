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

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
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
    # Monotonic version counter (S10-06). MAX(version_no) is not enough:
    # delete the highest version and MAX drops, so the next upload reuses that
    # number and two different documents end up sharing a version label in the
    # audit trail. This only ever goes up.
    version_counter: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # S13a — archive columns; see app.services.deletion.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    archived_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)


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

    # --- lifecycle (S10-06) ------------------------------------------------
    #
    # `execution_state` and `governance_status` were previously bolted onto
    # this class at import time by `app/models/import_batch.py`, "without
    # editing the file agent P owns". That made `SowVersion.execution_state`
    # exist only if `import_batch` happened to have been imported first — a
    # hidden ordering dependency, and invisible to anyone reading this file.
    # They are ordinary columns; they belong here. The monkey-patch is
    # idempotent (it checks `hasattr` first), so declaring them makes it a
    # no-op rather than a conflict.
    execution_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    governance_status: Mapped[str | None] = mapped_column(String(48))

    # Versions are numbered per Sow, starting at 1. Without this a "v2" could
    # only be inferred from upload order, which is not stable once a version
    # is deleted.
    version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Set on the older version when a revision replaces it, so the chain of
    # what-replaced-what is explicit rather than reconstructed from dates.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sow_version.id")
    )
    # Soft discard, for a version that has already been through approval and
    # therefore cannot be deleted (CLAUDE.md rule 4 — approval records are
    # immutable). A discarded version leaves every board and list but its row
    # and its file survive.
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discarded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id")
    )
    discard_reason: Mapped[str | None] = mapped_column(String(500))
