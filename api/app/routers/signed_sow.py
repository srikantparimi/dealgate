"""S5 E8 — signed SOW upload / verify / release API (build-guide §6.7).

Endpoints:

- ``POST /signed-sow/{package_id}/upload-url``   — pre-signed PUT to the
  SOW bucket. Owner / SystemAdmin only.
- ``POST /signed-sow/{package_id}``              — register the upload
  (``file_s3_key`` + ``file_hash``). Owner / SystemAdmin only.
- ``GET  /signed-sow/{package_id}``              — current upload +
  diff. Any governance role.
- ``POST /signed-sow/{package_id}/verify``       — re-extract + diff.
  Owner / SystemAdmin only.
- ``POST /signed-sow/{package_id}/release``      — SES + tasks + renewal
  + move package to ``released``. Owner / SystemAdmin only.

Role gates are UX + audit — the service re-checks package status
server-side and audits every transition (CLAUDE.md rule 5).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    get_bedrock_sow,
)
from app.integrations.s3_sow import (
    MAX_SOW_BYTES,
    SowS3,
    UnsupportedContentType,
    get_sow_s3,
)
from app.integrations.ses import SESClient, get_ses_client
from app.models.approval import ApprovalPackage
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.test_fixtures import allowed_for_package
from app.services.user_provisioning import ensure_user
from app.services.signed_sow import (
    _require_signature_eligibility,
    SignedSowError,
    create_upload,
    latest_upload_for,
    mark_declined,
    mark_expired,
    release,
    serialize_upload,
    verify,
)


router = APIRouter(prefix="/signed-sow", tags=["signed-sow"])


# ---- role gates ---------------------------------------------------------


_READ_ROLES: frozenset[str] = frozenset(
    {
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
    }
)


def _wrap(exc: SignedSowError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _load_package_and_opp(
    session: AsyncSession, package_id: uuid.UUID
) -> tuple[ApprovalPackage, Opportunity]:
    package = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == package_id)
        )
    ).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="approval_package not found")
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == package.opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return package, opp


def _require_owner(user: AuthUser, opp: Opportunity) -> None:
    """Account owner or SystemAdmin — the write allow-list for §6.7."""

    if "SystemAdmin" in user.groups:
        return
    if opp.owner_id is not None and opp.owner_id == user.id:
        return
    raise HTTPException(status_code=403, detail="not authorised")


def _require_read(user: AuthUser) -> None:
    if not any(g in _READ_ROLES for g in user.groups):
        raise HTTPException(status_code=403, detail="insufficient role")


# ---- schemas ------------------------------------------------------------


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(
        description="MIME type — pdf or docx only",
        examples=["application/pdf"],
    )


class UploadUrlResponse(BaseModel):
    url: str
    s3_key: str
    method: str
    expires_in: int
    required_headers: dict[str, str] | None = None
    max_bytes: int = MAX_SOW_BYTES


class CreateUploadRequest(BaseModel):
    file_s3_key: str = Field(min_length=1, max_length=1024)
    file_hash: str = Field(min_length=1, max_length=128)
    # T22: the uploader (SPA + integrations) must attest that the pdf
    # carries signature evidence. Defaults to True for backwards
    # compatibility; a false value produces a 400.
    has_signature_evidence: bool = True


class MarkDeclinedRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=400)


class MarkExpiredRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=400)


# ---- endpoints ----------------------------------------------------------


@router.post("/{package_id}/file", status_code=201)
async def upload_signed_file(
    package_id: uuid.UUID,
    file: UploadFile = File(...),
    has_signature_evidence: bool = Form(...),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> dict[str, Any]:
    actor = await ensure_user(session, user)
    actor_id = actor.id
    await session.commit()
    package, opp = await _load_package_and_opp(session, package_id)
    if "SystemAdmin" not in user.groups and opp.owner_id != actor_id:
        raise HTTPException(status_code=403, detail="not authorised")
    if not await allowed_for_package(session, actor_id, package):
        raise HTTPException(status_code=404, detail="approval_package not found")
    if package.superseded_by is not None or package.status != "ready_to_sign":
        raise HTTPException(status_code=409, detail="package is not ready for signature")
    opportunity_id, version_id = opp.id, package.sow_version_id
    if not has_signature_evidence:
        raise HTTPException(status_code=400, detail="unsigned upload rejected")
    content = await file.read(MAX_SOW_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="signed file is empty")
    if len(content) > MAX_SOW_BYTES:
        raise HTTPException(status_code=413, detail="signed file exceeds size limit")
    content_type = file.content_type or "application/octet-stream"
    if content_type not in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        raise HTTPException(status_code=422, detail="signed file must be PDF or DOCX")
    try:
        key = s3.build_key(file.filename or "signed.pdf", content_type, opportunity_id)
    except UnsupportedContentType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Refresh authority after receiving bytes and waiting for business locks.
    session.expire_all()
    opp = (await session.execute(
        select(Opportunity).where(Opportunity.id == opportunity_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    sow = (await session.execute(
        select(Sow).join(SowVersion, SowVersion.sow_id == Sow.id)
        .where(SowVersion.id == version_id).with_for_update(of=Sow)
    )).scalar_one_or_none()
    if sow is None or sow.archived_at is not None:
        raise HTTPException(status_code=404, detail="SOW not found")
    package = (await session.execute(
        select(ApprovalPackage).where(ApprovalPackage.id == package_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="approval_package not found")
    if "SystemAdmin" not in user.groups and opp.owner_id != actor_id:
        raise HTTPException(status_code=403, detail="not authorised")
    if not await allowed_for_package(session, actor_id, package):
        raise HTTPException(status_code=404, detail="approval_package not found")
    if package.superseded_by is not None or package.status != "ready_to_sign":
        raise HTTPException(status_code=409, detail="package is not ready for signature")
    try:
        await _require_signature_eligibility(session, package)
    except SignedSowError as exc:
        raise _wrap(exc) from exc
    try:
        await anyio.to_thread.run_sync(s3.put_object, key, content, content_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="could not store signed file") from exc
    try:
        upload = await create_upload(
            session, actor_id=actor_id, package_id=package_id,
            file_s3_key=key, file_hash=hashlib.sha256(content).hexdigest(),
            has_signature_evidence=True,
        )
    except SignedSowError as exc:
        raise _wrap(exc) from exc
    return serialize_upload(upload)


@router.post(
    "/{package_id}/upload-url", response_model=UploadUrlResponse
)
async def create_upload_url(
    package_id: uuid.UUID,
    body: UploadUrlRequest,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> UploadUrlResponse:
    package, opp = await _load_package_and_opp(session, package_id)
    _require_owner(user, opp)
    _ = package  # S17: signature upload URL no longer needs a coverage gate.
    try:
        # We reuse the SOW bucket + prefix — the signed pdf lives under
        # the opportunity's SOW folder alongside the pre-signature drafts.
        signed = s3.generate_upload_url(opp.id, body.filename, body.content_type)
    except UnsupportedContentType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadUrlResponse(
        url=signed.url,
        s3_key=signed.s3_key,
        method=signed.method,
        expires_in=signed.expires_in,
        required_headers=signed.required_headers,
        max_bytes=MAX_SOW_BYTES,
    )


@router.post("/{package_id}", status_code=201)
async def create_upload_endpoint(
    package_id: uuid.UUID,
    body: CreateUploadRequest,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _, opp = await _load_package_and_opp(session, package_id)
    _require_owner(user, opp)
    try:
        upload = await create_upload(
            session,
            actor_id=user.id,
            package_id=package_id,
            file_s3_key=body.file_s3_key,
            file_hash=body.file_hash,
            has_signature_evidence=body.has_signature_evidence,
        )
    except SignedSowError as exc:
        raise _wrap(exc) from exc
    return serialize_upload(upload)


@router.post("/{package_id}/decline")
async def decline_endpoint(
    package_id: uuid.UUID,
    body: MarkDeclinedRequest,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """External signer declined the request (T22)."""

    _, opp = await _load_package_and_opp(session, package_id)
    _require_owner(user, opp)
    row = await latest_upload_for(session, package_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="no signed_sow_upload for this package"
        )
    try:
        row = await mark_declined(
            session, actor_id=user.id, upload_id=row.id, reason=body.reason
        )
    except SignedSowError as exc:
        raise _wrap(exc) from exc
    return serialize_upload(row)


@router.post("/{package_id}/expire")
async def expire_endpoint(
    package_id: uuid.UUID,
    body: MarkExpiredRequest,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """External signature request expired without a return (T22)."""

    _, opp = await _load_package_and_opp(session, package_id)
    _require_owner(user, opp)
    row = await latest_upload_for(session, package_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="no signed_sow_upload for this package"
        )
    try:
        row = await mark_expired(
            session, actor_id=user.id, upload_id=row.id, reason=body.reason
        )
    except SignedSowError as exc:
        raise _wrap(exc) from exc
    return serialize_upload(row)


@router.get("/{package_id}")
async def get_upload_endpoint(
    package_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any] | None:
    _require_read(user)
    # Validate the package exists so callers get a clean 404 rather than
    # a null pretending nothing was ever uploaded.
    await _load_package_and_opp(session, package_id)
    row = await latest_upload_for(session, package_id)
    if row is None:
        return None
    return serialize_upload(row)


@router.post("/{package_id}/verify")
async def verify_endpoint(
    package_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    bedrock: BedrockSowExtract = Depends(get_bedrock_sow),
    s3: SowS3 = Depends(get_sow_s3),
) -> dict[str, Any]:
    _, opp = await _load_package_and_opp(session, package_id)
    _require_owner(user, opp)
    row = await latest_upload_for(session, package_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="no signed_sow_upload for this package"
        )
    try:
        file_bytes = await anyio.to_thread.run_sync(s3.download_bytes, row.file_s3_key)
        row = await verify(
            session, actor_id=user.id, upload_id=row.id, bedrock=bedrock,
            file_bytes=file_bytes,
        )
    except SignedSowError as exc:
        raise _wrap(exc) from exc
    return serialize_upload(row)


@router.post("/{package_id}/release")
async def release_endpoint(
    package_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    ses: SESClient = Depends(get_ses_client),
) -> dict[str, Any]:
    _, opp = await _load_package_and_opp(session, package_id)
    _require_owner(user, opp)
    row = await latest_upload_for(session, package_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="no signed_sow_upload for this package"
        )
    try:
        row = await release(
            session, actor_id=user.id, upload_id=row.id, ses=ses
        )
    except SignedSowError as exc:
        raise _wrap(exc) from exc
    return serialize_upload(row)
