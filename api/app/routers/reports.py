"""S20 reports router — approval turnaround + portfolio basis.

Owner: W4. Thin router: role gate, parse the window, delegate to
:mod:`app.services.reports`, marshal a response envelope compatible with
the docs/reports/s20/contracts.md §3 shape.

Endpoints:

* ``GET /reports/approvals/turnaround`` — L18/T42 approval turnaround.
* ``GET /reports/portfolio/basis``      — L17 portfolio population/basis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.opportunity import Opportunity
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
