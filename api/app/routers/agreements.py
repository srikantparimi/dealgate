"""Agreements (NDA / MSA) API — S2-E3.

Endpoints:

- ``POST   /agreements``                     — Legal / SystemAdmin creates a row.
- ``GET    /agreements``                     — governance roles read a filtered list.
- ``PATCH  /agreements/{id}``                — Legal / SystemAdmin mutates state
  and dates. Every changed field emits an ``agreement.state_changed`` audit row
  (the audit action name is used across all mutations per §12).
- ``POST   /agreements/{id}/evidence-upload-url``  — short-lived S3 PUT URL.
- ``GET    /agreements/{id}/evidence-download-url`` — short-lived S3 GET URL.

Business rules live in ``app.services.agreement_state``; the S3 signing lives
in ``app.integrations.s3_evidence``. This router does auth, shape conversion
and audit emission — nothing else.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.integrations.s3_evidence import (
    EvidenceS3,
    UnsupportedContentType,
    get_evidence_s3,
)
from app.models.client import Agreement, LegalEntity
from app.services.agreement_state import (
    ALLOWED_STATES,
    InvalidAgreementTransition,
    transition,
)

router = APIRouter(prefix="/agreements", tags=["agreements"])


# Governance roles that may read agreements. Mutations are stricter — Legal
# or SystemAdmin only. Kept in sync with blueprint §3.
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


# --- schemas --------------------------------------------------------------


class AgreementRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_entity_id: uuid.UUID
    kind: str
    state: str
    owner_email: str | None
    next_action: str | None
    due_date: date | None
    effective_from: date | None
    expiry: date | None
    notice_days: int | None
    evidence_s3_key: str | None
    signatories: list[dict[str, Any]] | None
    created_at: datetime
    updated_at: datetime


class AgreementListResponse(BaseModel):
    items: list[AgreementRow]
    allowed_states: list[str] = Field(default_factory=lambda: list(ALLOWED_STATES))


class AgreementCreateBody(BaseModel):
    legal_entity_id: uuid.UUID
    type: str = Field(description="NDA or MSA")
    state: str = "missing"
    owner_email: EmailStr | None = None
    next_action: str | None = Field(default=None, max_length=255)
    due_date: date | None = None


class AgreementPatchBody(BaseModel):
    state: str | None = None
    next_action: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    effective_from: date | None = None
    expiry: date | None = None
    notice_days: int | None = Field(default=None, ge=0)
    evidence_s3_key: str | None = Field(default=None, max_length=1024)
    signatories: list[dict[str, Any]] | None = None


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


class DownloadUrlResponse(BaseModel):
    url: str
    expires_in: int


# --- helpers --------------------------------------------------------------


def _serialize(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, date, datetime)):
        return str(value)
    return value


def _row(agreement: Agreement) -> AgreementRow:
    return AgreementRow.model_validate(agreement)


async def _load(session: AsyncSession, agreement_id: uuid.UUID) -> Agreement:
    row = (
        await session.execute(
            select(Agreement).where(Agreement.id == agreement_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agreement not found")
    return row


# --- endpoints ------------------------------------------------------------


@router.post("", response_model=AgreementRow, status_code=201)
async def create_agreement(
    body: AgreementCreateBody,
    actor: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AgreementRow:
    if body.type not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"type must be one of {sorted(_ALLOWED_KINDS)}",
        )
    if body.state not in ALLOWED_STATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"state must be one of {list(ALLOWED_STATES)}",
        )
    # `legal_entity_id` must exist. Reject 404 rather than letting the FK
    # error bubble up as a 500 at flush time.
    legal_entity = (
        await session.execute(
            select(LegalEntity).where(LegalEntity.id == body.legal_entity_id)
        )
    ).scalar_one_or_none()
    if legal_entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="legal_entity not found"
        )

    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=body.legal_entity_id,
        kind=body.type,
        state=body.state,
        owner_email=str(body.owner_email) if body.owner_email else None,
        next_action=body.next_action,
        due_date=body.due_date,
    )
    session.add(agreement)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor.id,
        action="agreement.created",
        entity="agreement",
        entity_id=str(agreement.id),
        before=None,
        after={
            "legal_entity_id": str(agreement.legal_entity_id),
            "kind": agreement.kind,
            "state": agreement.state,
            "owner_email": agreement.owner_email,
            "next_action": agreement.next_action,
            "due_date": _serialize(agreement.due_date),
        },
    )
    await session.commit()
    await session.refresh(agreement)
    return _row(agreement)


@router.get("", response_model=AgreementListResponse)
async def list_agreements(
    legal_entity_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None),
    expiring_within_days: int | None = Query(default=None, ge=0, le=3650),
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AgreementListResponse:
    stmt = select(Agreement)
    if legal_entity_id is not None:
        stmt = stmt.where(Agreement.legal_entity_id == legal_entity_id)
    if state is not None:
        if state not in ALLOWED_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"state must be one of {list(ALLOWED_STATES)}",
            )
        stmt = stmt.where(Agreement.state == state)
    stmt = stmt.order_by(Agreement.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()

    if expiring_within_days is not None:
        # Filter in Python so the boundary condition is trivial to read.
        from datetime import date as _date, timedelta

        cutoff = _date.today() + timedelta(days=expiring_within_days)
        rows = [r for r in rows if r.expiry is not None and r.expiry <= cutoff]

    # Agreements carry no cost fields — the response shape reflects that;
    # nothing further to strip.
    return AgreementListResponse(items=[_row(r) for r in rows])


_PATCH_TRACKED: tuple[str, ...] = (
    "next_action",
    "due_date",
    "effective_from",
    "expiry",
    "notice_days",
    "evidence_s3_key",
    "signatories",
)


@router.patch("/{agreement_id}", response_model=AgreementRow)
async def patch_agreement(
    agreement_id: uuid.UUID,
    body: AgreementPatchBody,
    actor: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AgreementRow:
    agreement = await _load(session, agreement_id)
    provided = body.model_dump(exclude_unset=True)
    if not provided:
        return _row(agreement)

    # Apply non-state fields FIRST so `expiry` is set before we validate the
    # `executed` transition inside `transition()`.
    for field in _PATCH_TRACKED:
        if field not in provided:
            continue
        old_value = getattr(agreement, field)
        new_value = provided[field]
        if old_value == new_value:
            continue
        setattr(agreement, field, new_value)
        await append_audit(
            session,
            actor_id=actor.id,
            action="agreement.state_changed",
            entity="agreement",
            entity_id=str(agreement.id),
            before={field: _serialize(old_value)},
            after={field: _serialize(new_value)},
        )

    # State transition last — it may require columns that were just set above
    # (e.g. `expiry` before moving to `executed`).
    if "state" in provided and provided["state"] is not None:
        new_state = provided["state"]
        old_state = agreement.state
        if new_state != old_state:
            try:
                transition(agreement, new_state, actor.id)
            except InvalidAgreementTransition as exc:
                # 422 with the reason from the state machine; no audit row.
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(exc),
                ) from exc
            await append_audit(
                session,
                actor_id=actor.id,
                action="agreement.state_changed",
                entity="agreement",
                entity_id=str(agreement.id),
                before={"state": old_state},
                after={"state": new_state},
            )

    await session.commit()
    await session.refresh(agreement)
    return _row(agreement)


@router.post(
    "/{agreement_id}/evidence-upload-url",
    response_model=UploadUrlResponse,
)
async def create_evidence_upload_url(
    agreement_id: uuid.UUID,
    body: UploadUrlRequest,
    actor: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> UploadUrlResponse:
    agreement = await _load(session, agreement_id)
    try:
        signed = s3.generate_upload_url(agreement.id, body.filename, body.content_type)
    except UnsupportedContentType as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await append_audit(
        session,
        actor_id=actor.id,
        action="agreement.evidence_upload_url_issued",
        entity="agreement",
        entity_id=str(agreement.id),
        before=None,
        after={
            "s3_key": signed.s3_key,
            "content_type": body.content_type,
            "expires_in": signed.expires_in,
        },
    )
    await session.commit()
    return UploadUrlResponse(
        url=signed.url,
        s3_key=signed.s3_key,
        method=signed.method,
        expires_in=signed.expires_in,
        required_headers=signed.required_headers,
    )


@router.get(
    "/{agreement_id}/evidence-download-url",
    response_model=DownloadUrlResponse,
)
async def get_evidence_download_url(
    agreement_id: uuid.UUID,
    actor: AuthUser = Depends(require_role(*_MUTATE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> DownloadUrlResponse:
    agreement = await _load(session, agreement_id)
    if not agreement.evidence_s3_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agreement has no evidence file",
        )
    url = s3.generate_download_url(agreement.evidence_s3_key)
    await append_audit(
        session,
        actor_id=actor.id,
        action="agreement.evidence_download_url_issued",
        entity="agreement",
        entity_id=str(agreement.id),
        before=None,
        after={"s3_key": agreement.evidence_s3_key},
    )
    await session.commit()
    return DownloadUrlResponse(url=url, expires_in=300)


_ = current_user  # kept for future ownership checks; silences lint.
