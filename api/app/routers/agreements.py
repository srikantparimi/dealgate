"""Agreements as a flat NDA/MSA document store (S17).

Contract: one row per uploaded file. Client + kind (NDA/MSA) + file. The
list is client, type, filename, uploaded by, uploaded date. No states,
owners, next actions, expiry dates or extraction — S16a's tracking is
gone. Nothing else in the app reads these rows to gate a decision.

Endpoints:

- ``POST   /agreements``             — multipart upload; picks client + kind + file.
- ``GET    /agreements``             — governance-role list (filterable by client).
- ``GET    /agreements/{id}/download`` — short-lived S3 GET url for the stored file.
- ``DELETE /agreements/{id}``        — SystemAdmin or Legal removes the row + S3 object.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.integrations.s3_evidence import EvidenceS3, UnsupportedContentType, get_evidence_s3
from app.integrations.s3_sow import MAX_SOW_BYTES
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.user import User
from app.services.user_identity import display_user_name
from app.services.user_provisioning import ensure_user
from app.services.test_fixtures import account_scope, user_allowed

router = APIRouter(prefix="/agreements", tags=["agreements"])

_READ_ROLES: tuple[str, ...] = (
    "Marketing",
    "Sales",
    "SalesLeader",
    "Presales",
    "Delivery",
    "HR",
    "Finance",
    "Legal",
    "CEO",
    "SystemAdmin",
)
_MUTATE_ROLES: tuple[str, ...] = ("Legal", "SystemAdmin")
_ALLOWED_KINDS: frozenset[str] = frozenset({"NDA", "MSA"})
_ALLOWED_CTS: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)


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


class AgreementListResponse(BaseModel):
    items: list[AgreementRow]


async def _actor(session: AsyncSession, user: AuthUser) -> User:
    actor = await ensure_user(session, user)
    # Release identity/audit locks before reading or locking business records.
    await session.commit()
    return actor


async def _authorize_client(session: AsyncSession, actor: User, client_id: uuid.UUID) -> None:
    if not user_allowed(actor, await account_scope(session, client_id)):
        raise HTTPException(status_code=404, detail="client not found")


async def _read_document(file: UploadFile) -> tuple[bytes, str]:
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_CTS:
        raise HTTPException(422, "Upload a PDF or a .docx Word document.")
    content = await file.read(MAX_SOW_BYTES + 1)
    if not content:
        raise HTTPException(422, "file is empty")
    if len(content) > MAX_SOW_BYTES:
        raise HTTPException(413, "Document exceeds the supported upload size")
    return content, content_type


async def _store_document(s3: EvidenceS3, identity: uuid.UUID, file: UploadFile, content_type: str, content: bytes) -> str:
    try:
        return await asyncio.to_thread(s3.put_object, identity, file.filename or "agreement", content_type, content)
    except UnsupportedContentType as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Document storage is unavailable") from exc


def _snapshot(row: Agreement, file_hash: str | None) -> AgreementFileVersion:
    return AgreementFileVersion(agreement_id=row.id, version_no=row.version_no,
        file_key=row.file_key, filename=row.filename, file_size=row.file_size,
        file_hash=file_hash, uploaded_by=row.uploaded_by, uploaded_at=row.uploaded_at)


async def _locked_agreement(session: AsyncSession, actor: User, identity: uuid.UUID) -> Agreement:
    account_id = await session.scalar(select(Agreement.client_id).where(Agreement.id == identity))
    if account_id is None:
        raise HTTPException(404, "agreement not found")
    await _authorize_client(session, actor, account_id)
    await session.scalar(select(Client).where(Client.id == account_id).with_for_update()
        .execution_options(populate_existing=True))
    row = await session.scalar(select(Agreement).where(Agreement.id == identity).with_for_update()
        .execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "agreement not found")
    await _authorize_client(session, actor, account_id)
    return row


def _serialize(row: Agreement, client: Client, uploader: User | None) -> AgreementRow:
    return AgreementRow(
        id=row.id,
        client_id=row.client_id,
        client_name=client.name,
        kind=row.kind,  # type: ignore[arg-type]
        filename=row.filename,
        file_size=row.file_size,
        uploaded_by=row.uploaded_by,
        uploaded_by_name=(
            display_user_name(uploader.name, uploader.email) if uploader else "Unassigned"
        ),
        uploaded_at=row.uploaded_at.isoformat() if row.uploaded_at else "",
        version_no=row.version_no,
    )


@router.get("", response_model=AgreementListResponse)
async def list_agreements(
    client_id: uuid.UUID | None = Query(default=None),
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AgreementListResponse:
    actor = await _actor(session, _user)
    if client_id is not None:
        await _authorize_client(session, actor, client_id)
    stmt = select(Agreement).order_by(Agreement.uploaded_at.desc())
    if client_id is not None:
        stmt = stmt.where(Agreement.client_id == client_id)
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return AgreementListResponse(items=[])
    client_ids = {r.client_id for r in rows}
    uploader_ids = {r.uploaded_by for r in rows}
    clients = {
        c.id: c
        for c in (
            await session.execute(select(Client).where(Client.id.in_(client_ids)))
        ).scalars()
    }
    for identity in list(clients):
        if not user_allowed(actor, await account_scope(session, identity)):
            del clients[identity]
    users = {
        u.id: u
        for u in (
            await session.execute(select(User).where(User.id.in_(uploader_ids)))
        ).scalars()
    }
    return AgreementListResponse(
        items=[
            _serialize(r, clients[r.client_id], users.get(r.uploaded_by))
            for r in rows
            if r.client_id in clients
        ]
    )


@router.post("", response_model=AgreementRow, status_code=status.HTTP_201_CREATED)
async def upload_agreement(
    client_id: uuid.UUID = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> AgreementRow:
    db_user = await _actor(session, user)
    await _authorize_client(session, db_user, client_id)
    kind_upper = kind.strip().upper()
    if kind_upper not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {sorted(_ALLOWED_KINDS)}",
        )
    client = await session.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="client not found")
    file_bytes, content_type = await _read_document(file)

    client = await session.scalar(select(Client).where(Client.id == client_id)
        .with_for_update().execution_options(populate_existing=True))
    await _authorize_client(session, db_user, client_id)
    agreement_id = uuid.uuid4()
    key = await _store_document(s3, agreement_id, file, content_type, file_bytes)

    row = Agreement(
        id=agreement_id,
        client_id=client_id,
        kind=kind_upper,
        file_key=key,
        filename=file.filename or "agreement",
        file_size=len(file_bytes),
        uploaded_by=db_user.id,
        uploaded_at=datetime.now(UTC),
        version_no=1,
    )
    session.add(row)
    await session.flush()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    session.add(_snapshot(row, file_hash))
    await append_audit(
        session,
        actor_id=db_user.id,
        action="agreement.uploaded",
        entity="agreement",
        entity_id=str(row.id),
        before=None,
        after={
            "client_id": str(client_id),
            "kind": kind_upper,
            "filename": row.filename,
            "file_size": row.file_size,
            "version_no": row.version_no,
            "file_hash": file_hash,
        },
    )
    await session.commit()
    return _serialize(row, client, db_user)


@router.post("/{agreement_id}/replace", response_model=AgreementRow)
async def replace_agreement(agreement_id: uuid.UUID, expected_version: int = Form(...),
    file: UploadFile = File(...), user: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session), s3: EvidenceS3 = Depends(get_evidence_s3)):
    actor = await _actor(session, user)
    existing = await session.get(Agreement, agreement_id)
    if existing is None:
        raise HTTPException(404, "agreement not found")
    await _authorize_client(session, actor, existing.client_id)
    content, content_type = await _read_document(file)
    row = await _locked_agreement(session, actor, agreement_id)
    if row.version_no != expected_version:
        raise HTTPException(409, "Document was replaced; reload before replacing it again")
    previous = await session.get(AgreementFileVersion, (row.id, row.version_no))
    if previous is None:
        # Preserve legacy roots without a snapshot; mixed old writers are not safe.
        session.add(_snapshot(row, None))
    before = {"version_no": row.version_no, "filename": row.filename, "file_key": row.file_key}
    key = await _store_document(s3, row.id, file, content_type, content)
    row.version_no += 1
    row.file_key, row.filename, row.file_size = key, file.filename or "agreement", len(content)
    row.uploaded_by, row.uploaded_at = actor.id, datetime.now(UTC)
    file_hash = hashlib.sha256(content).hexdigest()
    session.add(_snapshot(row, file_hash))
    await append_audit(session, actor_id=actor.id, action="agreement.replaced", entity="agreement",
        entity_id=str(row.id), before=before, after={"version_no": row.version_no,
        "filename": row.filename, "file_key": row.file_key, "file_hash": file_hash})
    await session.commit()
    return _serialize(row, await session.get(Client, row.client_id), actor)


@router.get("/{agreement_id}/versions")
async def agreement_versions(agreement_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*_READ_ROLES)), session: AsyncSession = Depends(get_session)):
    actor = await _actor(session, user)
    row = await session.get(Agreement, agreement_id)
    if row is None:
        raise HTTPException(404, "agreement not found")
    await _authorize_client(session, actor, row.client_id)
    versions = (await session.scalars(select(AgreementFileVersion)
        .where(AgreementFileVersion.agreement_id == agreement_id)
        .order_by(AgreementFileVersion.version_no.desc()))).all()
    items = []
    for version in versions:
        uploader = await session.get(User, version.uploaded_by)
        items.append({"version_no": version.version_no, "filename": version.filename,
            "file_size": version.file_size, "file_hash": version.file_hash,
            "uploaded_by": str(version.uploaded_by),
            "uploaded_by_name": display_user_name(uploader.name, uploader.email) if uploader else "Unassigned",
            "uploaded_at": version.uploaded_at.isoformat()})
    return {"items": items}


@router.get("/{agreement_id}/versions/{version_no}/download")
async def download_agreement_version(agreement_id: uuid.UUID, version_no: int,
    user: AuthUser = Depends(require_role(*_READ_ROLES)), session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3)):
    actor = await _actor(session, user)
    row = await session.get(Agreement, agreement_id)
    if row is None:
        raise HTTPException(404, "agreement not found")
    await _authorize_client(session, actor, row.client_id)
    version = await session.get(AgreementFileVersion, (agreement_id, version_no))
    if version is None:
        raise HTTPException(404, "document version not found")
    return {"url": s3.generate_download_url(version.file_key), "filename": version.filename}


@router.get("/{agreement_id}/download")
async def download_agreement(
    agreement_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, str]:
    actor = await _actor(session, _user)
    row = await session.get(Agreement, agreement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="agreement not found")
    await _authorize_client(session, actor, row.client_id)
    return {"url": s3.generate_download_url(row.file_key), "filename": row.filename}


@router.delete("/{agreement_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_agreement(
    agreement_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
):
    db_user = await _actor(session, user)
    row = await _locked_agreement(session, db_user, agreement_id)
    from app.services.parent_deletion import request_agreement_deletion
    from app.routers.deletion import _job_response
    job = await request_agreement_deletion(session, actor_id=db_user.id, agreement=row)
    await session.commit()
    return _job_response(job)
