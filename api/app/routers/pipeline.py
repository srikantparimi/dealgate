"""Pipeline API (S18 §2) — HubSpot-sourced deals for the Pipeline UI.

Every SPA surface that shows deal lists reads through this router:

- ``/pipeline``                        (Pipeline page)
- ``/command`` pipeline card
- SOW upload deal picker
- SOW detail "linked HubSpot deal" panel

Role gating mirrors the client read set: any leader role plus Sales /
Presales can list; Sales sees only rows they own, per the base filter in
``hubspot_pipeline`` — which returns HubSpot rows regardless of ownership
so leaders can see the whole board.

Read-only in this slice (S18 §2). No POST/PATCH here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.deals import LEADER_ROLES
from app.services.hubspot_pipeline import (
    ClientRow,
    DEFAULT_SORT_CLIENTS,
    DEFAULT_SORT_OPPS,
    OpportunityRow,
    PipelineDeal,
    PipelineFilters,
    PipelineSummary,
    SortSpec,
    VALID_DATE_FIELDS,
    get_pipeline_deal,
    list_clients as _list_clients,
    list_opportunities as _list_opportunities,
    list_pipeline_deals,
    search_pipeline_deals,
    summary as _summary,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# The same read roles the /clients list uses (leader roles + Presales +
# Sales — Sales sees the row because HubSpot is the master of ownership,
# and leaders review the board).
PIPELINE_READ_ROLES: frozenset[str] = frozenset(LEADER_ROLES | {"Presales", "Sales"})


def _require_reader(user: AuthUser) -> None:
    if not any(role in PIPELINE_READ_ROLES for role in user.groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="pipeline read requires a sales or leader role",
        )


class LinkedSowRow(BaseModel):
    sow_id: uuid.UUID
    created_at: datetime


class PipelineDealRow(BaseModel):
    opportunity_id: uuid.UUID
    hubspot_deal_id: str | None
    name: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    stage: str | None
    stage_label: str | None
    amount: Decimal | None
    owner_id: uuid.UUID | None
    owner_email: str | None
    owner_name: str | None
    close_date: date | None
    hubspot_last_seen_at: datetime | None
    linked_sows: list[LinkedSowRow] = Field(default_factory=list)


class PipelineListResponse(BaseModel):
    items: list[PipelineDealRow]
    total_open: int
    total_closed_lost: int
    page: int
    size: int


def _to_row(deal: PipelineDeal) -> PipelineDealRow:
    return PipelineDealRow(
        opportunity_id=deal.opportunity_id,
        hubspot_deal_id=deal.hubspot_deal_id,
        name=deal.name,
        client_id=deal.client_id,
        client_name=deal.client_name,
        stage=deal.stage,
        stage_label=deal.stage_label,
        amount=deal.amount,
        owner_id=deal.owner_id,
        owner_email=deal.owner_email,
        owner_name=deal.owner_name,
        close_date=deal.close_date,
        hubspot_last_seen_at=deal.hubspot_last_seen_at,
        linked_sows=[
            LinkedSowRow(sow_id=s.sow_id, created_at=s.created_at) for s in deal.linked_sows
        ],
    )


@router.get("/deals", response_model=PipelineListResponse)
async def list_deals(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    include_closed_lost: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> PipelineListResponse:
    _require_reader(user)
    deals, total_open, total_closed_lost = await list_pipeline_deals(
        session,
        include_closed_lost=include_closed_lost,
        page=page,
        size=size,
    )
    return PipelineListResponse(
        items=[_to_row(d) for d in deals],
        total_open=total_open,
        total_closed_lost=total_closed_lost,
        page=page,
        size=size,
    )


@router.get("/deals/{opportunity_id}", response_model=PipelineDealRow)
async def get_deal(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PipelineDealRow:
    _require_reader(user)
    deal = await get_pipeline_deal(session, opportunity_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal not found")
    return _to_row(deal)


@router.get("/deals/search", response_model=list[PipelineDealRow])
async def search_deals(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PipelineDealRow]:
    """Feeds the SOW-upload picker's HubSpot-deal dropdown."""

    _require_reader(user)
    deals = await search_pipeline_deals(session, q=q, limit=limit)
    return [_to_row(d) for d in deals]


# ---------------------------------------------------------------------------
# S19 slice 1 — full Pipeline surface endpoints (C1–C8).
# ---------------------------------------------------------------------------


class OpportunityRowOut(BaseModel):
    opportunity_id: uuid.UUID
    hubspot_deal_id: str | None
    name: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    stage_id: str | None
    stage_label: str | None
    is_closed_won: bool
    is_closed_lost: bool
    amount: Decimal | None
    currency: str | None
    close_date: date | None
    owner_id: uuid.UUID | None
    owner_name: str | None
    owner_email: str | None
    hubspot_last_activity_at: datetime | None
    sow_approval_state: str
    attention_flags: list[str]
    next_action_open_count: int
    next_action_min_due: date | None
    sow_count: int


class ClientRowOut(BaseModel):
    client_id: uuid.UUID
    client_name: str
    hubspot_company_id: str | None
    owner_id: uuid.UUID | None
    owner_name: str | None
    owner_email: str | None
    open_opp_count: int
    open_value_by_currency: dict[str, Decimal]
    stage_breakdown: dict[str, int]
    has_nda: bool
    has_msa: bool
    worst_sow_approval_state: str
    attention_flags: list[str]
    latest_activity_at: datetime | None
    next_action_min_due: date | None
    next_action_open_count: int


class OpportunityListOut(BaseModel):
    items: list[OpportunityRowOut]
    total: int
    page: int
    page_size: int


class ClientListOut(BaseModel):
    items: list[ClientRowOut]
    total: int
    page: int
    page_size: int


class SummaryOut(BaseModel):
    open_count: int
    open_value_by_currency: dict[str, Decimal]
    closing_this_month: int
    overdue_actions: int
    pending_approvals: int
    agreement_gaps: int


def _parse_filters(
    pipeline: str | None,
    stage: list[str] | None,
    owner: list[uuid.UUID] | None,
    readiness: list[str] | None,
    attention: list[str] | None,
    date_field: str | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
    include_closed: bool,
) -> PipelineFilters:
    if date_field is not None and date_field not in VALID_DATE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"date_field must be one of {sorted(VALID_DATE_FIELDS)}",
        )
    return PipelineFilters(
        pipeline=pipeline,
        stage=tuple(stage or ()),
        owner=tuple(owner or ()),
        readiness=tuple(readiness or ()),
        attention=tuple(attention or ()),
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
        search=search,
        include_closed=include_closed,
    )


def _parse_sort(raw: str | None, default: tuple[SortSpec, ...]) -> tuple[SortSpec, ...]:
    if not raw:
        return default
    specs: list[SortSpec] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        descending = chunk.startswith("-")
        column = chunk.lstrip("-+").strip()
        if column:
            specs.append(SortSpec(column=column, descending=descending))
    return tuple(specs) if specs else default


def _opp_to_out(row: OpportunityRow) -> OpportunityRowOut:
    return OpportunityRowOut(
        opportunity_id=row.opportunity_id,
        hubspot_deal_id=row.hubspot_deal_id,
        name=row.name,
        client_id=row.client_id,
        client_name=row.client_name,
        stage_id=row.stage_id,
        stage_label=row.stage_label,
        is_closed_won=row.is_closed_won,
        is_closed_lost=row.is_closed_lost,
        amount=row.amount,
        currency=row.currency,
        close_date=row.close_date,
        owner_id=row.owner_id,
        owner_name=row.owner_name,
        owner_email=row.owner_email,
        hubspot_last_activity_at=row.hubspot_last_activity_at,
        sow_approval_state=row.sow_approval_state,
        attention_flags=list(row.attention_flags),
        next_action_open_count=row.next_action_open_count,
        next_action_min_due=row.next_action_min_due,
        sow_count=row.sow_count,
    )


def _client_to_out(row: ClientRow) -> ClientRowOut:
    return ClientRowOut(
        client_id=row.client_id,
        client_name=row.client_name,
        hubspot_company_id=row.hubspot_company_id,
        owner_id=row.owner_id,
        owner_name=row.owner_name,
        owner_email=row.owner_email,
        open_opp_count=row.open_opp_count,
        open_value_by_currency=row.open_value_by_currency,
        stage_breakdown=row.stage_breakdown,
        has_nda=row.has_nda,
        has_msa=row.has_msa,
        worst_sow_approval_state=row.worst_sow_approval_state,
        attention_flags=list(row.attention_flags),
        latest_activity_at=row.latest_activity_at,
        next_action_min_due=row.next_action_min_due,
        next_action_open_count=row.next_action_open_count,
    )


@router.get("/opportunities", response_model=OpportunityListOut)
async def list_opportunities_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    pipeline: str | None = Query(None),
    stage: list[str] | None = Query(None),
    owner: list[uuid.UUID] | None = Query(None),
    readiness: list[str] | None = Query(None),
    attention: list[str] | None = Query(None),
    date_field: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None, max_length=200),
    include_closed: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
) -> OpportunityListOut:
    _require_reader(user)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, search, include_closed,
    )
    sort_spec = _parse_sort(sort, DEFAULT_SORT_OPPS)
    result = await _list_opportunities(
        session, filters=filters, page=page, page_size=page_size, sort=sort_spec
    )
    return OpportunityListOut(
        items=[_opp_to_out(r) for r in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/clients", response_model=ClientListOut)
async def list_clients_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    pipeline: str | None = Query(None),
    stage: list[str] | None = Query(None),
    owner: list[uuid.UUID] | None = Query(None),
    readiness: list[str] | None = Query(None),
    attention: list[str] | None = Query(None),
    date_field: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None, max_length=200),
    include_closed: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
) -> ClientListOut:
    _require_reader(user)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, search, include_closed,
    )
    sort_spec = _parse_sort(sort, DEFAULT_SORT_CLIENTS)
    result = await _list_clients(
        session, filters=filters, page=page, page_size=page_size, sort=sort_spec
    )
    return ClientListOut(
        items=[_client_to_out(r) for r in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/summary", response_model=SummaryOut)
async def summary_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    pipeline: str | None = Query(None),
    stage: list[str] | None = Query(None),
    owner: list[uuid.UUID] | None = Query(None),
    readiness: list[str] | None = Query(None),
    attention: list[str] | None = Query(None),
    date_field: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None, max_length=200),
    include_closed: bool = Query(False),
) -> SummaryOut:
    _require_reader(user)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, search, include_closed,
    )
    result: PipelineSummary = await _summary(session, filters=filters)
    return SummaryOut(
        open_count=result.open_count,
        open_value_by_currency=result.open_value_by_currency,
        closing_this_month=result.closing_this_month,
        overdue_actions=result.overdue_actions,
        pending_approvals=result.pending_approvals,
        agreement_gaps=result.agreement_gaps,
    )


# S19 slice 1 H1/H2: sync_status feed for the amber banner. Every worker
# writes a row here; the UI reads it to show "Synced N min ago" + the amber
# state when lag > 30 min OR last_error is set.
sync_router = APIRouter(prefix="/sync-status", tags=["sync-status"])


class SyncStatusRowOut(BaseModel):
    source: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    lag_seconds: int | None


class SyncStatusListOut(BaseModel):
    items: list[SyncStatusRowOut]


@sync_router.get("", response_model=SyncStatusListOut)
async def list_sync_status(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SyncStatusListOut:
    _require_reader(user)
    from sqlalchemy import select as _select

    from app.models.sync_status import SyncStatus

    rows = (
        await session.execute(_select(SyncStatus).order_by(SyncStatus.source.asc()))
    ).scalars().all()
    return SyncStatusListOut(
        items=[
            SyncStatusRowOut(
                source=r.source,
                last_success_at=r.last_success_at,
                last_attempt_at=r.last_attempt_at,
                last_error=r.last_error,
                lag_seconds=r.lag_seconds,
            )
            for r in rows
        ]
    )
