"""S24-AG1 B4 — the standard NDA and MSA.

A standard copy is ONE stored object per version (``standard_agreement``),
kept under ``agreements/standard/{KIND}/``. Uploading one creates the next
version; it never touches the copies already attached to clients, which keep
pointing at the version they were given. Every role can read and download the
current version; Legal and SystemAdmin upload (the router enforces roles).

Write order (directive B5, plan rule 6): the object is stored first, then the
settings row is locked as the version mutex (lock order settings → rows →
audit), the version row and its audit row are written and committed together.
If that transaction fails, the stored object is queued for removal by the
deletion-cleanup worker: the API task role may only put and get objects, so
the compensating delete is a durable deletion job, never an in-request delete.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agreements import AgreementsSettings, StandardAgreement
from app.models.client import Agreement, Client
from app.models.user import User
from app.services import agreement_audit
from app.services.agreement_files import CheckedFile, standard_key
from app.services.agreement_status import (
    StandardInfo,
    iso_z,
    load_standards,
    person,
    standard_version_payload,
    visibility_scope,
)
from app.services.parent_deletion import queue_storage_cleanup

log = structlog.get_logger("agreement_standard")

DOWNLOAD_SECONDS = 300
MSG_STORAGE = "Document storage is unavailable. Try again in a minute."
MSG_RACE = "Another upload of the standard {kind} finished at the same moment. Upload the file again."


def missing_message(kind: str) -> str:
    return f"No standard {kind} has been uploaded yet."


async def standard_documents(session: AsyncSession, actor: Any, *, scope: Any = None) -> dict[str, Any]:
    """GET /agreements/standard: both kinds (None for a kind never uploaded), each with how many clients the
    caller can see hold that exact version. Three statements; equals the workspace's ``standard`` block."""
    from app.services.hubspot_pipeline import _client_visibility

    if scope is None:
        scope = await visibility_scope(session, actor)
    standards = await load_standards(session)
    ids = [info.id for info in standards.values() if info is not None]
    attached: dict[uuid.UUID, int] = {}
    if ids:
        rows = (await session.execute(
            select(Agreement.standard_agreement_id, func.count())
            .join(Client, Client.id == Agreement.client_id)
            .where(Agreement.source == "standard", Agreement.standard_agreement_id.in_(ids),
                   *_client_visibility(scope))
            .group_by(Agreement.standard_agreement_id)
        )).all()
        attached = {standard_id: int(count) for standard_id, count in rows}
    return {kind: (standard_version_payload(info, attached.get(info.id, 0)) if info is not None else None)
            for kind, info in standards.items()}


async def _lock_settings(session: AsyncSession) -> AgreementsSettings:
    """The settings singleton, locked FOR UPDATE: the version mutex for standard uploads (and the first lock
    of the batch start). Migration 0072 inserts it; a SQLite test schema may not have it, so it is created."""
    row = await session.scalar(
        select(AgreementsSettings).where(AgreementsSettings.id == 1).with_for_update()
        .execution_options(populate_existing=True))
    if row is None:
        row = AgreementsSettings(id=1)
        session.add(row)
        await session.flush()
    return row


async def queue_object_cleanup(session: AsyncSession, *, key: str, actor_id: uuid.UUID | None, title: str) -> bool:
    """Queue the removal of an object whose database row was never committed (directive B5, S10), through
    the shared compensating delete (``parent_deletion.queue_storage_cleanup``), and commit it.

    The caller has rolled back its failed transaction. The deletion-cleanup worker (every minute, with the
    delete permission the API lacks) re-checks that nothing references the key, then removes every version.
    Returns False, after logging the key, if even the job cannot be written (the original failure is never
    masked); the B13 orphan report then lists the object.
    """
    try:
        await queue_storage_cleanup(session, actor_id=actor_id, account_id=None, keys=[key], title=title)
        await session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — never mask the original failure
        await session.rollback()
        log.error("agreement_object_cleanup_not_queued", key=key, error=type(exc).__name__)
        return False


async def upload_standard(session: AsyncSession, s3: Any, *, actor: User, kind: str,
                          checked: CheckedFile) -> dict[str, Any]:
    """Store the file, then record the next version of the standard ``kind`` (201 StandardVersion).

    ``actor`` is the caller's user row (ensure_user, committed). A new version never changes a client's
    attached copy: those rows point at the version they were given.
    """
    # Read the caller's identity now: a rollback below expires every loaded instance, and touching an
    # expired attribute would reload it outside the async context.
    actor_id, uploaded_by = actor.id, person(actor.name, actor.email)
    key = standard_key(kind, checked.stored_name)
    try:
        await asyncio.to_thread(s3.put_object_at, key, checked.content_type, checked.content)
    except Exception as exc:
        log.warning("standard_upload_storage_failed", kind=kind, error=type(exc).__name__)
        raise HTTPException(502, MSG_STORAGE) from exc
    now = datetime.now(UTC)
    try:
        await _lock_settings(session)
        current = await session.scalar(
            select(func.max(StandardAgreement.version_no)).where(StandardAgreement.kind == kind))
        version = int(current or 0) + 1
        row = StandardAgreement(
            id=uuid.uuid4(), kind=kind, version_no=version, file_key=key, filename=checked.display_name,
            file_size=checked.size, sha256=checked.sha256, uploaded_by=actor_id, uploaded_at=now)
        session.add(row)
        await session.flush()
        await agreement_audit.record(
            session, actor_id=actor_id, action=agreement_audit.STANDARD_UPLOADED, entity="standard_agreement",
            entity_id=row.id,
            after={"kind": kind, "version_no": version, "standard_version": version, "standard": True,
                   "source": "standard", "filename": checked.display_name, "file_name": checked.display_name,
                   "file_size": checked.size, "sha256": checked.sha256, "file_key": key})
        await session.commit()
    except Exception as exc:
        await session.rollback()
        await queue_object_cleanup(session, key=key, actor_id=actor_id,
                                   title=f"Standard {kind} upload ({checked.display_name})")
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, MSG_RACE.format(kind=kind)) from exc
        raise
    info = StandardInfo(id=row.id, kind=kind, version=version, file_name=checked.display_name,
                        file_size=checked.size, sha256=checked.sha256, uploaded_by=uploaded_by,
                        uploaded_at=now, file_key=key)
    # A version just uploaded is attached to no client yet: a real count, not a missing value.
    return standard_version_payload(info, 0)


async def current_standard(session: AsyncSession, kind: str) -> StandardInfo:
    """The current standard ``kind``, or 404 with the reason (no standard copy uploaded yet)."""
    info = (await load_standards(session)).get(kind)
    if info is None:
        raise HTTPException(404, missing_message(kind))
    return info


async def download_standard(session: AsyncSession, s3: Any, *, actor: User, kind: str,
                            info: StandardInfo | None = None) -> dict[str, Any]:
    """A presigned link (300 seconds) to the current standard ``kind``, recorded in the audit log (B11).
    ``info`` is the version the caller already resolved (:func:`current_standard`), else it is read here."""
    if info is None:
        info = await current_standard(session, kind)
    try:
        url = s3.generate_download_url(info.file_key)
    except Exception as exc:
        log.warning("standard_download_link_failed", kind=kind, error=type(exc).__name__)
        raise HTTPException(502, MSG_STORAGE) from exc
    await agreement_audit.record(
        session, actor_id=actor.id, action=agreement_audit.DOWNLOADED, entity="standard_agreement",
        entity_id=info.id,
        after={"kind": kind, "standard": True, "source": "standard", "standard_version": info.version,
               "version_no": info.version, "filename": info.file_name, "file_name": info.file_name})
    await session.commit()
    return {"url": url, "expires_in_seconds": DOWNLOAD_SECONDS, "file_name": info.file_name,
            # additive
            "version": info.version, "uploaded_at": iso_z(info.uploaded_at)}


__all__ = [
    "DOWNLOAD_SECONDS", "current_standard", "download_standard", "missing_message", "queue_object_cleanup",
    "standard_documents", "upload_standard",
]
