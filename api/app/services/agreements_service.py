"""S24-AG1 B5/B6/B11 — every per-client NDA and MSA write, the audited downloads and the panel payload.

The new ``/clients/{id}/agreements/...`` routes and the legacy ``/agreements`` routes all call this module, so
one set of rules applies everywhere:

* **Client copy** — the client's own file. The first upload creates the agreement row; a later upload (or one
  over a standard copy or a "covered" mark) adds a version, and the earlier state stays in history.
* **Attach standard** — a row of source ``standard`` pointing at the ONE shared standard object; nothing is
  copied. Refused (409) when the client already holds the kind (a file or a mark).
* **Mark / unmark** — a kind covered with no file; removal is soft (kept in history).
* **Detach** — a client copy follows the existing deletion-job path (the cleanup worker removes its objects); a
  standard attachment removes only the client's row, because the shared object belongs to every holder.

Locks: the client row first, then its agreement / mark rows; the audit row is appended LAST, then commit (the
audit chain serialises on one global lock). Files: the object is written before the row; when the row cannot be
committed the object is queued for deletion (``parent_deletion.queue_storage_cleanup``), because the API task
role may only Put/Get in the bucket. Every audit payload names the client, kind and file, so the Activity feed
never needs the row and never shows an id. Classification (states, relationship, requirement) is never done
here: it comes from ``agreement_status``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.agreements import AgreementBatch, AgreementMark, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.user import User
from app.services import agreement_audit as audit
from app.services.agreement_files import CheckedFile, client_copy_key, object_key
from app.services.agreement_status import (
    KINDS,
    ClientFacts,
    Population,
    basis_text,
    business_unit_objects,
    business_unit_reason,
    iso_z,
    load_agreement_population,
    person,
    stage_text,
)
from app.services.business_time import business_today
from app.services.test_fixtures import ISSUED, account_scope, is_test_user, user_allowed

log = logging.getLogger("dealgate.agreements")

READ_ROLES: tuple[str, ...] = (
    "Marketing", "Sales", "SalesLeader", "Presales", "Delivery", "HR", "Finance", "Legal", "CEO", "SystemAdmin",
)
WRITE_ROLES: tuple[str, ...] = ("Legal", "SystemAdmin")
ADMIN_ROLES: tuple[str, ...] = ("SystemAdmin",)
DOWNLOAD_TTL_SECONDS = 300
NOTE_MAX = 200
STORAGE_UNAVAILABLE = "Document storage is unavailable. Try again in a minute."
# The reasons a person may choose (MarkRequest). ``per_hubspot`` is written only by the HubSpot mapping apply.
MARK_REASONS_API: tuple[str, ...] = (
    "signed_outside_dealgate", "covered_by_earlier_work", "confirmed_with_client", "other",
)


# --- who is calling ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reader:
    """The caller for a read: the DealGate user id, resolved without writing, and the token's groups.

    Reads never provision the user row (``ensure_user`` writes); the id is the row ``ensure_user`` would pick,
    so fixture participation is judged on the same id as the writes.
    """

    id: uuid.UUID
    groups: tuple[str, ...]


async def reader(session: AsyncSession, user) -> Reader:
    from app.services.canonical_user import resolve_viewer

    viewer = await resolve_viewer(session, user)
    return Reader(id=viewer.user_id or user.id, groups=tuple(user.groups or ()))


def test_identity_blocked(actor) -> bool:
    """A test identity may not run global writes (a real batch, its undo) outside local and test."""
    return is_test_user(actor) and os.environ.get("DEALGATE_ENV", "local") not in ("local", "test")


def clean_note(note: str | None) -> str | None:
    text = (note or "").strip()
    if len(text) > NOTE_MAX:
        raise HTTPException(422, f"A note can be at most {NOTE_MAX} characters.")
    return text or None


# --- access and locks -------------------------------------------------------------------------


async def authorize_client(session: AsyncSession, actor, client_id: uuid.UUID) -> None:
    """404 across the fixture boundary (real users never see test fixtures; test users only their own)."""
    if not user_allowed(actor, await account_scope(session, client_id)):
        raise HTTPException(404, "client not found")


async def lock_client(session: AsyncSession, actor, client_id: uuid.UUID) -> Client:
    client = await session.scalar(
        select(Client).where(Client.id == client_id).with_for_update().execution_options(populate_existing=True))
    if client is None or client.archived_at is not None:
        raise HTTPException(404, "client not found")
    await authorize_client(session, actor, client_id)  # re-checked under the lock
    return client


async def _locked_row(session: AsyncSession, client_id: uuid.UUID, kind: str) -> Agreement | None:
    return await session.scalar(
        select(Agreement).where(Agreement.client_id == client_id, Agreement.kind == kind)
        .with_for_update().execution_options(populate_existing=True))


async def _active_mark(session: AsyncSession, client_id: uuid.UUID, kind: str) -> AgreementMark | None:
    return await session.scalar(
        select(AgreementMark).where(AgreementMark.client_id == client_id, AgreementMark.kind == kind,
                                    AgreementMark.removed_at.is_(None))
        .with_for_update().execution_options(populate_existing=True))


# --- storage ----------------------------------------------------------------------------------


async def fixture_run_id(session: AsyncSession, client_id: uuid.UUID) -> uuid.UUID | None:
    """The run id of a server-issued test fixture (T11): its uploads are keyed under agreements/e2e/{run}/."""
    after = await session.scalar(
        select(AuditEvent.after).where(AuditEvent.action == ISSUED, AuditEvent.entity == "client",
                                       AuditEvent.entity_id == str(client_id))
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(1))
    try:
        return uuid.UUID(str((after or {}).get("run_id")))
    except (ValueError, TypeError, AttributeError):
        return None


def client_object_key(agreement_id: uuid.UUID, stored_name: str, run_id: uuid.UUID | None) -> str:
    """``agreements/{agreement}/…`` for a real client, ``agreements/e2e/{run}/{agreement}/…`` for a test fixture.

    Both stay under ``agreements/`` (the only prefix the API task role may write)."""
    if run_id is not None:
        return object_key(f"agreements/e2e/{run_id}/{agreement_id}", stored_name)
    return client_copy_key(agreement_id, stored_name)


async def _put(s3, key: str, checked: CheckedFile) -> None:
    try:
        await asyncio.to_thread(s3.put_object_at, key, checked.content_type, checked.content)
    except Exception as exc:  # noqa: BLE001 — any storage failure is the same answer to the caller
        raise HTTPException(502, STORAGE_UNAVAILABLE) from exc


async def _compensate(session: AsyncSession, *, actor_id: uuid.UUID, client_id: uuid.UUID, key: str,
                      title: str) -> None:
    """The row could not be committed after its object was stored: queue the object for deletion."""
    from app.services.parent_deletion import queue_storage_cleanup

    try:
        await session.rollback()
        await queue_storage_cleanup(session, actor_id=actor_id, account_id=client_id, keys=[key], title=title)
        await session.commit()
    except Exception:  # noqa: BLE001 — the orphan report (B13) still finds it; never mask the first error
        log.exception("agreement upload: the compensating cleanup could not be queued")
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass


def snapshot(row: Agreement, file_hash: str | None) -> AgreementFileVersion:
    """The history entry for the row's current version, with where it came from and its note."""
    return AgreementFileVersion(
        agreement_id=row.id, version_no=row.version_no, file_key=row.file_key, filename=row.filename,
        file_size=row.file_size, file_hash=file_hash, uploaded_by=row.uploaded_by, uploaded_at=row.uploaded_at,
        source=row.source, standard_agreement_id=row.standard_agreement_id, batch_id=row.batch_id, note=row.note)


async def _provenance(session: AsyncSession, source: str | None, standard_id: uuid.UUID | None,
                      batch_id: uuid.UUID | None) -> dict[str, Any]:
    version = label = None
    if standard_id is not None:
        version = await session.scalar(select(StandardAgreement.version_no).where(StandardAgreement.id == standard_id))
    if batch_id is not None:
        label = await session.scalar(select(AgreementBatch.label).where(AgreementBatch.id == batch_id))
    return {"source": source or "client", "standard_version": version, "batch": label}


# --- writes -----------------------------------------------------------------------------------


async def store_client_copy(
    session: AsyncSession, s3, *, actor: User, client_id: uuid.UUID, kind: str, checked: CheckedFile,
    note: str | None = None, agreement_id: uuid.UUID | None = None, expected_version: int | None = None,
) -> Agreement:
    """The client's own copy: a first copy, a new version, or a replacement for a standard copy or a mark.

    The caller has authorised the client and checked the file (authorise first, so a caller who may not see
    the client learns nothing about the file rules). ``agreement_id`` / ``expected_version`` are the legacy
    ``/agreements/{id}/replace`` guards: both are checked under the lock, before anything is stored.
    """
    note = clean_note(note)
    actor_id = actor.id  # read now: the compensation below runs after a rollback, which expires instances
    client = await lock_client(session, actor, client_id)
    row = await _locked_row(session, client_id, kind)
    if agreement_id is not None and (row is None or row.id != agreement_id):
        raise HTTPException(404, "agreement not found")
    if expected_version is not None and row is not None and row.version_no != expected_version:
        raise HTTPException(409, "Document was replaced; reload before replacing it again")
    mark = await _active_mark(session, client_id, kind)
    identity = row.id if row is not None else uuid.uuid4()
    key = client_object_key(identity, checked.stored_name, await fixture_run_id(session, client_id))
    await _put(s3, key, checked)
    now = datetime.now(UTC)
    try:
        before: dict[str, Any] | None = None
        if row is None:
            row = Agreement(id=identity, client_id=client_id, kind=kind, file_key=key,
                            filename=checked.display_name, file_size=checked.size, uploaded_by=actor.id,
                            uploaded_at=now, version_no=1, source="client", note=note)
            session.add(row)
            await session.flush()
            action = audit.CLIENT_UPLOADED
        else:
            if await session.get(AgreementFileVersion, (row.id, row.version_no)) is None:
                session.add(snapshot(row, None))  # a root written before version history existed
            before = {
                "client_id": str(client_id), "client_name": client.name, "kind": kind,
                "version_no": row.version_no, "filename": row.filename, "file_key": row.file_key,
                **await _provenance(session, row.source, row.standard_agreement_id, row.batch_id),
            }
            row.version_no += 1
            row.file_key, row.filename, row.file_size = key, checked.display_name, checked.size
            row.uploaded_by, row.uploaded_at = actor.id, now
            row.source, row.standard_agreement_id, row.batch_id, row.note = "client", None, None, note
            action = audit.CLIENT_REPLACED
        session.add(snapshot(row, checked.sha256))
        if mark is not None:
            # The client copy takes the mark's place; the mark stays in history (soft removal).
            mark.removed_at, mark.removed_by = now, actor.id
            before = {**(before or {"client_id": str(client_id), "client_name": client.name, "kind": kind}),
                      "mark": {"reason": mark.reason, "source": mark.source,
                               "marked_on": mark.marked_on.isoformat() if mark.marked_on else None}}
        await session.flush()
        await audit.record(
            session, actor_id=actor.id, action=action, entity="agreement", entity_id=row.id, before=before,
            after={"client_id": str(client_id), "client_name": client.name, "kind": kind,
                   "filename": row.filename, "file_size": row.file_size, "version_no": row.version_no,
                   "file_hash": checked.sha256, "file_key": row.file_key, "source": "client", "note": note})
        await session.commit()
    except Exception:
        await _compensate(session, actor_id=actor_id, client_id=client_id, key=key, title=checked.display_name)
        raise
    return row


async def attach_standard(session: AsyncSession, *, actor: User, client_id: uuid.UUID, kind: str) -> Agreement:
    """Attach the current standard copy to one client: a row pointing at the shared object, no file copied."""
    client = await lock_client(session, actor, client_id)
    standard = await session.scalar(
        select(StandardAgreement).where(StandardAgreement.kind == kind)
        .order_by(StandardAgreement.version_no.desc()).limit(1))
    if standard is None:
        raise HTTPException(404, f"No standard {kind} has been uploaded yet.")
    if await _locked_row(session, client_id, kind) is not None or await _active_mark(session, client_id, kind):
        raise HTTPException(409, f"This client already has an {kind}.")
    row = Agreement(id=uuid.uuid4(), client_id=client_id, kind=kind, file_key=standard.file_key,
                    filename=standard.filename, file_size=standard.file_size, uploaded_by=actor.id,
                    uploaded_at=datetime.now(UTC), version_no=1, source="standard",
                    standard_agreement_id=standard.id)
    session.add(row)
    await session.flush()
    session.add(snapshot(row, standard.sha256))
    await session.flush()
    await audit.record(
        session, actor_id=actor.id, action=audit.STANDARD_ATTACHED, entity="agreement", entity_id=row.id,
        after={"client_id": str(client_id), "client_name": client.name, "kind": kind, "filename": row.filename,
               "file_size": row.file_size, "source": "standard", "standard_version": standard.version_no,
               "batch": None})
    await session.commit()
    return row


async def set_mark(session: AsyncSession, *, actor: User, client_id: uuid.UUID, kind: str, reason: str,
                   marked_on: date, note: str | None, now: datetime | None = None) -> AgreementMark:
    """Mark a kind covered with no file. Replaces an earlier mark; refused while the client holds a file."""
    if reason not in MARK_REASONS_API:
        raise HTTPException(422, "Choose a reason from the list.")
    if marked_on > business_today(now):
        raise HTTPException(422, "The date cannot be in the future.")
    note = clean_note(note)
    client = await lock_client(session, actor, client_id)
    if await _locked_row(session, client_id, kind) is not None:
        raise HTTPException(409, f"This client holds an {kind} file. Remove the file first, then mark the {kind} covered.")
    previous = await _active_mark(session, client_id, kind)
    stamp = datetime.now(UTC)
    before = None
    if previous is not None:
        previous.removed_at, previous.removed_by = stamp, actor.id
        before = {"reason": previous.reason, "source": previous.source, "note": previous.note,
                  "marked_on": previous.marked_on.isoformat() if previous.marked_on else None,
                  "hubspot_value": previous.hubspot_value}
        await session.flush()  # the partial unique index allows one ACTIVE mark: retire the old one first
    mark = AgreementMark(id=uuid.uuid4(), client_id=client_id, kind=kind, reason=reason, note=note,
                         marked_on=marked_on, marked_by=actor.id, source="dealgate", created_at=stamp)
    session.add(mark)
    await session.flush()
    await audit.record(
        session, actor_id=actor.id, action=audit.MARKED, entity="agreement_mark", entity_id=mark.id, before=before,
        after={"client_id": str(client_id), "client_name": client.name, "kind": kind, "reason": reason,
               "marked_on": marked_on.isoformat(), "note": note, "source": "dealgate"})
    await session.commit()
    return mark


async def remove_mark(session: AsyncSession, *, actor: User, client_id: uuid.UUID, kind: str) -> AgreementMark:
    """Remove the active mark (soft: it stays in history)."""
    client = await lock_client(session, actor, client_id)
    mark = await _active_mark(session, client_id, kind)
    if mark is None:
        raise HTTPException(404, f"There is no {kind} mark to remove.")
    mark.removed_at, mark.removed_by = datetime.now(UTC), actor.id
    await session.flush()
    await audit.record(
        session, actor_id=actor.id, action=audit.MARK_REMOVED, entity="agreement_mark", entity_id=mark.id,
        before={"reason": mark.reason, "source": mark.source, "note": mark.note,
                "marked_on": mark.marked_on.isoformat() if mark.marked_on else None,
                "hubspot_value": mark.hubspot_value},
        after={"client_id": str(client_id), "client_name": client.name, "kind": kind, "source": mark.source})
    await session.commit()
    return mark


@dataclass
class Detached:
    client_id: uuid.UUID
    kind: str
    job: Any | None  # the client copy's deletion job (202); None when a standard attachment was removed (200)


async def detach(session: AsyncSession, *, actor: User, client_id: uuid.UUID | None = None,
                 kind: str | None = None, agreement_id: uuid.UUID | None = None) -> Detached:
    """Detach a kind's file from a client (by client and kind, or by the legacy agreement id)."""
    from app.services.deletion_storage import agreement_bucket, key_is_referenced
    from app.services.parent_deletion import queue_storage_cleanup, request_agreement_deletion

    if agreement_id is not None:
        found = (await session.execute(
            select(Agreement.client_id, Agreement.kind).where(Agreement.id == agreement_id))).first()
        if found is None:
            raise HTTPException(404, "agreement not found")
        await authorize_client(session, actor, found[0])
        client_id, kind = found[0], found[1]
    if client_id is None or kind is None:
        raise HTTPException(404, "agreement not found")
    client = await lock_client(session, actor, client_id)
    row = await _locked_row(session, client_id, kind)
    if row is None or (agreement_id is not None and row.id != agreement_id):
        raise HTTPException(404, "agreement not found" if agreement_id is not None
                            else f"No {kind} is attached to this client.")
    if row.source != "standard":
        job = await request_agreement_deletion(session, actor_id=actor.id, agreement=row, client_name=client.name)
        await session.commit()
        return Detached(client_id=client_id, kind=kind, job=job)
    described = {"client_id": str(client_id), "client_name": client.name, "kind": kind, "filename": row.filename,
                 "version_no": row.version_no,
                 **await _provenance(session, row.source, row.standard_agreement_id, row.batch_id)}
    versions = (await session.scalars(
        select(AgreementFileVersion.file_key).where(AgreementFileVersion.agreement_id == row.id))).all()
    keys = {row.file_key, *versions}
    identity = row.id
    await session.execute(delete(AgreementFileVersion).where(AgreementFileVersion.agreement_id == identity))
    await session.delete(row)
    await session.flush()
    # The shared standard object stays (standard_agreement points at it). Anything else this row's history
    # alone referenced would be orphaned, so it is queued like any other detached file.
    loose = [k for k in sorted(keys) if not await key_is_referenced(session, agreement_bucket(), k)]
    if loose:
        await queue_storage_cleanup(session, actor_id=actor.id, account_id=client_id, keys=loose,
                                    title=described["filename"], subject_type="agreement_detach")
    await audit.record(session, actor_id=actor.id, action=audit.DETACHED, entity="agreement",
                       entity_id=identity, before=None, after=described)
    await session.commit()
    return Detached(client_id=client_id, kind=kind, job=None)


async def set_relationship(session: AsyncSession, *, actor: User, client_id: uuid.UUID, relationship: str,
                           note: str | None) -> bool:
    """A writer's correction: existing or net new, basis ``manual``. Attaches nothing.

    Only a stored manual value equal to the request is a no-op (False, nothing audited). A provisional value shown
    before the cutover is computed live, so saving the same word there stores it by hand."""
    if relationship not in ("existing", "net_new"):
        raise HTTPException(422, "Choose existing or net new.")
    note = clean_note(note)
    client = await lock_client(session, actor, client_id)
    if client.relationship == relationship and client.relationship_basis == "manual":
        await session.commit()
        return False
    before = {"relationship": client.relationship, "relationship_basis": client.relationship_basis}
    client.relationship, client.relationship_basis = relationship, "manual"
    client.relationship_set_by, client.relationship_set_at = actor.id, datetime.now(UTC)
    await session.flush()
    await audit.record(
        session, actor_id=actor.id, action=audit.RELATIONSHIP_CHANGED, entity="client", entity_id=client_id,
        before=before, after={"client_id": str(client_id), "client_name": client.name,
                              "relationship": relationship, "relationship_basis": "manual", "note": note})
    await session.commit()
    return True


# --- downloads (audited) ----------------------------------------------------------------------


async def audited_link(session: AsyncSession, s3, *, actor: User, client: Client, row: Agreement,
                       version: AgreementFileVersion | None = None) -> dict[str, Any]:
    """A presigned link (300 s) for the row's current file or one of its versions, recorded in the audit log."""
    file_key = version.file_key if version is not None else row.file_key
    file_name = version.filename if version is not None else row.filename
    try:
        url = s3.generate_download_url(file_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, STORAGE_UNAVAILABLE) from exc
    if version is not None:
        prior = await _provenance(session, version.source, version.standard_agreement_id, version.batch_id)
    else:
        prior = await _provenance(session, row.source, row.standard_agreement_id, row.batch_id)
    await audit.record(
        session, actor_id=actor.id, action=audit.DOWNLOADED, entity="agreement", entity_id=row.id,
        after={"client_id": str(client.id), "client_name": client.name, "kind": row.kind, "filename": file_name,
               "version_no": version.version_no if version is not None else row.version_no, **prior})
    await session.commit()
    return {"url": url, "expires_in_seconds": DOWNLOAD_TTL_SECONDS, "file_name": file_name}


async def client_download(session: AsyncSession, s3, *, actor: User, client_id: uuid.UUID,
                          kind: str) -> dict[str, Any]:
    await authorize_client(session, actor, client_id)
    client = await session.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(404, "client not found")
    row = await session.scalar(select(Agreement).where(Agreement.client_id == client_id, Agreement.kind == kind))
    if row is None:
        raise HTTPException(404, f"There is no {kind} file for this client.")
    return await audited_link(session, s3, actor=actor, client=client, row=row)


# --- the panel payload (shared by the Agreements page and the Pipeline client panel) ----------


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _version_text(kind: str, version: AgreementFileVersion, previous_source: str | None,
                  standard_version: int | None, batch_label: str | None) -> str:
    if (version.source or "client") == "standard":
        text = f"Standard {kind} v{standard_version} attached" if standard_version else f"Standard {kind} attached"
        return f"{text} (batch {batch_label})" if batch_label else text
    if version.version_no > 1 and previous_source == "standard":
        text = f"Standard copy replaced with a client copy: {version.filename}"
    elif version.version_no > 1 and previous_source is not None:
        text = f"Client copy version {version.version_no} uploaded: {version.filename}"
    else:
        text = f"Client copy uploaded: {version.filename}"
    return f"{text}. Note: {version.note}" if version.note else text


def _mark_text(mark: AgreementMark) -> str:
    if mark.source == "hubspot":
        return f"Marked covered per HubSpot msa_type “{mark.hubspot_value}”" if mark.hubspot_value else (
            "Marked covered per HubSpot")
    text = f"Marked covered: {audit.REASON_LABELS.get(mark.reason, mark.reason)}"
    return f"{text}. Note: {mark.note}" if mark.note else text


async def load_history(session: AsyncSession, client_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    """Every version and every mark (removed ones included) per kind, newest first. Two statements."""
    uploader = aliased(User, name="history_uploader")
    versions = (await session.execute(
        select(AgreementFileVersion, Agreement.kind, StandardAgreement.version_no, AgreementBatch.label,
               uploader.name, uploader.email)
        .join(Agreement, Agreement.id == AgreementFileVersion.agreement_id)
        .outerjoin(StandardAgreement, StandardAgreement.id == AgreementFileVersion.standard_agreement_id)
        .outerjoin(AgreementBatch, AgreementBatch.id == AgreementFileVersion.batch_id)
        .outerjoin(uploader, uploader.id == AgreementFileVersion.uploaded_by)
        .where(Agreement.client_id == client_id)
        .order_by(Agreement.kind, AgreementFileVersion.version_no)
    )).all()
    marker = aliased(User, name="history_marker")
    remover = aliased(User, name="history_remover")
    marks = (await session.execute(
        select(AgreementMark, marker.name, marker.email, remover.name, remover.email)
        .outerjoin(marker, marker.id == AgreementMark.marked_by)
        .outerjoin(remover, remover.id == AgreementMark.removed_by)
        .where(AgreementMark.client_id == client_id)
    )).all()
    entries: dict[str, list[tuple[datetime, int, dict[str, Any]]]] = {k: [] for k in KINDS}
    order = 0
    previous: dict[str, tuple[int, str]] = {}
    for version, kind, standard_version, label, name, email in versions:
        if kind not in entries:
            continue
        prior = previous.get(kind)
        prior_source = prior[1] if prior and prior[0] == version.version_no - 1 else None
        previous[kind] = (version.version_no, version.source or "client")
        order += 1
        entries[kind].append((_aware(version.uploaded_at), order, {
            "at": iso_z(version.uploaded_at), "by": person(name, email),
            "what": _version_text(kind, version, prior_source, standard_version, label)}))
    for mark, m_name, m_email, r_name, r_email in marks:
        if mark.kind not in entries:
            continue
        order += 1
        entries[mark.kind].append((_aware(mark.created_at), order, {
            "at": iso_z(mark.created_at), "by": person(m_name, m_email), "what": _mark_text(mark)}))
        if mark.removed_at is not None:
            order += 1
            entries[mark.kind].append((_aware(mark.removed_at), order, {
                "at": iso_z(mark.removed_at), "by": person(r_name, r_email), "what": "Mark removed"}))
    return {k: [entry for _at, _n, entry in sorted(v, key=lambda e: (e[0], e[1]), reverse=True)]
            for k, v in entries.items()}


def doc_card(pop: Population, facts: ClientFacts, kind: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    status = facts.status
    detail = facts.docs[kind]
    has_row = detail.agreement_id is not None
    has_mark = detail.mark_id is not None
    standard = pop.standard.get(kind)
    return {
        "kind": kind,
        "state": status.state(kind),
        "agreement_id": str(detail.agreement_id) if has_row else None,
        "file_name": detail.file_name if has_row else None,
        "file_size": detail.file_size if has_row else None,
        "source": detail.source if has_row else None,
        "standard_version": detail.standard_version if has_row and detail.source == "standard" else None,
        "batch_id": detail.batch_label if has_row else None,
        "version_no": detail.version_no if has_row else None,
        "uploaded_by": detail.uploaded_by if has_row else None,
        "uploaded_at": iso_z(detail.uploaded_at) if has_row else None,
        "mark": {
            "reason": detail.mark_reason,
            "note": detail.mark_note,
            "marked_on": detail.mark_on.isoformat() if detail.mark_on else None,
            "marked_by": detail.mark_by,
            "source": detail.mark_source,
            "hubspot_value": detail.mark_hubspot_value,
            # additive: the reason in words
            "reason_label": audit.REASON_LABELS.get(detail.mark_reason or "", detail.mark_reason),
        } if has_mark else None,
        "hubspot_hint": facts.input.hubspot_msa_type if kind == "MSA" else None,
        "history": history,
        # additive
        "note": detail.note if has_row else None,
        "source_label": status.nda_label if kind == "NDA" else status.msa_label,
        "standard_available_version": standard.version if standard is not None else None,
    }


def client_payload(pop: Population, facts: ClientFacts, *, can_write: bool, is_admin: bool,
                   history: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    status = facts.status
    return {
        "client_id": str(status.client_id),
        "name": status.name,
        "relationship": status.relationship,
        "relationship_basis": status.relationship_basis,
        "relationship_set_by": facts.set_by,
        "relationship_set_at": iso_z(facts.set_at),
        "requirement": status.requirement,
        "needs_attention": status.needs_attention,
        "possible_duplicates": pop.duplicates_of(status.client_id),
        "deals": {
            "open": status.open_deals, "won": status.won_deals, "lost": status.lost_deals,
            "furthest_open_stage": status.furthest_open_stage,
            # additive: Hold has no stage of its own (furthest_open_stage reports 1-6), and the words
            "on_hold": status.on_hold, "stage_text": stage_text(status, pop.stage_labels),
            "count": status.deal_count,
        },
        "nda": doc_card(pop, facts, "NDA", history.get("NDA", [])),
        "msa": doc_card(pop, facts, "MSA", history.get("MSA", [])),
        "can_write": can_write,
        # additive
        "is_admin": is_admin,
        "stage_text": stage_text(status, pop.stage_labels),
        "provisional": status.provisional,
        "basis_text": basis_text(status, forecast=facts.forecast, set_by=facts.set_by),
        "business_units": business_unit_objects(status),
        "business_unit_note": business_unit_reason(facts),
        "flags": list(status.flags),
        "missing_kinds": [k for k in KINDS if status.state(k) == "missing"],
        "cutover": {"set": pop.cutover is not None, "date": pop.cutover.isoformat() if pop.cutover else None},
    }


async def panel(session: AsyncSession, viewer, client_id: uuid.UUID, *, can_write: bool,
                is_admin: bool) -> dict[str, Any]:
    """GET /clients/{id}/agreements: 404 when the caller cannot see the client."""
    pop = await load_agreement_population(session, viewer)
    facts = pop.clients.get(client_id)
    if facts is None:
        raise HTTPException(404, "client not found")
    return client_payload(pop, facts, can_write=can_write, is_admin=is_admin,
                          history=await load_history(session, client_id))


async def card(session: AsyncSession, viewer, client_id: uuid.UUID, kind: str) -> dict[str, Any]:
    """The kind's card after a write, from the same shared service the panel uses."""
    pop = await load_agreement_population(session, viewer)
    facts = pop.clients.get(client_id)
    if facts is None:
        raise HTTPException(404, "client not found")
    history = await load_history(session, client_id)
    return doc_card(pop, facts, kind, history.get(kind, []))


__all__ = [
    "ADMIN_ROLES", "DOWNLOAD_TTL_SECONDS", "Detached", "MARK_REASONS_API", "NOTE_MAX", "READ_ROLES", "Reader",
    "WRITE_ROLES", "attach_standard", "audited_link", "authorize_client", "card", "clean_note",
    "client_download", "client_object_key", "client_payload", "detach", "doc_card", "fixture_run_id",
    "load_history", "lock_client", "panel", "reader", "remove_mark", "set_mark", "set_relationship", "snapshot",
    "store_client_copy", "test_identity_blocked",
]
