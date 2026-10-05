"""S20 reports router — approval turnaround + portfolio basis.

Owner: W4. Thin router: role gate, parse the window, delegate to
:mod:`app.services.reports`, marshal a response envelope compatible with
the docs/reports/s20/contracts.md §3 shape.

Endpoints:

* ``GET /reports/approvals/turnaround`` — L18/T42 approval turnaround.
* ``GET /reports/portfolio/basis``      — L17 portfolio population/basis.
* ``GET /reports/pipeline/by-stage``    — W4 item 3: aggregate open opportunities
  by HubSpot stage label. Totals computed over the full filter set before
  the response is paginated.
* ``GET /reports/pipeline/by-owner``    — W4 item 3: aggregate by deal owner.
* ``GET /reports/pipeline/by-bu``       — W4 item 3: BU aggregation. Honestly
  returns ``bu_mirrored=false`` because the staging HubSpot portal has
  no Business Unit property on deals (W1-D10).
* ``GET /reports/sow/gm``               — W4 item 3: SOW GM table per
  component (US / India / Blended) with floor pass/fail markers.
* ``GET /reports/approvals/aging``      — W4 item 3: approvals aging buckets
  (<=24h, 1-3d, 3-7d, >7d) across every pending package.
* ``GET /reports/pipeline/export.csv``  — W4 item 3: CSV export of the
  current filter set. All rows (no pagination). Totals row at the top
  computed BEFORE the row stream.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.gm.policy import INDIA_FLOOR, US_FLOOR
from app.models.approval import ApprovalPackage
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.services.hubspot_pipeline import (
    PipelineFilters,
    list_opportunities,
    summary as pipeline_summary,
)
from app.services.reports import (
    TurnaroundReport,
    compute_approval_turnaround,
)


router = APIRouter(prefix="/reports", tags=["reports"])


# ---- role gate ---------------------------------------------------------

_READ_ROLES: frozenset[str] = frozenset(
    {
        "CEO",
        "Finance",
        "Delivery",
        "Legal",
        "HR",
        "Sales",
        "SalesLeader",
        "SystemAdmin",
    }
)


def _require_reader(user: AuthUser) -> None:
    if not any(g in _READ_ROLES for g in user.groups):
        raise HTTPException(status_code=403, detail="insufficient role")


# ---- schemas -----------------------------------------------------------


class StageTurnaroundOut(BaseModel):
    stage: str = Field(
        description=(
            "Approval-package status the interval was measured from "
            "(e.g. 'pending_delivery_hr'). See "
            "app/services/reports.STAGE_ORDER."
        )
    )
    sample_size: int = Field(
        description=(
            "Number of transitions that contributed. 0 → other fields "
            "are null; the UI renders 'Unknown' rather than a fake zero."
        )
    )
    avg_hours: float | None = None
    median_hours: float | None = None
    p90_hours: float | None = None


class TurnaroundResponse(BaseModel):
    window: str
    window_from: datetime
    window_to: datetime
    total_transitions: int
    per_stage: list[StageTurnaroundOut]
    overall_median_hours: float | None
    generated_at: datetime
    # A stripped copy of the §3 envelope's `meta` — the fields that
    # actually mean something for this endpoint.
    meta: dict[str, Any]


class PortfolioBasisResponse(BaseModel):
    population: dict[str, Any] = Field(
        description=(
            "Explicit population accounting. `included` + `excluded` + "
            "`reasons` per L17. Every count is a global total."
        )
    )
    basis: dict[str, Any] = Field(
        description=(
            "The report's as-of date + source watermark. UI shows this "
            "under the header so a screenshot is self-describing."
        )
    )


# ---- endpoints ---------------------------------------------------------


def _to_out(report: TurnaroundReport) -> TurnaroundResponse:
    return TurnaroundResponse(
        window=report.window,
        window_from=report.window_from,
        window_to=report.window_to,
        total_transitions=report.total_transitions,
        per_stage=[
            StageTurnaroundOut(
                stage=s.stage,
                sample_size=s.sample_size,
                avg_hours=s.avg_hours,
                median_hours=s.median_hours,
                p90_hours=s.p90_hours,
            )
            for s in report.per_stage
        ],
        overall_median_hours=report.overall_median_hours,
        generated_at=report.generated_at,
        meta={
            "freshness": {
                "source": "audit_event",
                "processed_at": report.generated_at.isoformat(),
                "state": "verified working"
                if report.total_transitions > 0
                else "Unknown",
            },
            "filters_echo": {"window": report.window},
        },
    )


@router.get("/approvals/turnaround", response_model=TurnaroundResponse)
async def approvals_turnaround_endpoint(
    window: str = Query(
        "30d",
        description=(
            "Rolling window token: '<n>d', '<n>w' or '<n>h'. Default 30d."
        ),
        max_length=8,
    ),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> TurnaroundResponse:
    """L18/T42 · approval turnaround aggregates.

    Returns per-stage average / median / p90 hours plus a total-transitions
    counter. A window with no transitions returns `sample_size=0` and
    null metrics — never a synthetic zero.
    """

    _require_reader(user)
    try:
        report = await compute_approval_turnaround(session, window=window)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_out(report)


@router.get("/portfolio/basis", response_model=PortfolioBasisResponse)
async def portfolio_basis_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PortfolioBasisResponse:
    """L17 · Portfolio report population + basis.

    The Portfolio report (`/reports`, first tab) needs the same base
    query as Pipeline (contracts.md §4 aggregate contract). Instead of
    duplicating that in a second service, we return the *population*
    of the report — how many opportunities the current mirror has open
    vs closed vs archived — and the *basis* (as-of timestamp and last
    reconcile). The UI puts this in the report header so a screenshot
    is self-describing.
    """

    _require_reader(user)

    # Count opportunities across three population buckets:
    #   included: source='hubspot' AND archived_at IS NULL
    #   excluded_archived: source='hubspot' AND archived_at IS NOT NULL
    #   excluded_non_hubspot: source != 'hubspot' (SOW-first, imported, etc.)
    # Reasons list mirrors the counts so the UI can label them.
    async def _count(where) -> int:
        stmt = select(func.count(Opportunity.id)).where(where)
        return int((await session.execute(stmt)).scalar_one())

    included = await _count(
        (Opportunity.source == "hubspot")
        & (Opportunity.archived_at.is_(None))
    )
    excluded_archived = await _count(
        (Opportunity.source == "hubspot")
        & (Opportunity.archived_at.is_not(None))
    )
    excluded_non_hubspot = await _count(
        Opportunity.source != "hubspot"
    )

    # Basis — pull hubspot_reconcile / hubspot_backfill sync_status
    # rows. We import lazily to avoid a circular dependency with the
    # sync_status service.
    from app.models.sync_status import SyncStatus

    ss_rows = list(
        (
            await session.execute(
                select(SyncStatus).where(
                    SyncStatus.source.in_(
                        (
                            "hubspot_reconcile",
                            "hubspot_backfill",
                            "hubspot_webhook",
                        )
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    basis_watermarks: dict[str, Any] = {}
    for row in ss_rows:
        basis_watermarks[row.source] = {
            "last_success_at": (
                row.last_success_at.isoformat() if row.last_success_at else None
            ),
            "last_error": row.last_error,
            "lag_seconds": row.lag_seconds,
        }

    generated_at = datetime.now(tz=UTC)
    return PortfolioBasisResponse(
        population={
            "included": included,
            "excluded_archived": excluded_archived,
            "excluded_non_hubspot": excluded_non_hubspot,
            "reasons": {
                "included": "source=hubspot AND archived_at IS NULL",
                "excluded_archived": "source=hubspot AND archived_at IS NOT NULL",
                "excluded_non_hubspot": "source != 'hubspot' (SOW-first / imported)",
            },
        },
        basis={
            "as_of": generated_at.isoformat(),
            "watermarks": basis_watermarks,
        },
    )


# ---- W4 Session 6 · pipeline aggregates for Reports --------------------
#
# All three /reports/pipeline/by-* endpoints call
# `hubspot_pipeline.list_opportunities` with page_size=1000 so the full
# authorized filter set is materialised; aggregation happens in Python
# over the row set (not a separate SQL — guarantees the Reports number
# comes from the same base filter as the Pipeline page). Totals are
# computed BEFORE pagination because `list_opportunities` returns
# `total` as the window count prior to LIMIT (A5/T35 contract).
# -----------------------------------------------------------------------


_ID_RX = re.compile(r"^\d{10,12}$")


def _is_raw_id(label: str | None) -> bool:
    """Honest-value test: a raw HubSpot id in a label field is a defect."""
    return bool(label and _ID_RX.match(label))


class StageAggregateRow(BaseModel):
    stage_label: str
    stage_id: str | None
    count: int
    open_value_usd: str  # Decimal rendered as string


class ByStageResponse(BaseModel):
    total_count: int
    total_open_value_usd: str
    rows: list[StageAggregateRow]
    generated_at: datetime


@router.get("/pipeline/by-stage", response_model=ByStageResponse)
async def pipeline_by_stage(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ByStageResponse:
    """W4 item 3 · open-opportunity rollup by HubSpot stage.

    Routes through `hubspot_pipeline.list_opportunities` so the Reports
    row count for stage X reconciles with `/pipeline?stage=X`.
    """

    _require_reader(user)
    # page_size=1000 captures the full staging deal set in one call. If
    # this ever paginates (>1k open deals) the number is still honest:
    # we aggregate from `stage_counts` which is computed over the full
    # filter set, not the page window.
    page = await list_opportunities(
        session,
        filters=PipelineFilters(open_closed="open"),
        page=1,
        page_size=1000,
    )

    # The chip stage_counts give the authoritative per-stage counts.
    # Compute value totals from the materialised row set (first 1000).
    value_by_stage: dict[str | None, Decimal] = defaultdict(lambda: Decimal(0))
    for row in page.items:
        if row.currency not in (None, "USD"):
            continue  # USD column only; mixed-currency rendering is per chip.
        if row.amount is not None:
            value_by_stage[row.stage_id] += Decimal(row.amount)

    rows_out: list[StageAggregateRow] = []
    total_count = 0
    total_value = Decimal(0)
    for sc in page.stage_counts:
        # Skip raw-id stage labels (defensive — W1-D9 reconciles labels).
        label = sc.stage_label or "Unknown"
        if _is_raw_id(sc.stage_label):
            label = sc.stage_id or "Unknown"
        value = value_by_stage.get(sc.stage_id, Decimal(0))
        rows_out.append(
            StageAggregateRow(
                stage_label=label,
                stage_id=sc.stage_id,
                count=sc.count,
                open_value_usd=format(value, "f"),
            )
        )
        total_count += sc.count
        total_value += value
    # Preserve HubSpot ordering (stage_order ascending if present).
    rows_out.sort(key=lambda r: (r.stage_id or ""))

    return ByStageResponse(
        total_count=total_count,
        total_open_value_usd=format(total_value, "f"),
        rows=rows_out,
        generated_at=datetime.now(tz=UTC),
    )


class OwnerAggregateRow(BaseModel):
    owner_name: str
    owner_email: str | None
    count: int
    open_value_usd: str


class ByOwnerResponse(BaseModel):
    total_count: int
    total_open_value_usd: str
    rows: list[OwnerAggregateRow]
    generated_at: datetime


@router.get("/pipeline/by-owner", response_model=ByOwnerResponse)
async def pipeline_by_owner(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ByOwnerResponse:
    """W4 item 3 · open-opportunity rollup by deal owner.

    Owner here is `opportunity.owner_id` (D2 deal owner), not the client
    account owner. A deal with no owner contributes to "Unassigned".
    """

    _require_reader(user)
    page = await list_opportunities(
        session,
        filters=PipelineFilters(open_closed="open"),
        page=1,
        page_size=1000,
    )

    agg: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in page.items:
        name = row.owner_name or "Unassigned"
        key = (name, row.owner_email)
        slot = agg.setdefault(
            key, {"count": 0, "value": Decimal(0), "email": row.owner_email}
        )
        slot["count"] += 1
        if row.amount is not None and (row.currency in (None, "USD")):
            slot["value"] += Decimal(row.amount)

    rows_out = [
        OwnerAggregateRow(
            owner_name=name,
            owner_email=slot["email"],
            count=slot["count"],
            open_value_usd=format(slot["value"], "f"),
        )
        for (name, _email), slot in agg.items()
    ]
    rows_out.sort(key=lambda r: (-r.count, r.owner_name))
    total_value = sum((Decimal(r.open_value_usd) for r in rows_out), Decimal(0))

    return ByOwnerResponse(
        total_count=sum(r.count for r in rows_out),
        total_open_value_usd=format(total_value, "f"),
        rows=rows_out,
        generated_at=datetime.now(tz=UTC),
    )


class BuAggregateRow(BaseModel):
    business_unit: str
    count: int
    open_value_usd: str


class ByBuResponse(BaseModel):
    bu_mirrored: bool
    note: str
    total_count: int
    total_open_value_usd: str
    rows: list[BuAggregateRow]
    generated_at: datetime


@router.get("/pipeline/by-bu", response_model=ByBuResponse)
async def pipeline_by_bu(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ByBuResponse:
    """W4 item 3 · open-opportunity rollup by Business Unit.

    Per W1-D10, the staging HubSpot portal exposes no BU property on
    the deal schema, so for the staging environment this endpoint
    returns `bu_mirrored=false` with every opportunity bucketed into
    "Not mirrored" — never a synthetic zero or a fake split.
    """

    _require_reader(user)
    page = await list_opportunities(
        session,
        filters=PipelineFilters(open_closed="open"),
        page=1,
        page_size=1000,
    )

    bu_counts: dict[str, dict[str, Any]] = {}
    any_bu_seen = False
    for row in page.items:
        bu = row.business_unit or "Not mirrored"
        if row.business_unit:
            any_bu_seen = True
        slot = bu_counts.setdefault(bu, {"count": 0, "value": Decimal(0)})
        slot["count"] += 1
        if row.amount is not None and (row.currency in (None, "USD")):
            slot["value"] += Decimal(row.amount)

    rows_out = [
        BuAggregateRow(
            business_unit=bu,
            count=slot["count"],
            open_value_usd=format(slot["value"], "f"),
        )
        for bu, slot in bu_counts.items()
    ]
    rows_out.sort(key=lambda r: (-r.count, r.business_unit))

    note = (
        "HubSpot staging portal has no Business Unit property on deals "
        "(W1-D10). Every deal is bucketed into 'Not mirrored' until a BU "
        "property is defined upstream and backfilled."
    )
    total_value = sum((Decimal(r.open_value_usd) for r in rows_out), Decimal(0))

    return ByBuResponse(
        bu_mirrored=any_bu_seen,
        note=note,
        total_count=sum(r.count for r in rows_out),
        total_open_value_usd=format(total_value, "f"),
        rows=rows_out,
        generated_at=datetime.now(tz=UTC),
    )


# ---- SOW GM table ------------------------------------------------------


class SowGmRow(BaseModel):
    opportunity_id: str
    hubspot_deal_id: str | None
    deal_name: str | None
    client_name: str | None
    component: str  # 'US' | 'India' | 'Blended'
    revenue: str
    gm_pct: str | None  # None when revenue is zero (undefined)
    floor_pct: str
    floor_pass: bool | None  # None when gm_pct is undefined


class SowGmResponse(BaseModel):
    us_floor_pct: str
    india_floor_pct: str
    rows: list[SowGmRow]
    generated_at: datetime
    note: str


@router.get("/sow/gm", response_model=SowGmResponse)
async def sow_gm_report(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SowGmResponse:
    """W4 item 3 · SOW GM table per component with floor pass/fail.

    Picks the newest GmModel per opportunity (same selector as the CEO
    dashboard) and splits revenue + cost into US / India / Blended rows.
    Each row carries the applicable floor and a pass/fail flag.
    """

    _require_reader(user)

    # Pull the latest GM model per opportunity. We import the dashboard
    # helpers lazily to avoid a circular import at module load.
    from app.services.dashboards import (
        _load_latest_gm_for_opps,
        _model_totals,
    )
    from app.services.hubspot_pipeline import list_opportunity_rows

    # Route through the single-truth list helper (C8/F3) — same
    # hubspot-sourced + non-archived scope every other list surface uses.
    opp_rows = await list_opportunity_rows(session)
    opp_by_id = {o.id: o for o in opp_rows}
    latest = await _load_latest_gm_for_opps(session, [o.id for o in opp_rows])

    rows: list[SowGmRow] = []
    for opp_id, model in latest.items():
        totals = _model_totals(model)
        rev_us = Decimal(totals["revenue_us"] or 0)
        rev_in = Decimal(totals["revenue_india"] or 0)
        cost_us = Decimal(totals["cost_us"] or 0)
        cost_in = Decimal(totals["cost_india"] or 0)

        def _row(
            component: str, rev: Decimal, cost: Decimal, floor: Decimal
        ) -> SowGmRow:
            gm = None
            if rev > 0:
                gm = (rev - cost) / rev
            opp = opp_by_id.get(opp_id)
            return SowGmRow(
                opportunity_id=str(opp_id),
                hubspot_deal_id=opp.hubspot_deal_id if opp else None,
                deal_name=opp.name if opp else None,
                client_name=None,
                component=component,
                revenue=format(rev, "f"),
                gm_pct=format(gm, "f") if gm is not None else None,
                floor_pct=format(floor, "f"),
                floor_pass=(gm >= floor) if gm is not None else None,
            )

        if rev_us > 0:
            rows.append(_row("US", rev_us, cost_us, US_FLOOR))
        if rev_in > 0:
            rows.append(_row("India", rev_in, cost_in, INDIA_FLOOR))
        total_rev = rev_us + rev_in
        total_cost = cost_us + cost_in
        # Blended floor: weighted by revenue share; fallback US_FLOOR
        # when revenue is pure-US and INDIA_FLOOR when pure-India.
        if total_rev > 0:
            weighted = (rev_us * US_FLOOR + rev_in * INDIA_FLOOR) / total_rev
            rows.append(_row("Blended", total_rev, total_cost, weighted))

    rows.sort(key=lambda r: (r.deal_name or "", r.component))

    return SowGmResponse(
        us_floor_pct=format(US_FLOOR, "f"),
        india_floor_pct=format(INDIA_FLOOR, "f"),
        rows=rows,
        generated_at=datetime.now(tz=UTC),
        note=(
            "Blended floor is revenue-weighted across the US + India "
            "components. Rows with zero revenue in a component are "
            "omitted (undefined GM — never a synthetic zero)."
        ),
    )


# ---- Approvals aging ---------------------------------------------------


class AgingBucket(BaseModel):
    label: str  # "<= 24h", "1-3d", "3-7d", "> 7d"
    count: int


class AgingLane(BaseModel):
    status: str
    total: int
    buckets: list[AgingBucket]


class ApprovalsAgingResponse(BaseModel):
    as_of: datetime
    lanes: list[AgingLane]


@router.get("/approvals/aging", response_model=ApprovalsAgingResponse)
async def approvals_aging(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ApprovalsAgingResponse:
    """W4 item 3 · pending-approval aging buckets.

    Buckets packages by (now - submitted_at) across the three pending
    lanes (`pending_delivery_hr`, `pending_finance_legal`,
    `pending_ceo_exception`). Used by the Reports Aging tab.
    """

    _require_reader(user)
    now = datetime.now(tz=UTC)
    lanes_status = (
        "pending_delivery_hr",
        "pending_finance_legal",
        "pending_ceo_exception",
    )
    rows = list(
        (
            await session.execute(
                select(ApprovalPackage).where(ApprovalPackage.status.in_(lanes_status))
            )
        )
        .scalars()
        .all()
    )
    out: list[AgingLane] = []
    for status in lanes_status:
        lane_rows = [r for r in rows if r.status == status]
        buckets = {"<= 24h": 0, "1-3d": 0, "3-7d": 0, "> 7d": 0}
        for r in lane_rows:
            if r.submitted_at is None:
                buckets["<= 24h"] += 1
                continue
            age_days = (now - r.submitted_at).total_seconds() / 86400.0
            if age_days <= 1:
                buckets["<= 24h"] += 1
            elif age_days <= 3:
                buckets["1-3d"] += 1
            elif age_days <= 7:
                buckets["3-7d"] += 1
            else:
                buckets["> 7d"] += 1
        out.append(
            AgingLane(
                status=status,
                total=len(lane_rows),
                buckets=[AgingBucket(label=k, count=v) for k, v in buckets.items()],
            )
        )
    return ApprovalsAgingResponse(as_of=now, lanes=out)


# ---- CSV export --------------------------------------------------------


@router.get("/pipeline/export.csv")
async def pipeline_export_csv(
    request: Request,
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
    sort: str | None = Query(None),
) -> StreamingResponse:
    """W4 item 3 · CSV export of the current open-pipeline filter set.

    Totals row ships at the top of the stream, computed BEFORE any
    pagination. Columns: deal, client, owner, stage, amount, currency,
    close_date, SOW state, attention.
    """

    _require_reader(user)

    from dataclasses import replace
    from app.routers.pipeline import _parse_filters, _parse_sort, _resolve_scope
    from app.services.hubspot_pipeline import DEFAULT_SORT_OPPS, scope_pipeline_filters

    supported = {"pipeline", "stage", "owner", "account_owner", "business_unit", "readiness", "attention",
        "date_field", "date_from", "date_to", "date_preset", "search", "include_closed", "open_closed",
        "missing", "client", "group", "watching", "sort"}
    if set(request.query_params) - supported:
        raise HTTPException(400, "Unsupported Pipeline export query parameters")
    # No earlier scope/summary/page query may establish a READ COMMITTED snapshot.
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        if session.in_transaction():
            raise HTTPException(409, "Pipeline export requires a fresh snapshot transaction")
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        await session.execute(text("SET TRANSACTION READ ONLY"))
    elif dialect == "sqlite" and not session.in_transaction():
        await session.execute(text("BEGIN"))
    snapshot_time = datetime.now(UTC)
    scope = await _resolve_scope(session, user=user, group_ids=group, watching=watching)
    filters = _parse_filters(pipeline, stage, owner, readiness, attention, date_field, date_from,
        date_to, date_preset, search, include_closed, account_owner=account_owner,
        business_unit=business_unit, open_closed=open_closed, missing=missing,
        client=tuple((client or []) + list(scope["client"] or ())) or None,
        watching_ids=scope["watching_ids"])
    if scope["opportunity_id"] is not None:
        filters = replace(filters, opportunity_id=scope["opportunity_id"])
    filters = await scope_pipeline_filters(session, user, filters)
    sort_spec = _parse_sort(sort, DEFAULT_SORT_OPPS)
    pre_summary = await pipeline_summary(session, filters=filters, now=snapshot_time)
    rows, page_number = [], 1
    while True:
        page = await list_opportunities(session, filters=filters, page=page_number, page_size=1000,
            sort=sort_spec, now=snapshot_time)
        rows.extend(page.items)
        if len(rows) >= page.total or not page.items:
            break
        page_number += 1

    def _iter_csv():
        buf = io.StringIO()
        w = csv.writer(buf)
        # Header + totals row FIRST.
        w.writerow(
            [
                "deal",
                "client",
                "owner",
                "stage",
                "amount",
                "currency",
                "close_date",
                "sow_state",
                "attention",
                "source_origin",
            ]
        )
        totals_label = (
            f"TOTAL: {pre_summary.open_count} matching · "
            + ", ".join(
                f"{v} {k}" for k, v in pre_summary.open_value_by_currency.items()
            )
        )
        w.writerow([totals_label, "", "", "", "", "", "", "", "", ""])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        for row in rows:
            w.writerow(
                [
                    row.name or row.hubspot_deal_id or "",
                    row.client_name or "",
                    row.owner_name or "Unassigned",
                    row.stage_label or "Unknown",
                    format(row.amount, "f") if row.amount is not None else "",
                    row.currency or "",
                    row.close_date.isoformat() if row.close_date else "",
                    row.sow_approval_state,
                    "|".join(row.attention_flags),
                    row.source_origin,
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    return StreamingResponse(
        _iter_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=pipeline.csv",
            "X-Totals-Count": str(pre_summary.open_count),
        },
    )
