"""SOW version lifecycle: revise, supersede, delete, discard (S10-06).

The versioning table has always existed — one ``Sow`` per opportunity, many
``SowVersion`` rows — but nothing in the SOW-first flow ever reached it for a
revision. Uploading a corrected SOW either created a *second opportunity* for
the same engagement (when the business-key dedupe could not fire because the
term dates were missing) or was refused as a duplicate. And there was no way
to remove a bad upload at all: the API had no delete route for a SOW, a
version, an upload job or an opportunity.

Two rules shape what follows.

**Immutability (CLAUDE.md rule 4).** A version is never edited in place to
become a revision. A revision is a new row; the old one is marked superseded
and stays exactly as it was, because an approver's decision has to remain
attached to the words they actually approved.

**Delete is bounded by approval.** A version that has never been part of an
approval package is a private draft — a wrong file, a bad extraction, a test
run — and deleting it removes clutter nobody has relied on. Once a version
has been submitted, someone has acted on it, and it can only be discarded.
Either way an ``audit_event`` records what happened: ``audit_event.entity_id``
is a plain string with no foreign key, so the trail survives the row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.approval import ApprovalPackage
from app.models.sow import Sow, SowVersion

__all__ = [
    "SowLifecycleError",
    "VersionSummary",
    "discard_version",
    "delete_version",
    "list_versions",
    "reserve_version_no",
    "supersede",
    "was_ever_submitted",
]


class SowLifecycleError(Exception):
    """Refusal the router turns into a 4xx with the reason."""

    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class VersionSummary:
    id: uuid.UUID
    version_no: int
    uploaded_at: datetime
    uploaded_by: uuid.UUID | None
    extract_status: str
    execution_state: str
    is_current: bool
    superseded_by: uuid.UUID | None
    discarded_at: datetime | None
    discard_reason: str | None
    file_name: str | None
    ever_submitted: bool


async def reserve_version_no(session: AsyncSession, sow_id: uuid.UUID) -> int:
    """Reserve and return the next ordinal for this SOW.

    Numbers are never reused, including after a delete. MAX(version_no) alone
    does not give that: delete the highest version and MAX drops, so the next
    upload reuses that number — and the audit trail then has two different
    documents both recorded as "version 2". So the counter lives on the Sow
    row and only ever increments.

    Seeded from MAX on first use so SOWs created before the counter existed
    carry on from where they actually are rather than restarting at 1.
    """

    sow = (
        await session.execute(select(Sow).where(Sow.id == sow_id))
    ).scalar_one_or_none()
    if sow is None:
        raise SowLifecycleError("sow not found", status_code=404)

    highest = (
        await session.execute(
            select(func.max(SowVersion.version_no)).where(SowVersion.sow_id == sow_id)
        )
    ).scalar()
    sow.version_counter = max(int(sow.version_counter or 0), int(highest or 0)) + 1
    await session.flush()
    return sow.version_counter


async def was_ever_submitted(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> bool:
    """True if any approval package has ever referenced this version.

    This is the line between delete and discard. Note it asks whether a
    package *exists*, not whether one is currently open — a withdrawn or
    rejected package still means a human looked at this document.
    """

    found = (
        await session.execute(
            select(ApprovalPackage.id)
            .where(ApprovalPackage.sow_version_id == sow_version_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def list_versions(
    session: AsyncSession, sow_id: uuid.UUID
) -> list[VersionSummary]:
    """Every version of one SOW, newest first, including discarded ones."""

    rows = list(
        (
            await session.execute(
                select(SowVersion)
                .where(SowVersion.sow_id == sow_id)
                .order_by(SowVersion.version_no.desc())
            )
        ).scalars()
    )
    out: list[VersionSummary] = []
    for r in rows:
        out.append(
            VersionSummary(
                id=r.id,
                version_no=r.version_no,
                uploaded_at=r.uploaded_at,
                uploaded_by=r.uploaded_by,
                extract_status=r.extract_status,
                execution_state=r.execution_state,
                is_current=r.superseded_by is None and r.discarded_at is None,
                superseded_by=r.superseded_by,
                discarded_at=r.discarded_at,
                discard_reason=r.discard_reason,
                file_name=(r.file_s3_key or "").rsplit("/", 1)[-1] or None,
                ever_submitted=await was_ever_submitted(session, r.id),
            )
        )
    return out


async def supersede(
    session: AsyncSession,
    *,
    old: SowVersion,
    new: SowVersion,
    actor_id: uuid.UUID | None,
) -> None:
    """Point an older version at the revision that replaced it.

    The old row is otherwise untouched: its extracted fields, its GM and any
    approval attached to it stay exactly as they were. Superseding records
    that it is no longer the operative document, not that it never existed.
    """

    if old.id == new.id:
        raise SowLifecycleError("a version cannot supersede itself", status_code=422)
    before = {"execution_state": old.execution_state, "superseded_by": None}
    old.superseded_by = new.id
    if old.execution_state == "draft":
        old.execution_state = "superseded"
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="sow_version.superseded",
        entity="sow_version",
        entity_id=str(old.id),
        before=before,
        after={
            "execution_state": old.execution_state,
            "superseded_by": str(new.id),
            "superseded_by_version_no": new.version_no,
        },
    )


async def delete_version(
    session: AsyncSession,
    *,
    sow_version_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> dict[str, str | None]:
    """Hard-delete a version that has never reached an approval package.

    Refuses once the version has been submitted — at that point it is part of
    a decision record and only :func:`discard_version` applies.

    The audit row is written *before* the delete, and survives it: the audit
    table addresses its subject by a plain string id with no foreign key, so
    the history shows the document existed, who removed it and why, even
    though the row is gone. The S3 object is left for the caller to remove —
    object deletion is not transactional with the database, and a failure
    there must not roll back an otherwise good delete.
    """

    version = (
        await session.execute(
            select(SowVersion).where(SowVersion.id == sow_version_id)
        )
    ).scalar_one_or_none()
    if version is None:
        raise SowLifecycleError("sow version not found", status_code=404)

    if await was_ever_submitted(session, sow_version_id):
        raise SowLifecycleError(
            "this version has been submitted for approval and cannot be "
            "deleted — discard it instead so the decision record survives"
        )

    # Anything pointing at this row has to stop pointing at it first,
    # otherwise the delete fails on the FK and the caller gets a 500 for what
    # is really a simple ordering problem.
    pointing = list(
        (
            await session.execute(
                select(SowVersion).where(SowVersion.superseded_by == sow_version_id)
            )
        ).scalars()
    )
    for row in pointing:
        row.superseded_by = None
        if row.execution_state == "superseded":
            row.execution_state = "draft"

    snapshot = {
        "version_no": version.version_no,
        "file_s3_key": version.file_s3_key,
        "file_hash": version.file_hash,
        "extract_status": version.extract_status,
        "sow_id": str(version.sow_id),
    }
    await append_audit(
        session,
        actor_id=actor_id,
        action="sow_version.deleted",
        entity="sow_version",
        entity_id=str(version.id),
        before=snapshot,
        after={"deleted": True, "reason": reason},
    )
    s3_key = version.file_s3_key
    await session.delete(version)
    await session.flush()
    return {"s3_key": s3_key, "reason": reason}


async def discard_version(
    session: AsyncSession,
    *,
    sow_version_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str,
) -> SowVersion:
    """Soft-discard a version, leaving the row and the file in place.

    For anything that has been through approval. A reason is required — a
    discarded SOW disappears from every board, and six months later the only
    explanation anyone will have is this sentence.
    """

    if not reason or not reason.strip():
        raise SowLifecycleError("a reason is required to discard", status_code=422)

    version = (
        await session.execute(
            select(SowVersion).where(SowVersion.id == sow_version_id)
        )
    ).scalar_one_or_none()
    if version is None:
        raise SowLifecycleError("sow version not found", status_code=404)
    if version.discarded_at is not None:
        return version  # idempotent

    before = {
        "execution_state": version.execution_state,
        "discarded_at": None,
    }
    version.discarded_at = datetime.now(UTC)
    version.discarded_by = actor_id
    version.discard_reason = reason.strip()
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="sow_version.discarded",
        entity="sow_version",
        entity_id=str(version.id),
        before=before,
        after={
            "discarded_at": version.discarded_at.isoformat(),
            "reason": version.discard_reason,
        },
    )
    return version


async def sow_for_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Sow | None:
    return (
        await session.execute(
            select(Sow).where(Sow.opportunity_id == opportunity_id)
        )
    ).scalar_one_or_none()
