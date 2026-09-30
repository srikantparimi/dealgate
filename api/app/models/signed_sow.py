"""S5 E8 — signed SOW upload ORM model (Agent X2).

One :class:`SignedSowUpload` per ``approval_package`` that has landed
in ``ready_to_sign``. The row is set-once (rule 4) on the identity
columns — file pointer, hash, uploader. The state-machine fields
(``verify_status``, ``diff_json``, ``verified_at``, ``released_at``)
are touched by :mod:`app.services.signed_sow`, which pairs every
change with an ``audit_event`` (rule 5).

Re-uploading a different executed pdf **creates a new row** (audits
``signed_sow.replaced``) — the previous row is left as-is so the
audit trail can reconstruct the sequence. See the service docstring
for the transition rules.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


# Kept in lock-step with alembic 0015's CHECK constraint and the
# ``VERIFY_STATUSES`` tuple in ``app.services.signed_sow``.
#
# S20 W7 (T22): expanded to distinguish `unsigned` (upload has no
# detectable signature), `declined` (external signer refused) and
# `expired` (signature request timed out) from the generic `blocked`.
# The CHECK migration lands via requests.md #W7-2026-09-30-01; until
# it does, the SQLite test path uses this tuple directly via
# `Base.metadata.create_all` so tests exercise the full alphabet.
VERIFY_STATUSES: tuple[str, ...] = (
    "pending",
    "verified",
    "blocked",
    "unsigned",
    "declined",
    "expired",
)

# `signer_state` tracks the external signature-request lifecycle,
# independent of verify_status. `null` when no request has been sent;
# `sent` after the request goes out; then one of `signed / declined /
# expired` when the external system reports back.
SIGNER_STATES: tuple[str, ...] = ("sent", "signed", "declined", "expired")


class SignedSowUpload(Base):
    __tablename__ = "signed_sow_upload"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("approval_package.id"), nullable=False
    )
    file_s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    verify_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    # S20 W7 (T22): human-readable reason accompanying every non-verified
    # verify_status. Examples: `price_mismatch`, `unsigned_upload`,
    # `declined_by_signer`, `signature_request_expired`.
    verify_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # S20 W7 (T22): external signature lifecycle. Advances independently
    # from `verify_status` so the UI can show "Sent" while a diff is
    # still pending.
    signer_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    diff_json: Mapped[dict[str, Any] | None] = mapped_column(JsonB, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["SIGNER_STATES", "VERIFY_STATUSES", "SignedSowUpload"]
