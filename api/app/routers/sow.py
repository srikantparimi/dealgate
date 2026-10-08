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
import datetime as _dt
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
from app.models.sow import SowVersion
from app.models.user import User as UserModel
from app.services.deals import can_mutate_deal
from app.services.user_identity import display_user_name
from app.services.user_provisioning import ensure_user
from app.services.test_fixtures import account_scope, reviewer_scope, user_allowed
from app.services.extraction_conflicts import ConflictReview, conflict_items, resolve_conflict
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
    version_no: int = 1
    sow_id: uuid.UUID
    opportunity_id: uuid.UUID
    uploaded_by: uuid.UUID | None
    # S21-1c item 1: never a short id in the UI fallback — carry the
    # uploader's display name on the version so OverviewTab and the
    # workspace header can render "Uploader · Jane Doe" when the deal
    # has no owner.
    uploaded_by_name: str | None = None
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


async def _actor(session: AsyncSession, user: AuthUser) -> AuthUser:
    actor = await ensure_user(session, user)
    canonical = AuthUser(actor.id, actor.email, actor.name, tuple(actor.groups))
    await session.commit()
    return canonical


async def _load_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID, user: AuthUser, *, lock: bool = False
) -> Opportunity:
    query = select(Opportunity).where(Opportunity.id == opportunity_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    opp = (await session.execute(query)).scalar_one_or_none()
    if opp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found"
        )
    scope = await account_scope(session, opp.client_id, opportunity_id=opp.id) if opp.client_id else None
    if not user_allowed(user, scope):
        raise HTTPException(status_code=404, detail="opportunity not found")
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
    state: SowVersionState,
    download_url: str | None = None,
    *,
    user: AuthUser,
    uploaded_by_name: str | None = None,
) -> VersionResponse:
    return VersionResponse(
        id=state.id,
        sow_id=state.sow_id,
        version_no=state.version_no,
        opportunity_id=state.opportunity_id,
        uploaded_by=state.uploaded_by,
        uploaded_by_name=uploaded_by_name,
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


async def _resolve_uploader_name(
    session: AsyncSession, uploaded_by: uuid.UUID | None
) -> str | None:
    """S21-1c item 1 helper: look up the uploader's display name.

    Returns None when the uploaded_by column is NULL. Returns the
    `display_user_name` of a found user, else a stable "Former
    teammate" sentinel (never a raw id or UUID prefix) when the row
    exists on a SOW but the user has since been deleted.
    """

    if uploaded_by is None:
        return None
    user_row = await session.scalar(select(UserModel).where(UserModel.id == uploaded_by))
    if user_row is None:
        return "Former teammate"
    return display_user_name(user_row.name, user_row.email)


async def _load_version_or_404(
    session: AsyncSession, sow_version_id: uuid.UUID, user: AuthUser
) -> SowVersionState:
    version = await session.get(SowVersion, sow_version_id)
    if not user_allowed(user, await reviewer_scope(session, version)):
        raise HTTPException(status_code=404, detail="SOW version not found")
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
    user = await _actor(session, user)
    opp = await _load_opportunity(session, opportunity_id, user)
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
    user = await _actor(session, user)
    opp = await _load_opportunity(session, opportunity_id, user, lock=True)
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
    uploader_name = await _resolve_uploader_name(session, state.uploaded_by)
    return _to_response(state, download_url=download, user=user, uploaded_by_name=uploader_name)


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

    _user = await _actor(session, _user)
    await _load_opportunity(session, opportunity_id, _user)
    state = await latest_version_for(session, opportunity_id)
    if state is None:
        return None
    state = await _load_version_or_404(session, state.id, _user)
    download = s3.generate_download_url(state.file_s3_key)
    uploader_name = await _resolve_uploader_name(session, state.uploaded_by)
    return _to_response(state, download_url=download, user=_user, uploaded_by_name=uploader_name)


@router.get("/versions/{sow_version_id}", response_model=VersionResponse)
async def get_version(
    sow_version_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> VersionResponse:
    _user = await _actor(session, _user)
    state = await _load_version_or_404(session, sow_version_id, _user)
    download = s3.generate_download_url(state.file_s3_key)
    uploader_name = await _resolve_uploader_name(session, state.uploaded_by)
    return _to_response(state, download_url=download, user=_user, uploaded_by_name=uploader_name)


@router.get("/versions/{sow_version_id}/term-assist")
async def term_assist(
    sow_version_id: uuid.UUID,
    start: _dt.date | None = None,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """S22 click-through fix: the SOW's stated duration, deterministically.

    When the document states a duration ("seven weeks", a milestone plan
    ending at Week 7) but no calendar dates, a human supplies the
    kickoff and the server derives the end date — a labeled suggestion
    with its verbatim source snippet, applied through the normal
    field-confirm flow. Never guessed, never auto-saved.
    """
    from app.models.commercial_draft import CommercialDraft
    from app.services.term_assist import derived_end, stated_duration

    _user = await _actor(session, _user)
    state = await _load_version_or_404(session, sow_version_id, _user)

    # First source of truth: the user's own Staffing & GM working draft.
    # If it carries contract dates — or role dates that bound the plan —
    # the term suggestion is those dates, no typing required.
    draft = await session.get(CommercialDraft, state.opportunity_id)
    if draft is not None and isinstance(draft.inputs, dict):
        iso = r"^\d{4}-\d{2}-\d{2}$"
        import re as _re

        def _date(raw: object) -> str | None:
            return raw if isinstance(raw, str) and _re.match(iso, raw) else None

        d_start = _date(draft.inputs.get("service_start"))
        d_end = _date(draft.inputs.get("service_end"))
        if not (d_start and d_end):
            starts = sorted(
                d for row in draft.inputs.get("staffing") or []
                if (d := _date(row.get("start"))) is not None
            )
            ends = sorted(
                d for row in draft.inputs.get("staffing") or []
                if (d := _date(row.get("end"))) is not None
            )
            d_start = d_start or (starts[0] if starts else None)
            d_end = d_end or (ends[-1] if ends else None)
        if d_start and d_end:
            return {
                "available": True,
                "source": "staffing_draft",
                "suggested_start": d_start,
                "suggested_end": d_end,
                "quote": "dates from your Staffing & GM plan",
            }

    duration = stated_duration(state.extracted_fields)
    if duration is None:
        return {"available": False}
    out: dict = {"available": True, "source": "stated_duration", **duration}
    if start is not None:
        out["start"] = start.isoformat()
        out["suggested_end"] = derived_end(start, duration).isoformat()
    return out


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
    from app.services.sow_extract import SowReplayConflict

    user = await _actor(session, user)
    state = await _load_version_or_404(session, sow_version_id, user)
    opp = await _load_opportunity(session, state.opportunity_id, user, lock=True)
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
    except SowReplayConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    download = s3.generate_download_url(new_state.file_s3_key)
    uploader_name = await _resolve_uploader_name(session, new_state.uploaded_by)
    return _to_response(new_state, download_url=download, user=user, uploaded_by_name=uploader_name)


async def _conflict_editor(session, version_id, user, *, lock=False):
    state = await _load_version_or_404(session, version_id, user)
    opportunity = await _load_opportunity(session, state.opportunity_id, user, lock=lock)
    if not can_mutate_deal(user, opportunity) and "SystemAdmin" not in user.groups:
        raise HTTPException(403, "not authorised")
    return state


@router.get("/versions/{sow_version_id}/extraction-conflicts")
async def get_extraction_conflicts(sow_version_id: uuid.UUID,
    user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    user = await _actor(session, user)
    return conflict_items(await _conflict_editor(session, sow_version_id, user))


@router.post("/versions/{sow_version_id}/extraction-conflicts/{field_name}")
async def review_extraction_conflict(sow_version_id: uuid.UUID, field_name: str, body: ConflictReview,
    user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    from app.services.sow_extract import SowReplayConflict

    user = await _actor(session, user)
    await _conflict_editor(session, sow_version_id, user, lock=True)
    try:
        result = await resolve_conflict(session, actor_id=user.id, version_id=sow_version_id,
            field=field_name, body=body)
    except SowReplayConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except SowNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    await session.commit()
    return result


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

    _user = await _actor(session, _user)
    await _load_opportunity(session, opportunity_id, _user)
    state = await latest_version_for(session, opportunity_id)
    if state is not None:
        await _load_version_or_404(session, state.id, _user)
    try:
        payload = await build_confirmation(
            session, opportunity_id=opportunity_id, actor_id=_user.id
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

    user = await _actor(session, user)
    opp = await _load_opportunity(session, opportunity_id, user, lock=True)
    state = await latest_version_for(session, opportunity_id)
    if state is not None:
        await _load_version_or_404(session, state.id, user)
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
    "/versions/{sow_version_id}/reextract", response_model=VersionResponse
)
async def reextract_version(
    sow_version_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
    bedrock: BedrockSowExtract = Depends(get_bedrock_sow),
) -> VersionResponse:
    """S15: retry Bedrock extract on an existing SOW version.

    Called by the Confirm page's honest banner ("We couldn't read this
    document (reason). Retry extraction, or fill the fields below manually.").
    Fetches the file bytes from S3 and runs the full extract path
    (Textract fallback included). Only the exact same mutable document version
    may replay. Confirmed fields survive; conflicting candidates require review.
    """

    user = await _actor(session, user)
    state = await _load_version_or_404(session, sow_version_id, user)
    opp = await _load_opportunity(session, state.opportunity_id, user, lock=True)
    if not can_mutate_deal(user, opp) and "SystemAdmin" not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
        )

    file_bytes = s3.download_bytes(state.file_s3_key)
    from app.services.sow_extract import SowReplayConflict

    try:
        updated = await run_extract(
            session,
            sow_version_id=sow_version_id,
            bedrock=bedrock,
            file_bytes=file_bytes,
            replay=True,
        )
    except SowReplayConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    download = s3.generate_download_url(updated.file_s3_key)
    uploader_name = await _resolve_uploader_name(session, updated.uploaded_by)
    return _to_response(updated, download_url=download, user=user, uploaded_by_name=uploader_name)


@router.post(
    "/versions/{sow_version_id}/submit", response_model=VersionResponse
)
async def submit_version(
    sow_version_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> VersionResponse:
    user = await _actor(session, user)
    state = await _load_version_or_404(session, sow_version_id, user)
    opp = await _load_opportunity(session, state.opportunity_id, user, lock=True)
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
    uploader_name = await _resolve_uploader_name(session, new_state.uploaded_by)
    return _to_response(new_state, download_url=download, user=user, uploaded_by_name=uploader_name)
