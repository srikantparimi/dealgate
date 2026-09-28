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

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.integrations.s3_evidence import EvidenceS3, UnsupportedContentType, get_evidence_s3
from app.models.client import Agreement, Client
from app.models.user import User
from app.services.user_identity import display_user_name
from app.services.user_provisioning import ensure_user

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


class AgreementListResponse(BaseModel):
    items: list[AgreementRow]


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
    )


@router.get("", response_model=AgreementListResponse)
async def list_agreements(
    client_id: uuid.UUID | None = Query(default=None),
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AgreementListResponse:
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
    kind_upper = kind.strip().upper()
    if kind_upper not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {sorted(_ALLOWED_KINDS)}",
        )
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_CTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload a PDF or a .docx Word document.",
        )
    client = await session.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="client not found")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file is empty"
        )

    db_user = await ensure_user(session, user)
    agreement_id = uuid.uuid4()
    try:
        key = s3.put_object(agreement_id, file.filename or "agreement", content_type, file_bytes)
    except UnsupportedContentType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = Agreement(
        id=agreement_id,
        client_id=client_id,
        kind=kind_upper,
        file_key=key,
        filename=file.filename or "agreement",
        file_size=len(file_bytes),
        uploaded_by=db_user.id,
    )
    session.add(row)
    await session.flush()
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
        },
    )
    await session.commit()
    return _serialize(row, client, db_user)


@router.get("/{agreement_id}/download")
async def download_agreement(
    agreement_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, str]:
    row = await session.get(Agreement, agreement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="agreement not found")
    return {"url": s3.generate_download_url(row.file_key), "filename": row.filename}


@router.delete("/{agreement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agreement(
    agreement_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> None:
    row = await session.get(Agreement, agreement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="agreement not found")
    db_user = await ensure_user(session, user)
    before = {
        "client_id": str(row.client_id),
        "kind": row.kind,
        "filename": row.filename,
    }
    # Best-effort S3 delete; the DB row is the source of truth for existence.
    try:
        from app.integrations.s3_sow import _client

        _client().delete_object(Bucket=s3._bucket, Key=row.file_key)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — the audit + row delete still succeed.
        pass
    await session.delete(row)
    await append_audit(
        session,
        actor_id=db_user.id,
        action="agreement.deleted",
        entity="agreement",
        entity_id=str(agreement_id),
        before=before,
        after=None,
    )
    await session.commit()
