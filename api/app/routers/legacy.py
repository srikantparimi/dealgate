"""S6 legacy import endpoints.

Finance/CEO/SystemAdmin only (:data:`app.services.legacy_import.LEGACY_ROLES`).
Business logic lives in ``app.services.legacy_import``; this router does
role-gating, shape conversion and audit emission (see agreements.py).

Endpoints:

- ``POST /legacy/upload-url``               — SigV4 pre-signed PUT URL for a
  single SOW PDF/DOCX. Callers loop over their file list to bulk-upload.
- ``POST /legacy/batches``                  — create a new batch envelope.
- ``POST /legacy/batches/{id}/sows``        — associate uploaded SOWs
  (already in S3) with the batch, creating ``sow_version`` rows tagged
  ``legacy=True, approval_evidenced=False``.
- ``POST /legacy/batches/{id}/excel``       — parse + validate + import the
  Excel of resource lines. All-or-nothing per file.
- ``GET  /legacy/batches/{id}/reconciliation`` — the report.
- ``POST /legacy/batches/{id}/approve``     — freeze the batch. Does NOT
  create approvals for the legacy SOWs (blueprint §13 rollout rule).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.s3_sow import (
    SowS3,
    UnsupportedContentType,
    get_sow_s3,
)
from app.services.legacy_import import (
    LEGACY_ROLES,
    LegacyImportError,
    ReconciliationReport,
    SowUpload,
    approve_batch,
    assert_role,
    bulk_upload_sows,
    create_batch,
    import_excel,
    load_batch,
    reconcile,
)

router = APIRouter(prefix="/legacy", tags=["legacy"])


# --- role helper ---------------------------------------------------------


async def _finance_user(
    user: AuthUser = Depends(current_user),
) -> AuthUser:
    assert_role(user.groups)
    return user


# --- schemas -------------------------------------------------------------


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(examples=["application/pdf"])


class UploadUrlResponse(BaseModel):
    url: str
    s3_key: str
    method: str
    expires_in: int
    required_headers: dict[str, str] | None = None


class BatchRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    uploaded_by: uuid.UUID
    status: str
    sow_count: int
    resource_line_count: int
    errors: list[dict[str, Any]] | None = None
    approved_by: uuid.UUID | None = None


class SowAttachRow(BaseModel):
    s3_key: str
    filename: str
    sow_ref: str
    client_name: str | None = None


class AttachSowsBody(BaseModel):
    files: list[SowAttachRow] = Field(default_factory=list)


class AttachSowsResponse(BaseModel):
    batch: BatchRow
    versions: list[uuid.UUID]


class ExcelImportResponse(BaseModel):
    imported: int
    sow_refs: list[str]
    errors: list[dict[str, Any]] = Field(default_factory=list)


class ProjectGmRow(BaseModel):
    sow_ref: str
    revenue_us: str
    revenue_india: str
    cost_us: str
    cost_india: str
    gm_us: str | None
    gm_india: str | None
    below_floor: bool
    failing: list[str]
    complete: bool


class ReconciliationResponse(BaseModel):
    batch_id: uuid.UUID
    status: str
    matched: list[dict[str, Any]]
    unmatched_sows: list[dict[str, Any]]
    orphaned_resource_lines: list[dict[str, Any]]
    project_gm: list[ProjectGmRow]
    below_floor: list[str]


# --- helpers -------------------------------------------------------------


def _batch_row(batch: Any) -> BatchRow:
    return BatchRow(
        id=batch.id,
        uploaded_by=batch.uploaded_by,
        status=batch.status,
        sow_count=batch.sow_count,
        resource_line_count=batch.resource_line_count,
        errors=batch.errors,
        approved_by=batch.approved_by,
    )


def _reconciliation_row(report: ReconciliationReport) -> ReconciliationResponse:
    return ReconciliationResponse(
        batch_id=report.batch_id,
        status=report.status,
        matched=report.matched,
        unmatched_sows=report.unmatched_sows,
        orphaned_resource_lines=report.orphaned_resource_lines,
        project_gm=[
            ProjectGmRow(
                sow_ref=snap.sow_ref,
                revenue_us=str(snap.revenue_us),
                revenue_india=str(snap.revenue_india),
                cost_us=str(snap.cost_us),
                cost_india=str(snap.cost_india),
                gm_us=str(snap.gm_us) if snap.gm_us is not None else None,
                gm_india=str(snap.gm_india) if snap.gm_india is not None else None,
                below_floor=snap.below_floor,
                failing=list(snap.failing),
                complete=snap.complete,
            )
            for snap in report.project_gm
        ],
        below_floor=report.below_floor,
    )


# --- endpoints -----------------------------------------------------------


@router.post("/upload-url", response_model=UploadUrlResponse)
async def issue_upload_url(
    body: UploadUrlRequest,
    _user: AuthUser = Depends(_finance_user),
    s3: SowS3 = Depends(get_sow_s3),
) -> UploadUrlResponse:
    # One key per upload; scoped under a synthetic id so the pattern matches
    # non-legacy uploads (opportunity-prefixed). We use a fresh UUID because
    # the target opportunity is created later inside :func:`bulk_upload_sows`.
    scope_id = uuid.uuid4()
    try:
        signed = s3.generate_upload_url(scope_id, body.filename, body.content_type)
    except UnsupportedContentType as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return UploadUrlResponse(
        url=signed.url,
        s3_key=signed.s3_key,
        method=signed.method,
        expires_in=signed.expires_in,
        required_headers=signed.required_headers,
    )


@router.post("/batches", response_model=BatchRow, status_code=201)
async def create_legacy_batch(
    actor: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> BatchRow:
    batch = await create_batch(session, actor_id=actor.id)
    return _batch_row(batch)


@router.post("/batches/{batch_id}/sows", response_model=AttachSowsResponse)
async def attach_sows(
    batch_id: uuid.UUID,
    body: AttachSowsBody,
    actor: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> AttachSowsResponse:
    batch = await load_batch(session, batch_id)
    uploads = [
        SowUpload(
            s3_key=f.s3_key,
            filename=f.filename,
            sow_ref=f.sow_ref,
            client_name=f.client_name,
        )
        for f in body.files
    ]
    versions = await bulk_upload_sows(
        session, actor_id=actor.id, batch=batch, uploads=uploads
    )
    return AttachSowsResponse(
        batch=_batch_row(batch),
        versions=[v.id for v in versions],
    )


@router.post("/batches/{batch_id}/excel", response_model=ExcelImportResponse)
async def import_excel_endpoint(
    batch_id: uuid.UUID,
    file: UploadFile = File(..., alias="file"),
    actor: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> ExcelImportResponse:
    batch = await load_batch(session, batch_id)
    payload = await file.read()
    try:
        result = await import_excel(
            session, actor_id=actor.id, batch=batch, xlsx_bytes=payload
        )
    except LegacyImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc
    return ExcelImportResponse(
        imported=result["imported"],
        sow_refs=result["sow_refs"],
        errors=[],
    )


@router.get(
    "/batches/{batch_id}/reconciliation",
    response_model=ReconciliationResponse,
)
async def get_reconciliation(
    batch_id: uuid.UUID,
    _user: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> ReconciliationResponse:
    report = await reconcile(session, batch_id)
    return _reconciliation_row(report)


@router.post(
    "/batches/{batch_id}/approve",
    response_model=ReconciliationResponse,
)
async def approve(
    batch_id: uuid.UUID,
    actor: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> ReconciliationResponse:
    report = await approve_batch(session, actor_id=actor.id, batch_id=batch_id)
    return _reconciliation_row(report)


__all__ = ["router", "LEGACY_ROLES"]
