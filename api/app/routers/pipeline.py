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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.deals import LEADER_ROLES
from app.services.hubspot_pipeline import (
    BUSINESS_TZ,
    ClientRow,
    DEFAULT_SORT_CLIENTS,
    DEFAULT_SORT_OPPS,
    OpportunityRow,
    PipelineDeal,
    PipelineFilters,
    PipelineSummary,
    SortSpec,
    StageCount,
    VALID_DATE_FIELDS,
    VALID_MISSING_FIELDS,
    VALID_OPEN_CLOSED,
    get_pipeline_deal,
    list_clients as _list_clients,
    list_opportunities as _list_opportunities,
    list_pipeline_deals,
    resolve_date_preset,
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
    hubspot_pipeline_id: str | None = None
    business_unit: str | None = None


class ClientRowOut(BaseModel):
    client_id: uuid.UUID
    client_name: str
    hubspot_company_id: str | None
    # D2 — three ownership concepts; keep them separate in the wire model.
    account_owner_id: str | None = None
    account_owner_name: str | None = None
    account_owner_email: str | None = None
    owner_id: uuid.UUID | None
    owner_name: str | None
    owner_email: str | None
    matching_deal_count: int
    total_open_deal_count: int
    # Legacy alias kept so older callers (Command center card, tests)
    # continue to read `open_opp_count` while the field is renamed.
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


class StageCountOut(BaseModel):
    pipeline_id: str | None
    stage_id: str | None
    stage_label: str | None
    stage_order: int | None
    count: int
    is_closed_won: bool = False
    is_closed_lost: bool = False


class FreshnessOut(BaseModel):
    """Response envelope §3 — freshness watermark for the dataset."""

    source: str = "hubspot_mirror"
    received_at: datetime | None = None
    processed_at: datetime | None = None
    reconciled_at: datetime | None = None
    state: str = "Unknown"


class ListMetaOut(BaseModel):
    """Meta block per response envelope §3.

    Echoes filters the caller sent so the SPA can render the "active
    filters" strip without re-parsing its own URL, and carries the
    stage-count reconciliation payload + explicit unknown-stage bucket
    (A5, T35, T40, D9).
    """

    freshness: FreshnessOut
    unknown_bucket: int = 0
    stage_counts: list[StageCountOut] = Field(default_factory=list)
    filters_echo: dict[str, Any] = Field(default_factory=dict)
    business_timezone: str = BUSINESS_TZ


class OpportunityListOut(BaseModel):
    items: list[OpportunityRowOut]
    total: int
    page: int
    page_size: int
    meta: ListMetaOut


class ClientListOut(BaseModel):
    items: list[ClientRowOut]
    total: int
    page: int
    page_size: int
    meta: ListMetaOut


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
    date_preset: str | None,
    search: str | None,
    include_closed: bool,
    account_owner: list[str] | None = None,
    business_unit: list[str] | None = None,
    open_closed: str | None = None,
    missing: list[str] | None = None,
) -> PipelineFilters:
    if date_field is not None and date_field not in VALID_DATE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"date_field must be one of {sorted(VALID_DATE_FIELDS)}",
        )
    if open_closed is not None and open_closed not in VALID_OPEN_CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"open_closed must be one of {sorted(VALID_OPEN_CLOSED)}",
        )
    if missing:
        bad = [m for m in missing if m not in VALID_MISSING_FIELDS]
        if bad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"missing must be a subset of {sorted(VALID_MISSING_FIELDS)}",
            )
    resolved_from, resolved_to = date_from, date_to
    if date_preset:
        resolved_from, resolved_to = resolve_date_preset(
            date_preset, date_from=date_from, date_to=date_to
        )
    return PipelineFilters(
        pipeline=pipeline,
        stage=tuple(stage or ()),
        owner=tuple(owner or ()),
        account_owner=tuple(account_owner or ()),
        business_unit=tuple(business_unit or ()),
        readiness=tuple(readiness or ()),
        attention=tuple(attention or ()),
        date_field=date_field,
        date_from=resolved_from,
        date_to=resolved_to,
        search=search,
        include_closed=include_closed,
        open_closed=open_closed,
        missing=tuple(missing or ()),
    )


def _filters_echo(filters: PipelineFilters) -> dict[str, Any]:
    """Echo the filter set into the response envelope's meta block."""

    def _serialize_uuid_tuple(t):
        return [str(x) for x in t]

    return {
        "pipeline": filters.pipeline,
        "stage": list(filters.stage),
        "owner": _serialize_uuid_tuple(filters.owner),
        "account_owner": list(filters.account_owner),
        "business_unit": list(filters.business_unit),
        "readiness": list(filters.readiness),
        "attention": list(filters.attention),
        "date_field": filters.date_field,
        "date_from": filters.date_from.isoformat() if filters.date_from else None,
        "date_to": filters.date_to.isoformat() if filters.date_to else None,
        "search": filters.search,
        "include_closed": filters.include_closed,
        "open_closed": filters.open_closed,
        "missing": list(filters.missing),
    }


async def _load_freshness(session: AsyncSession, *, now: datetime | None = None) -> FreshnessOut:
    """Compose the freshness watermark object per contracts §3.

    Reads ``sync_status`` (W1 owns the writer) and folds the three
    HubSpot watermarks into a single record for the SPA. When W1 has
    not yet landed rows (fresh worktree), returns ``state='Unknown'``.
    """

    from app.models.sync_status import SyncStatus

    rows = (
        await session.execute(_select(SyncStatus).where(SyncStatus.source.like("hubspot%")))
    ).scalars().all()
    by_source = {r.source: r for r in rows}
    received = by_source.get("hubspot_webhook_received") or by_source.get("hubspot_webhook")
    processed = by_source.get("hubspot_webhook_processed") or by_source.get("hubspot_webhook")
    reconciled = by_source.get("hubspot_reconcile") or by_source.get("hubspot_backfill")
    state = "Unknown"
    if processed and processed.last_success_at:
        lag = processed.lag_seconds or 0
        if processed.last_error:
            state = "Failed"
        elif lag > 120:
            state = "Stale"
        else:
            state = "verified working"
    return FreshnessOut(
        source="hubspot_mirror",
        received_at=received.last_success_at if received else None,
        processed_at=processed.last_success_at if processed else None,
        reconciled_at=reconciled.last_success_at if reconciled else None,
        state=state,
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
        hubspot_pipeline_id=row.hubspot_pipeline_id,
        business_unit=row.business_unit,
    )


def _client_to_out(row: ClientRow) -> ClientRowOut:
    return ClientRowOut(
        client_id=row.client_id,
        client_name=row.client_name,
        hubspot_company_id=row.hubspot_company_id,
        account_owner_id=row.account_owner_id,
        account_owner_name=row.account_owner_name,
        account_owner_email=row.account_owner_email,
        owner_id=row.owner_id,
        owner_name=row.owner_name,
        owner_email=row.owner_email,
        matching_deal_count=row.matching_deal_count,
        total_open_deal_count=row.total_open_deal_count,
        open_opp_count=row.matching_deal_count,
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


def _stage_counts_to_out(counts) -> list[StageCountOut]:
    return [
        StageCountOut(
            pipeline_id=c.pipeline_id,
            stage_id=c.stage_id,
            stage_label=c.stage_label,
            stage_order=c.stage_order,
            count=c.count,
            is_closed_won=c.is_closed_won,
            is_closed_lost=c.is_closed_lost,
        )
        for c in counts
    ]


_ALLOWED_PAGE_SIZES: frozenset[int] = frozenset({25, 50, 100})


def _validate_page_size(page_size: int) -> int:
    """Contracts §4: page_size ∈ {25, 50, 100}. Anything else rejected."""

    if page_size not in _ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"page_size must be one of {sorted(_ALLOWED_PAGE_SIZES)}",
        )
    return page_size


@router.get("/opportunities", response_model=OpportunityListOut)
async def list_opportunities_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    pipeline: str | None = Query(None),
    stage: list[str] | None = Query(None),
    owner: list[uuid.UUID] | None = Query(None),
    account_owner: list[str] | None = Query(None),
    business_unit: list[str] | None = Query(None),
    readiness: list[str] | None = Query(None),
    attention: list[str] | None = Query(None),
    date_field: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    date_preset: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    include_closed: bool = Query(False),
    open_closed: str | None = Query(None),
    missing: list[str] | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
) -> OpportunityListOut:
    _require_reader(user)
    _validate_page_size(page_size)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, date_preset, search, include_closed,
        account_owner=account_owner,
        business_unit=business_unit,
        open_closed=open_closed,
        missing=missing,
    )
    sort_spec = _parse_sort(sort, DEFAULT_SORT_OPPS)
    result = await _list_opportunities(
        session, filters=filters, page=page, page_size=page_size, sort=sort_spec
    )
    freshness = await _load_freshness(session)
    return OpportunityListOut(
        items=[_opp_to_out(r) for r in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        meta=ListMetaOut(
            freshness=freshness,
            unknown_bucket=result.unknown_bucket,
            stage_counts=_stage_counts_to_out(result.stage_counts),
            filters_echo=_filters_echo(filters),
            business_timezone=BUSINESS_TZ,
        ),
    )


@router.get("/clients", response_model=ClientListOut)
async def list_clients_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    pipeline: str | None = Query(None),
    stage: list[str] | None = Query(None),
    owner: list[uuid.UUID] | None = Query(None),
    account_owner: list[str] | None = Query(None),
    business_unit: list[str] | None = Query(None),
    readiness: list[str] | None = Query(None),
    attention: list[str] | None = Query(None),
    date_field: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    date_preset: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    include_closed: bool = Query(False),
    open_closed: str | None = Query(None),
    missing: list[str] | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
) -> ClientListOut:
    _require_reader(user)
    _validate_page_size(page_size)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, date_preset, search, include_closed,
        account_owner=account_owner,
        business_unit=business_unit,
        open_closed=open_closed,
        missing=missing,
    )
    sort_spec = _parse_sort(sort, DEFAULT_SORT_CLIENTS)
    result = await _list_clients(
        session, filters=filters, page=page, page_size=page_size, sort=sort_spec
    )
    freshness = await _load_freshness(session)
    # Reuse the opportunity stage-count aggregation so client + deal
    # views render identical chips (aggregate contract §"Aggregate").
    opp_result = await _list_opportunities(
        session, filters=filters, page=1, page_size=1
    )
    return ClientListOut(
        items=[_client_to_out(r) for r in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        meta=ListMetaOut(
            freshness=freshness,
            unknown_bucket=opp_result.unknown_bucket,
            stage_counts=_stage_counts_to_out(opp_result.stage_counts),
            filters_echo=_filters_echo(filters),
            business_timezone=BUSINESS_TZ,
        ),
    )


@router.get("/summary", response_model=SummaryOut)
async def summary_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    pipeline: str | None = Query(None),
    stage: list[str] | None = Query(None),
    owner: list[uuid.UUID] | None = Query(None),
    account_owner: list[str] | None = Query(None),
    business_unit: list[str] | None = Query(None),
    readiness: list[str] | None = Query(None),
    attention: list[str] | None = Query(None),
    date_field: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    date_preset: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    include_closed: bool = Query(False),
    open_closed: str | None = Query(None),
    missing: list[str] | None = Query(None),
) -> SummaryOut:
    _require_reader(user)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, date_preset, search, include_closed,
        account_owner=account_owner,
        business_unit=business_unit,
        open_closed=open_closed,
        missing=missing,
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
