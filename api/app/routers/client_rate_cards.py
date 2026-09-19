"""Client rate cards API — S9 wave 1.

Finance / SystemAdmin can publish; any governance role can read. Rows are
immutable — Finance publishes a new card to change rates.

Endpoints:

- ``GET  /clients/{id}/rate-card``          — active card + rows.
- ``POST /clients/{id}/rate-card``          — publish a new card.
- ``POST /clients/{id}/rate-card/import``   — extract from an MSA (draft only).
- ``POST /clients/{id}/rate-card/upload-url`` — pre-signed PUT for the MSA
  source file (reuses the SOW bucket adapter pattern).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.s3_sow import (
    MAX_SOW_BYTES,
    SowS3,
    UnsupportedContentType,
    get_sow_s3,
)
from app.models.client import Client
from app.services.client_rate_cards import (
    ALLOWED_SOURCES,
    ClientRateCardRowInput,
    active_client_rate_card,
    publish_client_rate_card,
    resolve_bill_rate,
    serialize_card,
)
from app.services.msa_import import (
    MsaRateExtractor,
    draft_to_row_inputs,
    import_rate_schedule,
)

# Any governance role can read the card; only Finance/SystemAdmin can write.
READ_ROLES = (
    "Finance",
    "Delivery",
    "HR",
    "Legal",
    "CEO",
    "SystemAdmin",
    "Sales",
    "SalesLeader",
    "Presales",
)
WRITE_ROLES = ("Finance", "SystemAdmin")


router = APIRouter(prefix="/clients", tags=["clients"])


# --- schemas ---------------------------------------------------------------


class RateCardRowSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str = Field(min_length=1, max_length=128)
    seniority: str = Field(min_length=1, max_length=64)
    location: str
    bill_rate: Decimal
    currency: str = Field(default="USD", min_length=3, max_length=3)
    unit: str = "hourly"
    effective_period: str | None = None


class PublishClientRateCardRequest(BaseModel):
    effective_from: date
    notes: str | None = Field(default=None, max_length=1024)
    source: str = "manual"
    source_document_id: uuid.UUID | None = None
    rows: list[RateCardRowSchema] = Field(min_length=1)


class ClientRateCardResponse(BaseModel):
    card: dict | None
    has_fallback: bool
    warning: str | None


class ImportRateScheduleRequest(BaseModel):
    msa_file_key: str = Field(min_length=1, max_length=1024)


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


# --- helpers ---------------------------------------------------------------


async def _load_client_or_404(session: AsyncSession, client_id: uuid.UUID) -> Client:
    obj = (
        await session.execute(select(Client).where(Client.id == client_id))
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="client not found"
        )
    return obj


def _to_input(row: RateCardRowSchema) -> ClientRateCardRowInput:
    return ClientRateCardRowInput(
        role=row.role,
        seniority=row.seniority,
        location=row.location,
        bill_rate=row.bill_rate,
        currency=row.currency,
        unit=row.unit,
        effective_period=row.effective_period,
    )


# --- endpoints -------------------------------------------------------------


@router.get("/{client_id}/rate-card", response_model=ClientRateCardResponse)
async def get_active_card_endpoint(
    client_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> ClientRateCardResponse:
    await _load_client_or_404(session, client_id)
    card = await active_client_rate_card(session, client_id)
    if card is None:
        return ClientRateCardResponse(
            card=None,
            has_fallback=True,
            warning=(
                "no client rate card published — SOWs for this client will "
                "fall back to the company default (loud warning on the package)."
            ),
        )
    return ClientRateCardResponse(
        card=serialize_card(card, include_rows=True),
        has_fallback=False,
        warning=None,
    )


@router.post(
    "/{client_id}/rate-card",
    response_model=ClientRateCardResponse,
    status_code=201,
)
async def publish_card_endpoint(
    client_id: uuid.UUID,
    body: PublishClientRateCardRequest,
    actor: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> ClientRateCardResponse:
    await _load_client_or_404(session, client_id)
    if body.source not in ALLOWED_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source must be one of {sorted(ALLOWED_SOURCES)}",
        )
    card = await publish_client_rate_card(
        session,
        actor_id=actor.id,
        client_id=client_id,
        rows=[_to_input(r) for r in body.rows],
        effective_from=body.effective_from,
        notes=body.notes,
        source=body.source,
        source_document_id=body.source_document_id,
    )
    return ClientRateCardResponse(
        card=serialize_card(card, include_rows=True),
        has_fallback=False,
        warning=None,
    )


def _default_msa_extractor() -> MsaRateExtractor | None:
    """Dependency stub — tests override via ``dependency_overrides``."""

    return None


@router.post("/{client_id}/rate-card/import")
async def import_card_endpoint(
    client_id: uuid.UUID,
    body: ImportRateScheduleRequest,
    actor: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
    extractor: MsaRateExtractor | None = Depends(_default_msa_extractor),
) -> dict:
    """Extract a rate schedule from an MSA and return a **draft**.

    Never publishes. A human confirms the draft via the publish endpoint
    (CLAUDE.md rule 6).
    """

    await _load_client_or_404(session, client_id)
    draft = await import_rate_schedule(
        session,
        actor_id=actor.id,
        client_id=client_id,
        msa_file_key=body.msa_file_key,
        extractor=extractor,
    )
    # Also return the publisher-ready row shape so the browser can send
    # them straight back on confirmation without re-parsing.
    inputs = draft_to_row_inputs(draft)
    return {
        "draft": draft.to_dict(),
        "publish_rows": [
            {
                "role": r.role,
                "seniority": r.seniority,
                "location": r.location,
                "bill_rate": format(r.bill_rate, "f"),
                "currency": r.currency,
                "unit": r.unit,
            }
            for r in inputs
        ],
    }


@router.post("/{client_id}/rate-card/upload-url", response_model=UploadUrlResponse)
async def upload_url_endpoint(
    client_id: uuid.UUID,
    body: UploadUrlRequest,
    _user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> UploadUrlResponse:
    await _load_client_or_404(session, client_id)
    try:
        signed = s3.generate_upload_url(client_id, body.filename, body.content_type)
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


# --- resolution preview (used by the Builder + tests) --------------------


class ResolveBillRateRequest(BaseModel):
    role: str
    seniority: str
    location: str
    sow_stated: Decimal | None = None


@router.post("/{client_id}/rate-card/resolve")
async def resolve_bill_rate_endpoint(
    client_id: uuid.UUID,
    body: ResolveBillRateRequest,
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _load_client_or_404(session, client_id)
    resolved = await resolve_bill_rate(
        session,
        client_id=client_id,
        role=body.role,
        seniority=body.seniority,
        location=body.location,
        sow_stated=body.sow_stated,
    )
    return {
        "rate": format(resolved.rate, "f") if resolved.rate is not None else None,
        "source": resolved.source,
        "warning": resolved.warning,
        "card_id": str(resolved.card_id) if resolved.card_id else None,
    }
