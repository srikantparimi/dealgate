"""SOW upload + extraction + confirm API (build-guide §6.3, story s3-e5).

Endpoints:

- ``POST   /sow/{opportunity_id}/upload-url``   — issue pre-signed PUT.
- ``POST   /sow/{opportunity_id}/versions``     — register a new version;
  kicks off Bedrock extract inline (dev). Also enforces the 25 MB cap via
  the client-provided ``file_size`` hint (S3 pre-sign cannot cap on its
  own — see :mod:`app.integrations.s3_sow`).
- ``GET    /sow/versions/{sow_version_id}``     — read the current fields
  and status.
- ``PATCH  /sow/versions/{sow_version_id}/fields/{field_name}`` — confirm
  or override one field.
- ``POST   /sow/versions/{sow_version_id}/submit`` — final human sign-off.

Auth:

- Reads: any governance role.
- Writes: opportunity owner or ``SystemAdmin``. The story additionally
  allows ``SystemAdmin`` on the upload endpoint; :func:`_require_owner`
  covers both by delegating to ``can_mutate_deal``.

Every write path emits an ``audit_event`` in the same transaction via the
service layer (CLAUDE.md rule 5). AI output is never persisted as
confirmed — the extract endpoint sets ``status="unconfirmed"`` and only
:func:`patch_field` can flip a field to ``confirmed`` (rule 6).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.services.redact import redact_costs
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
from app.models.opportunity import Opportunity
from app.services.deals import can_mutate_deal
from app.services.sow_extract import (
    SowInvalidField,
    SowNotFound,
    SowSubmissionIncomplete,
    SowVersionState,
    confirm_field,
    create_sow_version,
    latest_version_for,
    load_version_state,
    run_extract,
    submit_sow,
)

router = APIRouter(prefix="/sow", tags=["sow"])


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


# --- schemas --------------------------------------------------------------


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


class CreateVersionRequest(BaseModel):
    file_s3_key: str = Field(min_length=1, max_length=1024)
    file_hash: str = Field(min_length=1, max_length=128)
    # Client-provided size hint used for the 25 MB gate. Optional so a
    # legacy caller still works; when omitted the size check is skipped.
    file_size: int | None = Field(default=None, ge=0)


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sow_id: uuid.UUID
    opportunity_id: uuid.UUID
    uploaded_by: uuid.UUID | None
    uploaded_at: datetime
    file_s3_key: str
    file_hash: str
    extracted_fields: dict[str, Any] | None
    extract_status: str
    extract_model: str | None
    extract_prompt_version: str | None
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    engagement_type_suggested: str | None
    engagement_type_confirmed: str | None
    download_url: str | None = None


class FieldPatch(BaseModel):
    value: Any


# --- helpers --------------------------------------------------------------


async def _load_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Opportunity:
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found"
        )
    return opp


def _require_owner(user: AuthUser, opp: Opportunity) -> None:
    """Account owner or SystemAdmin — the write allow-list for §6.3."""

    if "SystemAdmin" in user.groups:
        return
    if opp.owner_id is not None and opp.owner_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
    )


def _to_response(
    state: SowVersionState, download_url: str | None = None, *, user: AuthUser
) -> VersionResponse:
    return VersionResponse(
        id=state.id,
        sow_id=state.sow_id,
        opportunity_id=state.opportunity_id,
        uploaded_by=state.uploaded_by,
        uploaded_at=state.uploaded_at,
        file_s3_key=state.file_s3_key,
        file_hash=state.file_hash,
        extracted_fields=redact_costs(state.extracted_fields, set(user.groups)),
        extract_status=state.extract_status,
        extract_model=state.extract_model,
        extract_prompt_version=state.extract_prompt_version,
        confirmed_by=state.confirmed_by,
        confirmed_at=state.confirmed_at,
        engagement_type_suggested=state.engagement_type_suggested,
        engagement_type_confirmed=state.engagement_type_confirmed,
        download_url=download_url,
    )


async def _load_version_or_404(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> SowVersionState:
    try:
        return await load_version_state(session, sow_version_id)
    except SowNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


# --- endpoints ------------------------------------------------------------


@router.post("/{opportunity_id}/upload-url", response_model=UploadUrlResponse)
async def create_upload_url(
    opportunity_id: uuid.UUID,
    body: UploadUrlRequest,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> UploadUrlResponse:
    opp = await _load_opportunity(session, opportunity_id)
    _require_owner(user, opp)
    try:
        signed = s3.generate_upload_url(opp.id, body.filename, body.content_type)
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
        max_bytes=MAX_SOW_BYTES,
    )


@router.post(
    "/{opportunity_id}/versions",
    response_model=VersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    opportunity_id: uuid.UUID,
    body: CreateVersionRequest,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
    bedrock: BedrockSowExtract = Depends(get_bedrock_sow),
) -> VersionResponse:
    opp = await _load_opportunity(session, opportunity_id)
    _require_owner(user, opp)

    if body.file_size is not None and body.file_size > MAX_SOW_BYTES:
        # 413 Payload Too Large — story AC "File > 25 MB → 413".
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"file exceeds {MAX_SOW_BYTES} bytes "
                f"({body.file_size} bytes provided)"
            ),
        )

    try:
        state = await create_sow_version(
            session,
            opportunity_id=opp.id,
            uploaded_by=user.id,
            file_s3_key=body.file_s3_key,
            file_hash=body.file_hash,
        )
    except SowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Dev-time: run extract synchronously so the confirm page is populated
    # on first load. Production will schedule a background job.
    state = await run_extract(session, sow_version_id=state.id, bedrock=bedrock)

    await session.commit()
    download = s3.generate_download_url(state.file_s3_key)
    return _to_response(state, download_url=download, user=user)


@router.get(
    "/opportunity/{opportunity_id}/current",
    response_model=VersionResponse | None,
)
async def get_current_version(
    opportunity_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> VersionResponse | None:
    """Return the latest SOW version for a deal, or ``null`` if none exist.

    Consumed by ``DealDetail`` to decide whether to render the upload
    dropzone or the confirm screen inline.
    """

    state = await latest_version_for(session, opportunity_id)
    if state is None:
        return None
    download = s3.generate_download_url(state.file_s3_key)
    return _to_response(state, download_url=download, user=_user)


@router.get("/versions/{sow_version_id}", response_model=VersionResponse)
async def get_version(
    sow_version_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> VersionResponse:
    state = await _load_version_or_404(session, sow_version_id)
    download = s3.generate_download_url(state.file_s3_key)
    return _to_response(state, download_url=download, user=_user)


@router.patch(
    "/versions/{sow_version_id}/fields/{field_name}",
    response_model=VersionResponse,
)
async def patch_field(
    sow_version_id: uuid.UUID,
    field_name: str,
    body: FieldPatch,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> VersionResponse:
    state = await _load_version_or_404(session, sow_version_id)
    opp = await _load_opportunity(session, state.opportunity_id)
    if not can_mutate_deal(user, opp) and "SystemAdmin" not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
        )
    try:
        new_state = await confirm_field(
            session,
            actor_id=user.id,
            sow_version_id=sow_version_id,
            field_name=field_name,
            value=body.value,
        )
    except SowInvalidField as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except SowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    download = s3.generate_download_url(new_state.file_s3_key)
    return _to_response(new_state, download_url=download, user=user)


@router.get("/{opportunity_id}/confirmation")
async def get_confirmation(
    opportunity_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """One-shot derived package for the confirmation screen (S9 wave 1).

    Runs classify → auto-staff → auto-GM in the request. Idempotent: a
    repeat call within the same session reuses the GM model already
    tied to the SOW version.
    """

    from app.services.sow_confirmation import (
        build_confirmation,
        serialize_confirmation,
    )

    try:
        payload = await build_confirmation(
            session, opportunity_id=opportunity_id, actor_id=None
        )
    except SowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Commit the auto-GM row if one was created — build_confirmation
    # writes through delivery_model.create_gm_model_version which flushes
    # but its own commit is what persists the audit + row together.
    await session.commit()
    return redact_costs(serialize_confirmation(payload), set(_user.groups))


@router.post("/{opportunity_id}/confirmation/submit")
async def submit_confirmation_endpoint(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Commit + transition. Idempotent by (sow_version_id, gm_model_id)."""

    opp = await _load_opportunity(session, opportunity_id)
    if not can_mutate_deal(user, opp) and "SystemAdmin" not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
        )
    from app.services.sow_confirmation import (
        serialize_confirmation,
        submit_confirmation,
    )

    try:
        payload = await submit_confirmation(
            session, opportunity_id=opportunity_id, actor_id=user.id
        )
    except SowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return redact_costs(serialize_confirmation(payload), set(user.groups))


@router.post(
    "/versions/{sow_version_id}/submit", response_model=VersionResponse
)
async def submit_version(
    sow_version_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> VersionResponse:
    state = await _load_version_or_404(session, sow_version_id)
    opp = await _load_opportunity(session, state.opportunity_id)
    if not can_mutate_deal(user, opp) and "SystemAdmin" not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
        )
    try:
        new_state = await submit_sow(
            session, actor_id=user.id, sow_version_id=sow_version_id
        )
    except SowSubmissionIncomplete as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "missing_fields": exc.missing},
        ) from exc
    except SowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    download = s3.generate_download_url(new_state.file_s3_key)
    return _to_response(new_state, download_url=download, user=user)
