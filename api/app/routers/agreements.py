"""NDA and MSA documents: the batch attach of the standard copies and the legacy document routes (S24-AG1).

Every write goes through ``app.services.agreements_service`` (the per-client rules, B5 file rules, compensating
delete, audit) or ``app.services.agreement_batches`` (B7); nothing here classifies a client. Roles (B11, enforced
here whatever the page shows): every role reads and downloads; Legal and SystemAdmin write; SystemAdmin alone
runs and undoes batches. Reads never write, except downloads, which record who downloaded what.

Routes (the workspace, export, documents, activity and standard routes live in ``agreements_workspace``; the
per-client routes in ``client_agreements``):

- ``POST /agreements/batches`` — dry run (default, 200) or start the job (202). ``GET /agreements/batches``,
  ``GET /agreements/batches/{label}``, ``POST /agreements/batches/{label}/undo`` (202).
- Legacy, kept for existing callers with the same rules: ``GET /agreements`` (+ source, standard version, batch
  label, note), ``POST /agreements`` (a kind the client already holds becomes a new version),
  ``POST /agreements/{id}/replace``, ``GET /agreements/{id}/versions``, the two download routes (audited) and
  ``DELETE /agreements/{id}`` (a client copy starts a deletion job, 202; a standard attachment is removed, 200).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.s3_evidence import EvidenceS3, get_evidence_s3
from app.models.agreements import AgreementBatch, StandardAgreement
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.user import User
from app.services import agreement_batches, agreements_service
from app.services.agreement_files import check_upload
from app.services.agreement_status import iso_z
from app.services.agreements_service import ADMIN_ROLES, READ_ROLES, WRITE_ROLES
from app.services.test_fixtures import account_scope, user_allowed
from app.services.user_identity import display_user_name
from app.services.user_provisioning import ensure_user

router = APIRouter(prefix="/agreements", tags=["agreements"])

# Kept under their S17 names for importers.
_READ_ROLES = READ_ROLES
_MUTATE_ROLES = WRITE_ROLES
_ALLOWED_KINDS: frozenset[str] = frozenset({"NDA", "MSA"})


class AgreementRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    kind: Literal["NDA", "MSA"]
    filename: str
    file_size: int
    uploaded_by: uuid.UUID
    uploaded_by_name: str
    uploaded_at: str
    version_no: int
    # S24-AG1 (additive): where the current version came from; batch is the label (AG-0001), never an id.
    source: Literal["client", "standard"] = "client"
    standard_version: int | None = None
    batch_id: str | None = None
    note: str | None = None


class AgreementListResponse(BaseModel):
    items: list[AgreementRow]


async def _actor(session: AsyncSession, user: AuthUser) -> User:
    actor = await ensure_user(session, user)
    # Release identity/audit locks before reading or locking business records.
    await session.commit()
    return actor


async def _authorize_client(session: AsyncSession, actor, client_id: uuid.UUID) -> None:
    if not user_allowed(actor, await account_scope(session, client_id)):
        raise HTTPException(status_code=404, detail="client not found")


async def _labels(session: AsyncSession, rows) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, str]]:
    standard_ids = {r.standard_agreement_id for r in rows if r.standard_agreement_id}
    batch_ids = {r.batch_id for r in rows if r.batch_id}
    versions = dict((await session.execute(select(StandardAgreement.id, StandardAgreement.version_no)
                                           .where(StandardAgreement.id.in_(standard_ids)))).all()) if standard_ids else {}
    labels = dict((await session.execute(select(AgreementBatch.id, AgreementBatch.label)
                                         .where(AgreementBatch.id.in_(batch_ids)))).all()) if batch_ids else {}
    return versions, labels


def _serialize(row: Agreement, client: Client, uploader: User | None, versions: dict | None = None,
               labels: dict | None = None) -> AgreementRow:
    return AgreementRow(
        id=row.id,
        client_id=row.client_id,
        client_name=client.name,
        kind=row.kind,  # type: ignore[arg-type]
        filename=row.filename,
        file_size=row.file_size,
        uploaded_by=row.uploaded_by,
        uploaded_by_name=display_user_name(uploader.name, uploader.email) if uploader else "Unassigned",
        uploaded_at=iso_z(row.uploaded_at) or "",
        version_no=row.version_no,
        source=row.source or "client",  # type: ignore[arg-type]
        standard_version=(versions or {}).get(row.standard_agreement_id) if row.standard_agreement_id else None,
        batch_id=(labels or {}).get(row.batch_id) if row.batch_id else None,
        note=row.note,
    )


async def _serialize_one(session: AsyncSession, row: Agreement, client: Client, uploader: User | None) -> AgreementRow:
    versions, labels = await _labels(session, [row])
    return _serialize(row, client, uploader, versions, labels)


# --- batches (B7) — registered before the /{agreement_id} routes ------------------------------


class BatchRequestBody(BaseModel):
    kinds: list[Literal["NDA", "MSA"]] = Field(min_length=1)
    dry_run: bool = True
    include_net_new_past_stage_1: bool = False
    include_client_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_client_ids: list[uuid.UUID] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=80)
    confirm: str | None = None


BatchLauncher = Callable[[uuid.UUID, str], Awaitable[None]]


def get_batch_launcher() -> BatchLauncher:
    """Starts the job after the 202. Tests override it to run the job inline on their own database."""
    return agreement_batches.launch_in_background


@router.post("/batches")
async def post_batch(
    body: BatchRequestBody,
    response: Response,
    user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_session),
    launch: BatchLauncher = Depends(get_batch_launcher),
) -> dict[str, Any]:
    if body.dry_run:
        viewer = await agreements_service.reader(session, user)
        return await agreement_batches.dry_run(
            session, viewer, kinds=body.kinds, include_net_new=body.include_net_new_past_stage_1,
            include_ids=body.include_client_ids, exclude_ids=body.exclude_client_ids)
    actor = await _actor(session, user)
    batch_id, created = await agreement_batches.start(
        session, actor=actor, kinds=body.kinds, include_net_new=body.include_net_new_past_stage_1,
        include_ids=body.include_client_ids, exclude_ids=body.exclude_client_ids,
        idempotency_key=body.idempotency_key, confirm=body.confirm)
    if created:
        await launch(batch_id, "run")
    response.status_code = status.HTTP_202_ACCEPTED
    return await agreement_batches.batch_payload_by_id(session, batch_id)


@router.get("/batches")
async def list_batches(
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"items": await agreement_batches.batch_payloads(session)}


@router.get("/batches/{label}")
async def get_batch(
    label: str,
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    items = await agreement_batches.batch_payloads(session, label=label.strip().upper())
    if not items:
        raise HTTPException(404, "Unknown batch")
    return items[0]


@router.post("/batches/{label}/undo", status_code=status.HTTP_202_ACCEPTED)
async def undo_batch(
    label: str,
    user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_session),
    launch: BatchLauncher = Depends(get_batch_launcher),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    batch_id, started = await agreement_batches.start_undo(session, actor=actor, label=label.strip().upper())
    if started:
        await launch(batch_id, "undo")
    return await agreement_batches.batch_payload_by_id(session, batch_id)


# --- legacy document routes -------------------------------------------------------------------


@router.get("", response_model=AgreementListResponse)
async def list_agreements(
    client_id: uuid.UUID | None = Query(default=None),
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AgreementListResponse:
    viewer = await agreements_service.reader(session, _user)
    if client_id is not None:
        await _authorize_client(session, viewer, client_id)
    stmt = select(Agreement).order_by(Agreement.uploaded_at.desc())
    if client_id is not None:
        stmt = stmt.where(Agreement.client_id == client_id)
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return AgreementListResponse(items=[])
    client_ids = {r.client_id for r in rows}
    uploader_ids = {r.uploaded_by for r in rows}
    clients = {c.id: c for c in (await session.execute(select(Client).where(Client.id.in_(client_ids)))).scalars()}
    for identity in list(clients):
        if not user_allowed(viewer, await account_scope(session, identity)):
            del clients[identity]
    users = {u.id: u for u in (await session.execute(select(User).where(User.id.in_(uploader_ids)))).scalars()}
    visible = [r for r in rows if r.client_id in clients]
    versions, labels = await _labels(session, visible)
    return AgreementListResponse(items=[
        _serialize(r, clients[r.client_id], users.get(r.uploaded_by), versions, labels) for r in visible])


@router.post("", response_model=AgreementRow, status_code=status.HTTP_201_CREATED)
async def upload_agreement(
    client_id: uuid.UUID = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> AgreementRow:
    """A client's own copy. A kind the client already holds becomes a new version of the same agreement."""
    actor = await _actor(session, user)
    await _authorize_client(session, actor, client_id)
    kind_upper = kind.strip().upper()
    if kind_upper not in _ALLOWED_KINDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"kind must be one of {sorted(_ALLOWED_KINDS)}")
    client = await session.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="client not found")
    agreements_service.clean_note(note)
    checked = await check_upload(file)
    row = await agreements_service.store_client_copy(session, s3, actor=actor, client_id=client_id,
                                                     kind=kind_upper, checked=checked, note=note)
    return await _serialize_one(session, row, await session.get(Client, client_id), actor)


@router.post("/{agreement_id}/replace", response_model=AgreementRow)
async def replace_agreement(
    agreement_id: uuid.UUID,
    expected_version: int = Form(...),
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> AgreementRow:
    """A new version of this agreement (over a standard copy it becomes the client's own copy)."""
    actor = await _actor(session, user)
    existing = await session.get(Agreement, agreement_id)
    if existing is None:
        raise HTTPException(404, "agreement not found")
    client_id, kind = existing.client_id, existing.kind
    await _authorize_client(session, actor, client_id)
    agreements_service.clean_note(note)
    checked = await check_upload(file)
    row = await agreements_service.store_client_copy(
        session, s3, actor=actor, client_id=client_id, kind=kind, checked=checked, note=note,
        agreement_id=agreement_id, expected_version=expected_version)
    return await _serialize_one(session, row, await session.get(Client, client_id), actor)


@router.get("/{agreement_id}/versions")
async def agreement_versions(
    agreement_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await agreements_service.reader(session, user)
    row = await session.get(Agreement, agreement_id)
    if row is None:
        raise HTTPException(404, "agreement not found")
    await _authorize_client(session, viewer, row.client_id)
    versions = (await session.scalars(select(AgreementFileVersion)
        .where(AgreementFileVersion.agreement_id == agreement_id)
        .order_by(AgreementFileVersion.version_no.desc()))).all()
    users = {u.id: u for u in (await session.scalars(
        select(User).where(User.id.in_({v.uploaded_by for v in versions})))).all()} if versions else {}
    standard_versions, labels = await _labels(session, versions)
    items = []
    for version in versions:
        uploader = users.get(version.uploaded_by)
        items.append({
            "version_no": version.version_no, "filename": version.filename, "file_size": version.file_size,
            "file_hash": version.file_hash, "uploaded_by": str(version.uploaded_by),
            "uploaded_by_name": display_user_name(uploader.name, uploader.email) if uploader else "Unassigned",
            "uploaded_at": iso_z(version.uploaded_at),
            # S24-AG1 (additive)
            "source": version.source or "client",
            "standard_version": standard_versions.get(version.standard_agreement_id)
            if version.standard_agreement_id else None,
            "batch_id": labels.get(version.batch_id) if version.batch_id else None,
            "note": version.note,
        })
    return {"items": items}


async def _download(session: AsyncSession, s3, user: AuthUser, agreement_id: uuid.UUID,
                    version_no: int | None) -> dict[str, Any]:
    actor = await _actor(session, user)  # a download is recorded in the audit log: credit a real user
    row = await session.get(Agreement, agreement_id)
    if row is None:
        raise HTTPException(404, "agreement not found")
    await _authorize_client(session, actor, row.client_id)
    version = None
    if version_no is not None:
        version = await session.get(AgreementFileVersion, (agreement_id, version_no))
        if version is None:
            raise HTTPException(404, "document version not found")
    client = await session.get(Client, row.client_id)
    link = await agreements_service.audited_link(session, s3, actor=actor, client=client, row=row, version=version)
    return {**link, "filename": link["file_name"]}  # ``filename`` kept for S17 callers


@router.get("/{agreement_id}/versions/{version_no}/download")
async def download_agreement_version(
    agreement_id: uuid.UUID,
    version_no: int,
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, Any]:
    return await _download(session, s3, user, agreement_id, version_no)


@router.get("/{agreement_id}/download")
async def download_agreement(
    agreement_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, Any]:
    return await _download(session, s3, _user, agreement_id, None)


@router.delete("/{agreement_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_agreement(
    agreement_id: uuid.UUID,
    response: Response,
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
):
    """Detach through the shared service: a client copy starts a deletion job (202); a standard attachment
    removes only this client's row (200), because the stored object is shared."""
    from app.routers.deletion import _job_response

    actor = await _actor(session, user)
    result = await agreements_service.detach(session, actor=actor, agreement_id=agreement_id)
    if result.job is not None:
        return _job_response(result.job)
    response.status_code = status.HTTP_200_OK
    return await agreements_service.card(session, actor, result.client_id, result.kind)
