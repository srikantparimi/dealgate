"""SOW upload router (S10-01).

Three endpoints:

- ``POST /sows/upload``          — multipart file → job envelope.
- ``GET  /sows/jobs/{job_id}``   — poll status.
- ``POST /sows/jobs/{job_id}/pick`` — resume after picker choice.

Auth (per ``docs/backlog/s10-sow-upload.md``):

- Uploader roles: Sales, Delivery, Finance, Legal, CEO, SystemAdmin,
  SalesLeader, HR (any governance role that owns a live deal).
- Reviewer roles (`SalesLeader`, `Finance`, `Legal`, `CEO`,
  `SystemAdmin`) see every job; other roles see only the jobs they
  uploaded. Enforced in :func:`_ensure_read_access`.

Every state change writes an ``audit_event`` via the service layer
(CLAUDE.md rule 5); this router does not emit its own audits.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    get_bedrock_sow,
)
from app.integrations.s3_sow import SowS3, get_sow_s3
from app.services.user_provisioning import ensure_user
from app.services.sow_upload_job_service import (
    RejectedDocumentType,
    UploadPipelineError,
    find_by_hash,
    get_job,
    resume_after_pick,
    serialize_job,
    start_upload,
)

router = APIRouter(prefix="/sows", tags=["sows"])


# --- role gates -----------------------------------------------------------

_UPLOAD_ROLES: tuple[str, ...] = (
    "Sales",
    "SalesLeader",
    "Delivery",
    "HR",
    "Finance",
    "Legal",
    "CEO",
    "SystemAdmin",
)
_READ_ROLES: tuple[str, ...] = _UPLOAD_ROLES

# Roles that see every job; others see only their own uploads.
_LEADER_ROLES: frozenset[str] = frozenset(
    {"SalesLeader", "Finance", "Legal", "CEO", "SystemAdmin"}
)


# --- schemas --------------------------------------------------------------


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: str
    resolution: str | None = None
    opportunity_id: uuid.UUID | None = None
    sow_version_id: uuid.UUID | None = None
    duplicate: bool = False
    needs_pick: dict[str, Any] | None = None


class JobStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    resolution: str | None
    error: str | None
    opportunity_id: uuid.UUID | None
    sow_version_id: uuid.UUID | None
    file_hash: str
    s3_key: str | None
    needs_pick: dict[str, Any] | None


class PickCreateNew(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    domain: str | None = None
    address_lines: list[str] | None = None


class PickRequest(BaseModel):
    """Body of the resume endpoint. Exactly one of ``client_id`` or
    ``create_new`` must be present; validation is server-side so a
    malformed body returns 422 with a clear message."""

    client_id: uuid.UUID | None = None
    create_new: PickCreateNew | None = None


# --- helpers --------------------------------------------------------------


def _ensure_read_access(user: AuthUser, uploader_id: uuid.UUID) -> None:
    if any(role in _LEADER_ROLES for role in user.groups):
        return
    if user.id == uploader_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="not authorised to view this job",
    )


def _job_to_response(job) -> JobStatusResponse:
    payload = serialize_job(job)
    return JobStatusResponse(
        id=uuid.UUID(payload["id"]),
        status=payload["status"],
        resolution=payload["resolution"],
        error=payload["error"],
        opportunity_id=(
            uuid.UUID(payload["opportunity_id"])
            if payload["opportunity_id"]
            else None
        ),
        sow_version_id=(
            uuid.UUID(payload["sow_version_id"])
            if payload["sow_version_id"]
            else None
        ),
        file_hash=payload["file_hash"],
        s3_key=payload["s3_key"],
        needs_pick=payload["needs_pick"],
    )


# --- endpoints ------------------------------------------------------------


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_sow(
    file: UploadFile = File(...),
    client_hint: str | None = Form(default=None),
    user: AuthUser = Depends(require_role(*_UPLOAD_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
    bedrock: BedrockSowExtract = Depends(get_bedrock_sow),
) -> UploadResponse:
    """Kick off the pipeline for a single-file upload.

    Duplicate file → 200 with ``duplicate=true``. Non-SOW → 422 with
    ``{detected_type, message}``. Success → 200 with the job envelope.
    """

    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="filename is required",
        )
    content_type = file.content_type or "application/pdf"
    if content_type not in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unsupported content_type {content_type!r}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uploaded file is empty",
        )

    # Duplicate short-circuit — the pipeline handles this internally too,
    # but running it here means the router never touches S3 for a dupe.
    #
    # This is the query that produced the bare "API error 500": when
    # migration 0028 had not been applied, `sow_upload_job` did not exist and
    # the raw ProgrammingError escaped every handler, so Starlette returned a
    # plain-text body the browser client could not read a message from. It
    # still runs before the try (the try's handlers are for pipeline
    # outcomes, not database faults); the schema-fault handler registered in
    # `app.main` is what now turns it into a 503 that says what happened.
    #
    # A `failed` job is deliberately not treated as a duplicate. `file_hash`
    # is UNIQUE, so returning the dead row here would mean a file that failed
    # once — a transient S3 or Bedrock outage, say — could never be uploaded
    # again. `start_upload` reuses and resets that row instead.
    existing = await find_by_hash(session, __sha256(file_bytes))
    if existing is not None and existing.status != "failed":
        await session.commit()
        return UploadResponse(
            job_id=existing.id,
            status=existing.status,
            resolution=existing.resolution,
            opportunity_id=existing.opportunity_id,
            sow_version_id=existing.sow_version_id,
            duplicate=True,
            needs_pick=existing.needs_pick_payload,
        )

    # Guarantee a `user` row exists before anything references it.
    # `sow_upload_job.uploader_id` is a NOT NULL FK, and an SSO principal who
    # was never invited through the admin console has no row — so without this
    # the very first upload by a new user is an IntegrityError.
    # Use the returned row's id: `ensure_user` may adopt a row an admin
    # pre-created under a different uuid.
    db_user = await ensure_user(session, user)

    try:
        job = await start_upload(
            session,
            uploader_id=db_user.id,
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=content_type,
            client_hint=client_hint,
            s3=s3,
            bedrock_sow=bedrock,
        )
    except RejectedDocumentType as exc:
        # No DB rows created — safe to bail without a commit. The message
        # comes from the exception so an unreadable file says so, rather than
        # claiming it is not a SOW.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detected_type": exc.detected_type, "message": exc.message},
        ) from exc
    except UploadPipelineError as exc:
        # Job row exists in `failed` — commit so the caller can poll it.
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    await session.commit()
    return UploadResponse(
        job_id=job.id,
        status=job.status,
        resolution=job.resolution,
        opportunity_id=job.opportunity_id,
        sow_version_id=job.sow_version_id,
        duplicate=False,
        needs_pick=job.needs_pick_payload,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
)
async def get_upload_job(
    job_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> JobStatusResponse:
    job = await get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    _ensure_read_access(user, job.uploader_id)
    return _job_to_response(job)


@router.post(
    "/jobs/{job_id}/pick",
    response_model=JobStatusResponse,
)
async def pick_upload_job(
    job_id: uuid.UUID,
    body: PickRequest,
    user: AuthUser = Depends(require_role(*_UPLOAD_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> JobStatusResponse:
    """Resume a paused job by naming the client.

    Idempotent — a repeat call after ``done`` returns the same envelope.
    """

    job = await get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # Only the original uploader (or an admin) can resume the pipeline —
    # a random viewer must not be able to force a client match.
    if user.id != job.uploader_id and "SystemAdmin" not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the uploader can resume this job",
        )

    if body.client_id is None and body.create_new is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pick requires either client_id or create_new",
        )
    if body.client_id is not None and body.create_new is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pick accepts client_id XOR create_new, not both",
        )

    try:
        job = await resume_after_pick(
            session,
            job=job,
            client_id=body.client_id,
            create_new=body.create_new.model_dump() if body.create_new else None,
        )
    except UploadPipelineError as exc:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    await session.commit()
    return _job_to_response(job)


# --- module-local helpers -------------------------------------------------


def __sha256(payload: bytes) -> str:
    """Local re-export so the router doesn't have to import the service
    hasher twice — keeps the dedupe short-circuit self-contained."""

    from app.services.sow_upload_pipeline import sha256_hex

    return sha256_hex(payload)


__all__ = ["router"]
