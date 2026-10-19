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

import csv
import io
import uuid
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select as _select
from sqlalchemy import text as _text
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
    VALID_DATE_FIELDS,
    VALID_MISSING_FIELDS,
    VALID_OPEN_CLOSED,
    get_opportunity_row,
    get_pipeline_deal,
    list_clients as _list_clients,
    list_opportunities as _list_opportunities,
    list_pipeline_deals,
    list_pipeline_facets,
    list_pipeline_stages,
    resolve_date_preset,
    search_pipeline_deals,
    scope_pipeline_filters,
    matching_opportunity_ids,
    summary as _summary,
)
from app.services.pipeline_workspace import (
    PAGE_SIZES,
    SOW_FILTERS,
    WorkspaceFilters,
    build_workspace,
    export_workspace,
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
    source_origin: str = "hubspot"
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
        source_origin=deal.source_origin,
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
        filters=await scope_pipeline_filters(session, user, PipelineFilters(include_closed=True)),
    )
    return PipelineListResponse(
        items=[_to_row(d) for d in deals],
        total_open=total_open,
        total_closed_lost=total_closed_lost,
        page=page,
        size=size,
    )


@router.get("/deals/{opportunity_id:uuid}", response_model=PipelineDealRow)
async def get_deal(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PipelineDealRow:
    _require_reader(user)
    deal = await get_pipeline_deal(session, opportunity_id, filters=await scope_pipeline_filters(session, user, PipelineFilters(include_closed=True)))
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
    deals = await search_pipeline_deals(session, q=q, limit=limit, filters=await scope_pipeline_filters(session, user, PipelineFilters(include_closed=True)))
    return [_to_row(d) for d in deals]


# ---------------------------------------------------------------------------
# S19 slice 1 — full Pipeline surface endpoints (C1–C8).
# ---------------------------------------------------------------------------


class OpportunityRowOut(BaseModel):
    source_origin: str = "hubspot"
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
    source_owner_id: str | None = None
    owner_archived: bool | None = None
    hubspot_last_activity_at: datetime | None
    sow_approval_state: str
    attention_flags: list[str]
    next_action_open_count: int
    next_action_min_due: date | None
    sow_count: int
    hubspot_pipeline_id: str | None = None
    business_unit: str | None = None
    # S20 W6 Session 4b item 2 · latest-comment preview on the row.
    latest_comment_body: str | None = None
    latest_comment_author: str | None = None
    latest_comment_pinned: bool = False
    latest_comment_at: datetime | None = None


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
    # S20 W2 Session 3b Rev-2 · per-chip value totals (L06).
    open_value_by_currency: dict[str, Decimal] = Field(default_factory=dict)


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
    sows_in_progress: int = 0
    agreements_uploaded: int = 0
    ceo_pending: int = 0


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
    client: list[uuid.UUID] | None = None,
    group: list[uuid.UUID] | None = None,
    watching_ids: tuple[uuid.UUID, ...] | None = None,
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
        client=tuple(client or ()),
        group=tuple(group or ()),
        watching_ids=watching_ids,
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


_FRESHNESS_STATE = {"fresh": "verified working", "stale": "Stale", "failed": "Failed"}


async def _load_freshness(session: AsyncSession, *, now: datetime | None = None) -> FreshnessOut:
    """Compose the freshness watermark object per contracts §3.

    S23-PL1 item 8: ``state`` and ``reconciled_at`` come from the last deal
    sync run (:func:`app.services.hubspot_sync_runs.compute_sync_health`), the
    same source as ``GET /hubspot/sync-health``. The intake heartbeat
    (``hubspot_webhook`` / ``hubspot_consumer`` rows) is no longer read.
    ``received_at`` and ``processed_at`` remain the per-event webhook
    watermarks, reported for information only.
    """

    from app.models.sync_status import SyncStatus
    from app.services.hubspot_sync_runs import compute_sync_health

    health = await compute_sync_health(session, now=now)
    rows = (
        await session.execute(_select(SyncStatus).where(SyncStatus.source.in_(
            ("hubspot_webhook_received", "hubspot_webhook_processed"))))
    ).scalars().all()
    by_source = {r.source: r for r in rows}
    received = by_source.get("hubspot_webhook_received")
    processed = by_source.get("hubspot_webhook_processed")
    last_success = health["last_success_at"]
    return FreshnessOut(
        source="hubspot_mirror",
        received_at=received.last_success_at if received else None,
        processed_at=processed.last_success_at if processed else None,
        reconciled_at=datetime.fromisoformat(last_success.replace("Z", "+00:00")) if last_success else None,
        state=_FRESHNESS_STATE[health["state"]],
    )


async def _resolve_scope(
    session: AsyncSession,
    *,
    user: AuthUser,
    group_ids: list[uuid.UUID] | None,
    watching: bool,
) -> dict[str, Any]:
    """S20 W6 · resolve group + watching axes into an opportunity-id scope.

    - Manual opportunity groups → their member ids.
    - Manual client groups → the client_ids, funneled via `filters.client`.
    - Rule-based groups → the group's `filter_json` is evaluated by
      `list_opportunities` (directive: no second engine) and the returned
      row ids become the scope.
    - Watchlist → the caller's own `WatchedItem` rows for kind=opportunity
      (+ client ids as extra `filters.client` scope).

    Returns a dict with the axes to apply on top of the caller's filters:
    `{"opportunity_id": tuple | None, "client": tuple | None,
    "watching_ids": tuple | None}`.
    """

    from sqlalchemy import select as _select

    from app.models.tracking_group import TrackingGroup, TrackingGroupMember
    from app.models.watchlist import WatchedItem
    from app.services.canonical_user import resolve_viewer
    from app.services.tracking_group import load_group

    opp_scope: set[uuid.UUID] = set()
    client_scope: set[uuid.UUID] = set()
    watching_ids: set[uuid.UUID] | None = None
    axis_used = False
    # S23-PL2: watches and groups are keyed on the DealGate user id, which
    # differs from the login id for HubSpot-created and invited users.
    owner = user
    if group_ids or watching:
        viewer = await resolve_viewer(session, user)
        if viewer.user_id is not None and viewer.user_id != user.id:
            owner = AuthUser(viewer.user_id, user.email, user.name, tuple(user.groups))

    if group_ids:
        axis_used = True
        groups = (
            await session.execute(
                _select(TrackingGroup).where(TrackingGroup.id.in_(group_ids))
            )
        ).scalars().all()
        for grp in groups:
            await load_group(session, actor=owner, group_id=grp.id)
            if grp.filter_json:
                # Rule-based: evaluate through the same engine.
                sub_filters = PipelineFilters(
                    pipeline=grp.filter_json.get("pipeline"),
                    stage=tuple(grp.filter_json.get("stage") or ()),
                    owner=tuple(uuid.UUID(o) for o in (grp.filter_json.get("owner") or [])),
                    business_unit=tuple(grp.filter_json.get("business_unit") or ()),
                    readiness=tuple(grp.filter_json.get("readiness") or ()),
                    attention=tuple(grp.filter_json.get("attention") or ()),
                    open_closed=grp.filter_json.get("open_closed"),
                    include_closed=bool(grp.filter_json.get("include_closed")),
                )
                sub_filters = await scope_pipeline_filters(session, user, sub_filters)
                opp_scope.update(await matching_opportunity_ids(session, sub_filters))
            else:
                members = (
                    await session.execute(
                        _select(TrackingGroupMember).where(
                            TrackingGroupMember.group_id == grp.id
                        )
                    )
                ).scalars().all()
                if grp.member_kind == "opportunity":
                    for m in members:
                        opp_scope.add(m.member_id)
                elif grp.member_kind == "client":
                    for m in members:
                        client_scope.add(m.member_id)

    if client_scope:
        grouped_clients = await scope_pipeline_filters(session, user,
            PipelineFilters(client=tuple(client_scope), include_closed=True))
        opp_scope.update(await matching_opportunity_ids(session, grouped_clients))
        client_scope.clear()

    if watching:
        axis_used = True
        rows = (
            await session.execute(
                _select(WatchedItem).where(WatchedItem.user_id == owner.id)
            )
        ).scalars().all()
        watching_ids = set()
        for r in rows:
            if r.kind == "opportunity":
                watching_ids.add(r.item_id)
            elif r.kind == "client":
                client_scope.add(r.item_id)

        if client_scope:
            watched_clients = await scope_pipeline_filters(session, user,
                PipelineFilters(client=tuple(client_scope), include_closed=True))
            watching_ids.update(await matching_opportunity_ids(session, watched_clients))
            client_scope.clear()

    return {
        "opportunity_id": (
            tuple(opp_scope) if (group_ids and not watching) else
            (tuple(opp_scope & (watching_ids or set())) if group_ids else
             tuple(watching_ids or ()) if axis_used else None)
        ),
        "client": tuple(client_scope) if client_scope else None,
        "watching_ids": tuple(watching_ids) if watching_ids is not None else None,
    }


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
        source_origin=row.source_origin,
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
        source_owner_id=row.source_owner_id,
        owner_archived=row.owner_archived,
        hubspot_last_activity_at=row.hubspot_last_activity_at,
        sow_approval_state=row.sow_approval_state,
        attention_flags=list(row.attention_flags),
        next_action_open_count=row.next_action_open_count,
        next_action_min_due=row.next_action_min_due,
        sow_count=row.sow_count,
        hubspot_pipeline_id=row.hubspot_pipeline_id,
        business_unit=row.business_unit,
        latest_comment_body=getattr(row, "latest_comment_body", None),
        latest_comment_author=getattr(row, "latest_comment_author", None),
        latest_comment_pinned=getattr(row, "latest_comment_pinned", False),
        latest_comment_at=getattr(row, "latest_comment_at", None),
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
            open_value_by_currency=dict(getattr(c, "open_value_by_currency", {})),
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
    client: list[uuid.UUID] | None = Query(None),
    group: list[uuid.UUID] | None = Query(None),
    watching: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
) -> OpportunityListOut:
    _require_reader(user)
    _validate_page_size(page_size)
    # S20 W6 · resolve group + watching axes into opportunity_id scope.
    scope = await _resolve_scope(session, user=user, group_ids=group, watching=watching)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, date_preset, search, include_closed,
        account_owner=account_owner,
        business_unit=business_unit,
        open_closed=open_closed,
        missing=missing,
        client=tuple((client or []) + list(scope["client"] or ())) or None,
        watching_ids=scope["watching_ids"],
    )
    if scope["opportunity_id"] is not None:
        filters = replace(filters, opportunity_id=scope["opportunity_id"])
    filters = await scope_pipeline_filters(session, user, filters)
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
    show_clients_without_matches: bool = Query(False),
    client: list[uuid.UUID] | None = Query(None),
    group: list[uuid.UUID] | None = Query(None),
    watching: bool = Query(False),
) -> ClientListOut:
    _require_reader(user)
    _validate_page_size(page_size)
    scope = await _resolve_scope(session, user=user, group_ids=group, watching=watching)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, date_preset, search, include_closed,
        account_owner=account_owner,
        business_unit=business_unit,
        open_closed=open_closed,
        missing=missing,
        client=client,
        watching_ids=scope["watching_ids"],
    )
    if scope["opportunity_id"] is not None:
        filters = replace(filters, opportunity_id=scope["opportunity_id"])
    filters = await scope_pipeline_filters(session, user, replace(filters, show_clients_without_matches=show_clients_without_matches))
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
    client: list[uuid.UUID] | None = Query(None),
    group: list[uuid.UUID] | None = Query(None),
    watching: bool = Query(False),
) -> SummaryOut:
    _require_reader(user)
    scope = await _resolve_scope(session, user=user, group_ids=group, watching=watching)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, date_preset, search, include_closed,
        account_owner=account_owner,
        business_unit=business_unit,
        open_closed=open_closed,
        missing=missing,
        client=client,
        watching_ids=scope["watching_ids"],
    )
    if scope["opportunity_id"] is not None:
        filters = replace(filters, opportunity_id=scope["opportunity_id"])
    filters = await scope_pipeline_filters(session, user, filters)
    result: PipelineSummary = await _summary(session, filters=filters)
    return SummaryOut(
        open_count=result.open_count,
        open_value_by_currency=result.open_value_by_currency,
        closing_this_month=result.closing_this_month,
        overdue_actions=result.overdue_actions,
        pending_approvals=result.pending_approvals,
        agreement_gaps=result.agreement_gaps,
        sows_in_progress=result.sows_in_progress,
        agreements_uploaded=result.agreements_uploaded,
        ceo_pending=result.ceo_pending,
    )


# S20 W2 · single-opportunity for the /deals/:id detail page. Returns
# the same shape /pipeline/opportunities returns per row so the SPA
# reuses OpportunityRow (name, stage_id, sow_state, attention_flags,
# next_action counts, BU, pipeline_id, is_closed_won/lost).
@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRowOut)
async def get_opportunity_endpoint(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunityRowOut:
    _require_reader(user)
    filters = await scope_pipeline_filters(session, user, PipelineFilters(include_closed=True))
    permitted = await get_pipeline_deal(session, opportunity_id, filters=filters)
    if permitted is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    row = await get_opportunity_row(session, opportunity_id=opportunity_id, filters=filters)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found"
        )
    return _opp_to_out(row)


# S20 W2 · ordered stage strip on /deals/:id. Powered by the mirror in
# `hubspot_stage`; zero-count stages included so the strip shows every
# stage the deal could sit in, in mirror display order.
@router.get("/pipelines/{pipeline_id}/stages", response_model=list[StageCountOut])
async def list_pipeline_stages_endpoint(
    pipeline_id: str,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[StageCountOut]:
    _require_reader(user)
    stages = await list_pipeline_stages(session, pipeline_id=pipeline_id)
    return _stage_counts_to_out(stages)


class OwnerFacetOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None


class PipelineFacetsOut(BaseModel):
    owners: list[OwnerFacetOut]
    business_units: list[str]


# S20 W2 Session 3b Rev-2 · facets for the Pipeline filter bar.
# `owners` populates the Owner multi-select; `business_units` populates
# the BU select. Options describe the normalized, authorized matching population.
@router.get("/facets", response_model=PipelineFacetsOut)
async def list_pipeline_facets_endpoint(
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
    client: list[uuid.UUID] | None = Query(None),
    group: list[uuid.UUID] | None = Query(None),
    watching: bool = Query(False),
) -> PipelineFacetsOut:
    _require_reader(user)
    scope = await _resolve_scope(session, user=user, group_ids=group, watching=watching)
    filters = _parse_filters(
        pipeline, stage, owner, readiness, attention,
        date_field, date_from, date_to, date_preset, search, include_closed,
        account_owner=account_owner, business_unit=business_unit,
        open_closed=open_closed, missing=missing, client=client,
        watching_ids=scope["watching_ids"],
    )
    if scope["opportunity_id"] is not None:
        filters = replace(filters, opportunity_id=scope["opportunity_id"])
    filters = await scope_pipeline_filters(session, user, filters)
    facets = await list_pipeline_facets(session, filters=filters)
    return PipelineFacetsOut(
        owners=[
            OwnerFacetOut(id=o.id, name=o.name, email=o.email) for o in facets.owners
        ],
        business_units=list(facets.business_units),
    )


# ---------------------------------------------------------------------------
# S23-PL2 — the Pipeline workspace (B1) and its export (B10).
# Everything is computed in app.services.pipeline_workspace from one
# population with one filter function; this layer parses and validates.
# Money is a decimal string (CLAUDE.md rule 2), dates are LA calendar dates.
# ---------------------------------------------------------------------------

_PAGE_SIZE_DETAIL = "page_size must be one of 25, 50, 100"

Tab = Literal["deals", "clients"]
Status = Literal["open", "all", "won", "lost", "hold"]
BusinessUnitFilter = Literal["ST21", "IT Avalon", "Retro Rabbit", "unmapped"]
Attention = Literal["overdue", "past_close", "no_owner", "inactive", "pending_approval", "any"]
Missing = Literal["owner", "close", "activity", "next_action", "nda", "msa", "agreements"]
DateField = Literal["close", "created", "activity"]
DatePreset = Literal["any", "passed", "next7", "next30", "next90", "last7", "last30", "last90", "month",
                     "quarter", "custom"]
Sort = Literal["value", "close", "activity", "name"]
Layout = Literal["list", "board"]
# S24-AG1 B10: the seven agreement states (agreement_status.DOC_STATES, docs/reference/openapi-agreements.yaml).
DocState = Literal["client", "standard", "covered", "missing", "due_later", "not_needed", "existing_none"]


class WorkspaceOwnerOut(BaseModel):
    name: str | None
    state: Literal["active", "archived", "none"]


class WorkspaceAgreementsOut(BaseModel):
    nda_on_file: bool = Field(description="True only when the client holds a client copy or a standard copy.")
    msa_on_file: bool = Field(description="True only when the client holds a client copy or a standard copy.")
    nda_state: DocState | None = Field(
        description="S24-AG1: the client's NDA state from the shared agreement service; null for a deal with no client.")
    msa_state: DocState | None = Field(
        description="S24-AG1: the client's MSA state from the shared agreement service; null for a deal with no client.")


class WorkspaceDealClientOut(BaseModel):
    id: uuid.UUID | None
    name: str | None


class WorkspaceNextActionOut(BaseModel):
    id: uuid.UUID
    text: str | None
    due_on: date | None


class WorkspaceDealRowOut(BaseModel):
    id: uuid.UUID
    title: str
    client: WorkspaceDealClientOut
    stage_id: int | None
    stage_label: str | None
    status: Literal["open", "hold", "won", "lost"] = Field(
        description="Additive: open (Hold reads hold and counts as open), won or lost.")
    amount: str | None = Field(description="Decimal string; null when HubSpot has no amount.")
    currency: str | None
    business_unit: str | None
    region: str | None
    region_note: str | None
    hubspot_region: str | None
    bu_unmapped: bool
    deal_owner: WorkspaceOwnerOut
    account_owner: WorkspaceOwnerOut
    close_date: date | None
    created_date: date | None
    last_activity_date: date | None
    days_since_activity: int | None
    sow_state: str
    sow_state_label: str
    sow_count: int
    agreements: WorkspaceAgreementsOut
    next_action: WorkspaceNextActionOut | None
    flags: list[Literal["action_overdue", "close_passed", "no_owner", "inactive_14d"]]
    watching: bool
    hubspot_deal_id: str | None = Field(description="Only for building the HubSpot link; never display text.")
    pipeline_label: str | None


class WorkspaceClientRowOut(BaseModel):
    id: uuid.UUID
    name: str
    account_owner: WorkspaceOwnerOut
    matching_deals: int
    open_deals: int
    matching_value_usd: str | None
    earliest_close_date: date | None
    last_activity_date: date | None
    days_since_activity: int | None
    agreements: WorkspaceAgreementsOut
    flags: list[Literal["no_owner", "action_overdue", "close_passed"]]
    hubspot_company_id: str | None


class OpenDealsMetricOut(BaseModel):
    value: int
    accounts: int
    drill: dict[str, Any]


class OpenValueMetricOut(BaseModel):
    value: str
    includes_on_hold: int
    deals: int
    drill: dict[str, Any]


class ClosingMetricOut(BaseModel):
    value: int
    value_usd: str
    drill: dict[str, Any]


class OverdueMetricOut(BaseModel):
    value: int
    with_next_action: int
    drill: dict[str, Any]


class PendingMetricOut(BaseModel):
    value: int
    drill: dict[str, Any]


class AgreementGapMetricOut(BaseModel):
    """S24-AG1 B10: clients that need attention (net new, past stage 1, NDA or MSA missing) among the
    clients with a deal in the filtered population; the drill lists exactly them (every status)."""

    value: int
    clients_total: int = Field(description="Clients with a deal in the same list without the missing filter.")
    any_agreement_files: bool = Field(description="Whether any agreement file exists anywhere (kept; unused by the page).")
    drill: dict[str, Any]


class WorkspaceMetricsOut(BaseModel):
    open_deals: OpenDealsMetricOut
    open_value_usd: OpenValueMetricOut
    closing_this_month: ClosingMetricOut
    overdue_next_actions: OverdueMetricOut
    pending_approvals: PendingMetricOut
    agreement_gap_clients: AgreementGapMetricOut


class WorkspaceStageOut(BaseModel):
    stage_id: int
    label: str
    full_label: str
    deals: int
    known_value_usd: str
    deals_without_amount: int


class WorkspaceFocusOut(BaseModel):
    all_open: int
    closing_this_month: int
    mine: int | None
    mine_available: bool
    needs_attention: int
    watching: int


class WorkspaceLaneOut(BaseModel):
    total: int
    value_usd: str
    deals: list[WorkspaceDealRowOut]


class WorkspacePageOut(BaseModel):
    number: int
    size: int
    total_rows: int
    total_value_usd: str | None


class WorkspaceTabCountsOut(BaseModel):
    deals: int
    clients: int


class WorkspaceOwnerOptionOut(BaseModel):
    id: str
    name: str


class WorkspaceBusinessUnitOptionOut(BaseModel):
    business_unit: str
    regions: list[str]


class WorkspaceSowStateOptionOut(BaseModel):
    value: str
    label: str


class WorkspaceOptionsOut(BaseModel):
    deal_owners: list[WorkspaceOwnerOptionOut]
    account_owners: list[WorkspaceOwnerOptionOut]
    business_units: list[WorkspaceBusinessUnitOptionOut]
    sow_states: list[WorkspaceSowStateOptionOut]


class WorkspaceOut(BaseModel):
    freshness: dict[str, Any] = Field(description="GET /hubspot/sync-health, unchanged (contract Freshness).")
    metrics: WorkspaceMetricsOut
    stages: list[WorkspaceStageOut]
    focus: WorkspaceFocusOut
    unmapped_regions: int
    rows: list[WorkspaceDealRowOut] | list[WorkspaceClientRowOut]
    rows_by_stage: dict[str, WorkspaceLaneOut] | None
    page: WorkspacePageOut
    tab_counts: WorkspaceTabCountsOut
    options: WorkspaceOptionsOut
    today: date


def _workspace_filters(
    tab: Tab = Query("deals"),
    status_: Status = Query("open", alias="status"),
    stage: list[int] | None = Query(None),
    owner: list[str] | None = Query(None),
    account_owner: list[str] | None = Query(None),
    bu: list[BusinessUnitFilter] | None = Query(None),
    q: str | None = Query(None, max_length=120),
    sow: str | None = Query(None),
    attention: Attention | None = Query(None),
    missing: Missing | None = Query(None),
    group: uuid.UUID | None = Query(None),
    watching: bool = Query(False),
    mine: bool = Query(False),
    date_field: DateField = Query("close"),
    date_preset: DatePreset = Query("any"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    include_unmatched_clients: bool = Query(False),
    sort: Sort = Query("value"),
    client: uuid.UUID | None = Query(None),
) -> WorkspaceFilters:
    """The workspace filters shared by ``/workspace`` and ``/export`` (422 on bad values)."""
    if stage and any(value < 1 or value > 9 for value in stage):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "stage must be between 1 and 9")
    if sow is not None and sow not in SOW_FILTERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"sow must be one of {', '.join(SOW_FILTERS)}")
    if date_preset == "custom" and date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_from must be on or before date_to")

    def _clean(values: list[str] | None) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value.strip() for value in values or () if value.strip()))

    return WorkspaceFilters(
        tab=tab, status=status_, stage=tuple(sorted(set(stage or ()))), owner=_clean(owner),
        account_owner=_clean(account_owner), bu=tuple(dict.fromkeys(bu or ())), q=(q or "").strip() or None,
        sow=sow, attention=attention, missing=missing, group=group, watching=watching, mine=mine,
        date_field=date_field, date_preset=date_preset, date_from=date_from, date_to=date_to,
        include_unmatched_clients=include_unmatched_clients, sort=sort, client=client,
    )


@router.get("/workspace", response_model=WorkspaceOut)
async def workspace_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    filters: WorkspaceFilters = Depends(_workspace_filters),
    layout: Layout = Query("list"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25),
) -> dict[str, Any]:
    """S23-PL2 B1: everything the Pipeline page shows, in one request."""
    _require_reader(user)
    if page_size not in PAGE_SIZES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _PAGE_SIZE_DETAIL)
    return await build_workspace(
        session, actor=user, filters=replace(filters, layout=layout, page=page, page_size=page_size))


@router.get("/export")
async def export_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    filters: WorkspaceFilters = Depends(_workspace_filters),
) -> StreamingResponse:
    """S23-PL2 B10: every filtered row of the active tab as CSV (UTF-8 BOM, CRLF).

    The same roles as the Reports export (Presales stays without export).
    Every cell is neutralised against spreadsheet formulas.
    """
    from app.routers.reports import _READ_ROLES as export_roles

    if not any(role in export_roles for role in user.groups):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
    # One consistent snapshot for every statement, as the Reports export does.
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        if session.in_transaction():
            raise HTTPException(status.HTTP_409_CONFLICT, "Pipeline export requires a fresh snapshot transaction")
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        await session.execute(_text("SET TRANSACTION READ ONLY"))
    elif dialect == "sqlite" and not session.in_transaction():
        await session.execute(_text("BEGIN"))
    header, rows = await export_workspace(session, actor=user, filters=filters)

    def _stream():
        buffer = io.StringIO()
        writer = csv.writer(buffer)  # CRLF line endings
        yield "﻿"
        for row in (header, *rows):
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()

    return StreamingResponse(
        _stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="DealGate_Pipeline_{filters.tab}.csv"'},
    )


# S19 slice 1 H1/H2: raw sync_status feed (one row per source). S23-PL1: the
# Pipeline "Last synced" label now comes from GET /hubspot/sync-health; the old
# page still reads lag_seconds / last_error from these rows for its amber chip
# until S23-PL2 replaces it. Settings > Integrations reads them for liveness.
sync_router = APIRouter(prefix="/sync-status", tags=["sync-status"])


class SyncStatusRowOut(BaseModel):
    source: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    lag_seconds: int | None


class SyncStatusListOut(BaseModel):
    items: list[SyncStatusRowOut]


# S23-PL1 item 2: GET /hubspot/sync-health — the ``Freshness`` schema in
# docs/reference/openapi-pipeline.yaml. Freshness comes from the last deal
# sync run, never from the intake heartbeat. Readable by every Pipeline role.
sync_health_router = APIRouter(prefix="/hubspot", tags=["hubspot"])


class SyncHealthErrorOut(BaseModel):
    hubspot_id: str
    reason: str


class SyncHealthRecoveryOut(BaseModel):
    available: bool
    admin_only: bool


class SyncHealthOut(BaseModel):
    state: str = Field(pattern="^(fresh|stale|failed)$")
    last_success_at: str | None
    last_attempt_at: str | None
    last_status: str = Field(pattern="^(ok|partial|failed)$")
    schedule: str
    deals_seen: int | None = None
    deals_written: int | None = None
    error_count: int | None = None
    errors: list[SyncHealthErrorOut] = Field(default_factory=list, max_length=5)
    recovery: SyncHealthRecoveryOut | None = None


@sync_health_router.get("/sync-health", response_model=SyncHealthOut,
                        response_model_exclude_unset=True)
async def get_sync_health(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SyncHealthOut:
    _require_reader(user)
    from app.services.hubspot_sync_runs import compute_sync_health

    return SyncHealthOut(**await compute_sync_health(session))


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
