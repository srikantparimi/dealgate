"""S10-01 — `sow_upload_job`, the durable envelope of one upload attempt.

The router (`app.routers.sows_upload`) creates one row when a human drops
a file, then the pipeline (`app.services.sow_upload_pipeline`) mutates
``status`` as it walks the chain. Every state transition emits an
``audit_event`` (CLAUDE.md rule 5).

Status alphabet (see also `app.services.sow_upload_pipeline`):

    queued → extracting → classifying → matching_client →
        deriving_gm → done
                                    ↘ needs_pick (paused until the
                                       reviewer picks a client)
    failed / duplicate are terminal too.

`file_hash` is the SHA-256 of the uploaded bytes and is unique so a
re-upload of the same file returns the existing job (no double-work).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class SowUploadJob(Base):
    __tablename__ = "sow_upload_job"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    uploader_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # SHA-256 hex. Unique — a repeat upload of the same bytes returns the
    # existing job (see `app.services.sow_upload_pipeline.find_by_hash`).
    file_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    # "matched" | "needs_pick" | "created" | None. Set by the client-
    # resolver step; the picker endpoint reads it to decide whether it can
    # resume the pipeline.
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("opportunity.id"), nullable=True
    )
    sow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sow_version.id"), nullable=True
    )
    # When `resolution="needs_pick"`, this envelope carries the picker
    # payload (top-3 candidates + create-new pre-fill). The frontend renders
    # from it directly so the picker survives a page reload.
    needs_pick_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["SowUploadJob"]
