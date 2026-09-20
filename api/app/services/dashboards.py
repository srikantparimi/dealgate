"""Role dashboards + Client SOW GM aggregation — S5 E10.

Every dashboard here is a read-only aggregate over the existing tables. No
math lives in the browser (CLAUDE.md rule 2, blueprint §2) — the client only
renders whatever this module returns. Every money value is a ``Decimal`` and
serialises as a string so precision survives the trip through JSON.

The aggregations lean on the ratified GM engine (:mod:`app.gm`) so the
numbers on a dashboard cannot drift from what the Delivery Model Builder or
the approval floor check computed for the same package. Where data is not
yet populated (Sprint 6 tables — ``forecast_period`` / ``actual_period``)
the response degrades gracefully: empty list + a ``note`` string that the
UI renders as a small footnote.

Only reads: no writes, no state changes. Role gating lives in the router
(:mod:`app.routers.dashboards`) — this module trusts that its caller has
already been vetted for the requested view.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import AuthUser
from app.gm.policy import INDIA_FLOOR, US_FLOOR
from app.models.adviser_estimate import AdviserEstimate
from app.models.approval import ApprovalPackage
from app.models.ceo_exception import CeoException
from app.models.client import Agreement, Client, LegalEntity
from app.models.gm_model import GmModel, ResourceLine
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.task import Task
from app.services.clients import coverage_state as _coverage_state

_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _fmt(value: Optional[Decimal]) -> Optional[str]:
    """Serialise a Decimal without losing precision. ``None`` stays ``None``."""

    if value is None:
        return None
    return format(value, "f")


def _line_cost_us(line: ResourceLine) -> Decimal:
    """US cost of a resource line — Decimal, unrounded.

    Missing ``hourly_cost`` is treated as zero for the aggregation but the
    parent ``gm_model.complete=False`` flag is what the "missing cost inputs"
    finance widget keys off — never silently ``0`` a whole margin story.
    """

    if line.location != "US":
        return _ZERO
    cost = line.hourly_cost or _ZERO
    return line.billable_hours * cost * (line.allocation_pct or _ZERO)


def _line_cost_india(line: ResourceLine) -> Decimal:
    if line.location != "India":
        return _ZERO
    cost = line.hourly_cost or _ZERO
    return line.billable_hours * cost * (line.allocation_pct or _ZERO)


def _model_totals(model: GmModel) -> dict[str, Decimal]:
    """Return ``{revenue_us, revenue_india, cost_us, cost_india, complete}``.

    Uses the snapshot revenue columns on ``gm_model`` and re-sums cost from
    the resource lines. Cost lines aren't split US/India in the aggregate;
    they're added to the US side to match the GM library's staff_aug default
    (build-guide §7). Any refinement stays in ``app.gm``.
    """

    revenue_us = model.revenue_us or _ZERO
    revenue_india = model.revenue_india or _ZERO
    cost_us = _ZERO
    cost_india = _ZERO
    complete = True
    for r in model.resource_lines:
        if r.hourly_cost is None:
            complete = False
        cost_us += _line_cost_us(r)
        cost_india += _line_cost_india(r)
    for c in model.cost_lines:
        if c.location == "India":
            cost_india += c.amount or _ZERO
        else:
            cost_us += c.amount or _ZERO
    return {
        "revenue_us": revenue_us,
        "revenue_india": revenue_india,
        "cost_us": cost_us,
        "cost_india": cost_india,
        "complete": complete,
    }


def _model_gm(model: GmModel) -> Optional[Decimal]:
    """Blended GM for a persisted model, using client-GM aggregation math.

    (US_GP + India_GP) / (US_Rev + India_Rev). ``None`` when revenue is zero
    (undefined GM — same convention as :class:`~app.gm.TemplateResult`).
    """

    totals = _model_totals(model)
    revenue = totals["revenue_us"] + totals["revenue_india"]
    if revenue <= 0:
        return None
    profit = (totals["revenue_us"] - totals["cost_us"]) + (
        totals["revenue_india"] - totals["cost_india"]
    )
    return profit / revenue


async def _load_latest_gm_for_opps(
    session: AsyncSession, opportunity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, GmModel]:
    """Return ``{opportunity_id: newest GmModel}`` with lines eagerly loaded."""

    if not opportunity_ids:
        return {}
    stmt = (
        select(GmModel)
        .options(
            selectinload(GmModel.resource_lines),
            selectinload(GmModel.cost_lines),
        )
        .where(GmModel.opportunity_id.in_(opportunity_ids))
        .order_by(GmModel.opportunity_id, GmModel.created_at.desc(), GmModel.id.desc())
    )
    rows = list((await session.execute(stmt)).scalars())
    out: dict[uuid.UUID, GmModel] = {}
    for m in rows:
        if m.opportunity_id is not None and m.opportunity_id not in out:
            out[m.opportunity_id] = m
    return out


async def _load_released_package_for_opps(
    session: AsyncSession, opportunity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ApprovalPackage]:
    """Return ``{opportunity_id: newest ready_to_sign ApprovalPackage}``."""

    if not opportunity_ids:
        return {}
    stmt = (
        select(ApprovalPackage)
        .where(ApprovalPackage.opportunity_id.in_(opportunity_ids))
        .where(ApprovalPackage.status == "ready_to_sign")
        .order_by(
            ApprovalPackage.opportunity_id,
            ApprovalPackage.released_at.desc(),
            ApprovalPackage.id.desc(),
        )
    )
    rows = list((await session.execute(stmt)).scalars())
    out: dict[uuid.UUID, ApprovalPackage] = {}
    for p in rows:
        if p.opportunity_id not in out:
            out[p.opportunity_id] = p
    return out


# ---------------------------------------------------------------------------
# CEO view
# ---------------------------------------------------------------------------


# Statuses that count towards "pipeline". Everything up to (and including)
# a released package that hasn't been countersigned is still pipeline —
# only rows past ``signed`` should drop off, but we don't have that column
# yet so we use the negative list.
_PIPELINE_STATUS_EXCLUDES = frozenset({"Closed-Won", "Closed-Lost", "Signed"})


async def ceo_view(session: AsyncSession) -> dict[str, Any]:
    """CEO dashboard aggregate.

    Widgets (blueprint §9):

    * ``pipeline_value`` — sum of revenue on every non-closed opportunity's
      latest gm_model.
    * ``approved_vs_forecast_gp`` — the aggregate gross profit implied by
      released packages, compared to what the newest ``gm_model`` forecasts.
    * ``below_floor_deals`` — opportunities whose latest gm_model falls
      under the US or India floor.
    * ``ceo_exceptions_pending`` — undecided ``ceo_exception`` rows.
    * ``revenue_expiring_in_90_days`` — placeholder (Sprint 6 renewals).
    * ``aged_blockers_by_owner`` — tasks past due, grouped by owner.
    """

    opps = list(
        (
            await session.execute(
                select(Opportunity).order_by(Opportunity.created_at.asc())
            )
        ).scalars()
    )
    active_opps = [o for o in opps if o.governance_status not in _PIPELINE_STATUS_EXCLUDES]
    latest_by_opp = await _load_latest_gm_for_opps(session, [o.id for o in active_opps])
    released_by_opp = await _load_released_package_for_opps(
        session, [o.id for o in active_opps]
    )

    pipeline_value = _ZERO
    forecast_gp = _ZERO
    approved_gp = _ZERO
    below_floor: list[dict[str, Any]] = []
    for opp in active_opps:
        model = latest_by_opp.get(opp.id)
        if model is None:
            continue
        totals = _model_totals(model)
        rev = totals["revenue_us"] + totals["revenue_india"]
        pipeline_value += rev
        gp = (totals["revenue_us"] - totals["cost_us"]) + (
            totals["revenue_india"] - totals["cost_india"]
        )
        forecast_gp += gp
        released = released_by_opp.get(opp.id)
        if released is not None:
            approved_gp += gp
        # Floor check per component.
        gm_us = None
        if totals["revenue_us"] > 0:
            gm_us = (totals["revenue_us"] - totals["cost_us"]) / totals["revenue_us"]
        gm_india = None
        if totals["revenue_india"] > 0:
            gm_india = (
                totals["revenue_india"] - totals["cost_india"]
            ) / totals["revenue_india"]
        below = (gm_us is not None and gm_us < US_FLOOR) or (
            gm_india is not None and gm_india < INDIA_FLOOR
        )
        if below:
            below_floor.append(
                {
                    "opportunity_id": str(opp.id),
                    "hubspot_deal_id": opp.hubspot_deal_id,
                    "governance_status": opp.governance_status,
                    "revenue": _fmt(rev),
                    "gm_us": _fmt(gm_us),
                    "gm_india": _fmt(gm_india),
                }
            )

    # CEO exceptions still awaiting a decision.
    ceo_pending_rows = list(
        (
            await session.execute(
                select(CeoException)
                .where(CeoException.decision.is_(None))
                .order_by(CeoException.drafted_at.asc())
            )
        ).scalars()
    )
    ceo_pending = [
        {
            "id": str(row.id),
            "package_id": str(row.package_id),
            "drafted_at": row.drafted_at.isoformat() if row.drafted_at else None,
            "has_rationale": row.rationale_text is not None,
        }
        for row in ceo_pending_rows
    ]

    # Aged blockers = incomplete tasks with a due_date in the past.
    today = date.today()
    blocker_rows = list(
        (
            await session.execute(
                select(Task)
                .where(Task.status.notin_(("done", "cancelled")))
                .where(Task.due_date.is_not(None))
                .where(Task.due_date < today)
            )
        ).scalars()
    )
    aged_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in blocker_rows:
        owner_key = str(t.owner_id) if t.owner_id else "unassigned"
        aged_by_owner[owner_key].append(
            {
                "task_id": str(t.id),
                "subject": t.subject,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "escalation_level": t.escalation_level,
                "category": t.category,
            }
        )

    return {
        "pipeline_value": _fmt(pipeline_value),
        "approved_vs_forecast_gp": {
            "approved_gp": _fmt(approved_gp),
            "forecast_gp": _fmt(forecast_gp),
        },
        "below_floor_deals": below_floor,
        "ceo_exceptions_pending": ceo_pending,
        "revenue_expiring_in_90_days": [],
        "aged_blockers_by_owner": dict(aged_by_owner),
        "notes": {
            "revenue_expiring_in_90_days": (
                "Renewal periods land in Sprint 6; degrading to empty list."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Finance view
# ---------------------------------------------------------------------------


async def finance_view(session: AsyncSession) -> dict[str, Any]:
    """Finance dashboard aggregate.

    * ``gm_by_sow`` — one row per opportunity's latest gm_model with US /
      India / blended GM and completeness flag.
    * ``gm_by_geography`` — total US and India revenue / cost / GM.
    * ``approved_vs_forecast_vs_actual`` — actuals stay ``None`` until the
      Sprint 6 ``actual_period`` table lands.
    * ``missing_cost_inputs`` — gm_models flagged incomplete (any resource
      line without a validated ``hourly_cost``).
    * ``exceptions_and_exposure`` — pending CEO exceptions + the gross
      profit shortfall implied by their pinned gm_model.
    """

    opps = list(
        (
            await session.execute(
                select(Opportunity).order_by(Opportunity.created_at.asc())
            )
        ).scalars()
    )
    latest_by_opp = await _load_latest_gm_for_opps(session, [o.id for o in opps])
    released_by_opp = await _load_released_package_for_opps(
        session, [o.id for o in opps]
    )

    gm_by_sow: list[dict[str, Any]] = []
    total_rev_us = _ZERO
    total_rev_india = _ZERO
    total_cost_us = _ZERO
    total_cost_india = _ZERO
    forecast_gp = _ZERO
    approved_gp = _ZERO
    missing_cost_inputs: list[dict[str, Any]] = []
    for opp in opps:
        model = latest_by_opp.get(opp.id)
        if model is None:
            continue
        totals = _model_totals(model)
        rev = totals["revenue_us"] + totals["revenue_india"]
        cost = totals["cost_us"] + totals["cost_india"]
        gm_us = (
            (totals["revenue_us"] - totals["cost_us"]) / totals["revenue_us"]
            if totals["revenue_us"] > 0
            else None
        )
        gm_india = (
            (totals["revenue_india"] - totals["cost_india"]) / totals["revenue_india"]
            if totals["revenue_india"] > 0
            else None
        )
        gm_blended = _model_gm(model)
        released = released_by_opp.get(opp.id)
        gp = (totals["revenue_us"] - totals["cost_us"]) + (
            totals["revenue_india"] - totals["cost_india"]
        )
        forecast_gp += gp
        if released is not None:
            approved_gp += gp
        gm_by_sow.append(
            {
                "opportunity_id": str(opp.id),
                "hubspot_deal_id": opp.hubspot_deal_id,
                "gm_model_id": str(model.id),
                "engagement_type": model.engagement_type,
                "revenue": _fmt(rev),
                "cost": _fmt(cost),
                "gm_us": _fmt(gm_us),
                "gm_india": _fmt(gm_india),
                "gm_blended": _fmt(gm_blended),
                "complete": totals["complete"],
                "approved": released is not None,
            }
        )
        total_rev_us += totals["revenue_us"]
        total_rev_india += totals["revenue_india"]
        total_cost_us += totals["cost_us"]
        total_cost_india += totals["cost_india"]
        if not totals["complete"]:
            missing_cost_inputs.append(
                {
                    "opportunity_id": str(opp.id),
                    "hubspot_deal_id": opp.hubspot_deal_id,
                    "gm_model_id": str(model.id),
                }
            )

    def _geo_slice(rev: Decimal, cost: Decimal) -> dict[str, Any]:
        gm = (rev - cost) / rev if rev > 0 else None
        return {
            "revenue": _fmt(rev),
            "cost": _fmt(cost),
            "gm": _fmt(gm),
        }

    exceptions = list(
        (
            await session.execute(
                select(CeoException)
                .options()
                .where(CeoException.decision.is_(None))
            )
        ).scalars()
    )
    exposure: list[dict[str, Any]] = []
    for exc in exceptions:
        # Best-effort: look up the pinned package + gm_model.
        pkg = await session.get(ApprovalPackage, exc.package_id)
        gp_shortfall = None
        if pkg is not None:
            model = await session.get(GmModel, pkg.gm_model_id)
            if model is not None:
                # Reload with lines so cost aggregation is honest.
                model = (
                    await session.execute(
                        select(GmModel)
                        .options(
                            selectinload(GmModel.resource_lines),
                            selectinload(GmModel.cost_lines),
                        )
                        .where(GmModel.id == model.id)
                    )
                ).scalar_one()
                totals = _model_totals(model)
                # Shortfall vs the higher of the two floors, applied to the
                # matching component. Sum both to give Finance a single
                # exposure number.
                shortfall = _ZERO
                if totals["revenue_us"] > 0:
                    floor_profit = totals["revenue_us"] * US_FLOOR
                    actual_profit = totals["revenue_us"] - totals["cost_us"]
                    if actual_profit < floor_profit:
                        shortfall += floor_profit - actual_profit
                if totals["revenue_india"] > 0:
                    floor_profit = totals["revenue_india"] * INDIA_FLOOR
                    actual_profit = totals["revenue_india"] - totals["cost_india"]
                    if actual_profit < floor_profit:
                        shortfall += floor_profit - actual_profit
                gp_shortfall = shortfall
        exposure.append(
            {
                "ceo_exception_id": str(exc.id),
                "package_id": str(exc.package_id),
                "gross_profit_shortfall_usd": _fmt(gp_shortfall),
            }
        )

    return {
        "gm_by_sow": gm_by_sow,
        "gm_by_geography": {
            "US": _geo_slice(total_rev_us, total_cost_us),
            "India": _geo_slice(total_rev_india, total_cost_india),
        },
        "approved_vs_forecast_vs_actual": {
            "approved_gp": _fmt(approved_gp),
            "forecast_gp": _fmt(forecast_gp),
            "actual_gp": None,
        },
        "missing_cost_inputs": missing_cost_inputs,
        "exceptions_and_exposure": exposure,
        "notes": {
            "actual_gp": (
                "Actuals depend on the Sprint 6 actual_period table; None for now."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Delivery view
# ---------------------------------------------------------------------------


HR_LEAD_TIME_DAYS = 45


async def delivery_view(session: AsyncSession) -> dict[str, Any]:
    """Delivery dashboard aggregate.

    * ``estimates_awaiting_review`` — adviser estimates without a reviewer.
    * ``staffing_gaps`` — to-hire resource lines whose start date is inside
      the standard HR lead time window (45 days by default).
    * ``upcoming_starts`` — resource lines starting in the next 30 days.
    * ``effort_variance`` — placeholder (needs timesheet integration).
    """

    estimates = list(
        (
            await session.execute(
                select(AdviserEstimate)
                .where(AdviserEstimate.reviewer_id.is_(None))
                .order_by(AdviserEstimate.submitted_at.desc())
            )
        ).scalars()
    )
    awaiting = [
        {
            "id": str(e.id),
            "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
            "submitted_by": str(e.submitted_by) if e.submitted_by else None,
        }
        for e in estimates
    ]

    today = date.today()
    lead_time_cutoff = today + timedelta(days=HR_LEAD_TIME_DAYS)
    upcoming_cutoff = today + timedelta(days=30)

    lines = list(
        (
            await session.execute(
                select(ResourceLine)
                .where(ResourceLine.start_date >= today)
                .order_by(ResourceLine.start_date.asc())
            )
        ).scalars()
    )

    staffing_gaps: list[dict[str, Any]] = []
    upcoming_starts: list[dict[str, Any]] = []
    for line in lines:
        payload = {
            "resource_line_id": str(line.id),
            "gm_model_id": str(line.gm_model_id),
            "role": line.role,
            "seniority": line.seniority,
            "location": line.location,
            "start_date": line.start_date.isoformat(),
        }
        if line.person_name is None and line.start_date <= lead_time_cutoff:
            days_out = (line.start_date - today).days
            staffing_gaps.append(
                {
                    **payload,
                    "days_until_start": days_out,
                    "lead_time_days": HR_LEAD_TIME_DAYS,
                    "warning": (
                        f"To-hire {line.role}/{line.seniority} starts in "
                        f"{days_out}d; HR needs {HR_LEAD_TIME_DAYS}."
                    ),
                }
            )
        if line.start_date <= upcoming_cutoff:
            upcoming_starts.append({**payload, "person_name": line.person_name})

    return {
        "estimates_awaiting_review": awaiting,
        "staffing_gaps": staffing_gaps,
        "upcoming_starts": upcoming_starts,
        "effort_variance": [],
        "notes": {
            "effort_variance": (
                "Effort variance needs timesheet feed; placeholder empty list."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Sales view
# ---------------------------------------------------------------------------


async def sales_view(session: AsyncSession, user: AuthUser) -> dict[str, Any]:
    """Sales dashboard aggregate — scoped to the caller.

    * ``my_deals`` — opportunities owned by the user.
    * ``next_client_actions`` — my_deals with a ``next_client_action`` set.
    * ``missing_contracts`` — my_deals whose client's coverage isn't Complete.
    * ``adviser_estimates`` — my recent Opportunity Adviser drafts.
    * ``approval_statuses`` — packages the user submitted, with their status.
    """

    my_opps = list(
        (
            await session.execute(
                select(Opportunity)
                .where(Opportunity.owner_id == user.id)
                .order_by(Opportunity.created_at.desc())
            )
        ).scalars()
    )
    my_deals = [
        {
            "id": str(o.id),
            "hubspot_deal_id": o.hubspot_deal_id,
            "governance_status": o.governance_status,
            "sales_stage": o.sales_stage,
            "engagement_type": o.engagement_type,
            "client_id": str(o.client_id) if o.client_id else None,
            "next_client_action": o.next_client_action,
            "next_client_date": o.next_client_date.isoformat()
            if o.next_client_date
            else None,
        }
        for o in my_opps
    ]

    next_actions = [d for d in my_deals if d["next_client_action"]]

    missing_contracts: list[dict[str, Any]] = []
    client_ids = {o.client_id for o in my_opps if o.client_id is not None}
    if client_ids:
        entities = list(
            (
                await session.execute(
                    select(LegalEntity).where(LegalEntity.client_id.in_(client_ids))
                )
            ).scalars()
        )
        entity_ids = [e.id for e in entities]
        entities_by_client: dict[uuid.UUID, list[LegalEntity]] = defaultdict(list)
        for e in entities:
            entities_by_client[e.client_id].append(e)
        agreements = []
        if entity_ids:
            agreements = list(
                (
                    await session.execute(
                        select(Agreement).where(
                            Agreement.legal_entity_id.in_(entity_ids)
                        )
                    )
                ).scalars()
            )
        ags_by_entity: dict[uuid.UUID, list[Agreement]] = defaultdict(list)
        for a in agreements:
            ags_by_entity[a.legal_entity_id].append(a)
        clients = list(
            (
                await session.execute(select(Client).where(Client.id.in_(client_ids)))
            ).scalars()
        )
        clients_by_id = {c.id: c for c in clients}
        for cid in client_ids:
            client_ags: list[Agreement] = []
            for e in entities_by_client.get(cid, []):
                client_ags.extend(ags_by_entity.get(e.id, []))
            state = _coverage_state(client_ags)
            if state != "Complete":
                c = clients_by_id.get(cid)
                missing_contracts.append(
                    {
                        "client_id": str(cid),
                        "client_name": c.name if c else None,
                        "coverage_state": state,
                    }
                )

    my_estimates = list(
        (
            await session.execute(
                select(AdviserEstimate)
                .where(AdviserEstimate.submitted_by == user.id)
                .order_by(AdviserEstimate.submitted_at.desc())
                .limit(25)
            )
        ).scalars()
    )
    adviser_estimates = [
        {
            "id": str(e.id),
            "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
            "label": e.label,
            "reviewed": e.reviewer_id is not None,
        }
        for e in my_estimates
    ]

    my_packages = list(
        (
            await session.execute(
                select(ApprovalPackage)
                .where(ApprovalPackage.submitted_by == user.id)
                .order_by(ApprovalPackage.submitted_at.desc())
            )
        ).scalars()
    )
    approval_statuses = [
        {
            "id": str(p.id),
            "opportunity_id": str(p.opportunity_id),
            "status": p.status,
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        }
        for p in my_packages
    ]

    return {
        "my_deals": my_deals,
        "next_client_actions": next_actions,
        "missing_contracts": missing_contracts,
        "adviser_estimates": adviser_estimates,
        "approval_statuses": approval_statuses,
    }


# ---------------------------------------------------------------------------
# HR view
# ---------------------------------------------------------------------------


async def hr_view(session: AsyncSession) -> dict[str, Any]:
    """HR dashboard aggregate.

    * ``demand_by_skill`` — for each ``(role, seniority, location)``
      combination, the confirmed FTE demand (from released packages) and
      the probability-weighted demand from all other open packages.

    "FTE" here means the sum of resource-line allocation percentages —
    it's a proxy until the delivery-model story ships a proper capacity
    curve. Probability weighting uses 0.5 for anything short of released
    so the number is directional, not a forecast (the story is clear that
    a real forecast is a Sprint 6 concern).
    """

    opps = list(
        (
            await session.execute(
                select(Opportunity).order_by(Opportunity.created_at.asc())
            )
        ).scalars()
    )
    latest = await _load_latest_gm_for_opps(session, [o.id for o in opps])
    released = await _load_released_package_for_opps(
        session, [o.id for o in opps]
    )

    demand: dict[tuple[str, str, str], dict[str, Decimal]] = defaultdict(
        lambda: {"confirmed_fte": _ZERO, "weighted_fte": _ZERO}
    )
    for opp in opps:
        model = latest.get(opp.id)
        if model is None:
            continue
        is_released = opp.id in released
        for line in model.resource_lines:
            key = (line.role, line.seniority, line.location)
            fte = line.allocation_pct or _ZERO
            if is_released:
                demand[key]["confirmed_fte"] += fte
            else:
                demand[key]["weighted_fte"] += fte * Decimal("0.5")

    return {
        "demand_by_skill": [
            {
                "role": role,
                "seniority": seniority,
                "location": location,
                "confirmed_fte": _fmt(values["confirmed_fte"]),
                "weighted_fte": _fmt(values["weighted_fte"]),
            }
            for (role, seniority, location), values in sorted(demand.items())
        ]
    }


# ---------------------------------------------------------------------------
# Legal view
# ---------------------------------------------------------------------------


async def legal_view(session: AsyncSession) -> dict[str, Any]:
    """Legal dashboard aggregate.

    * ``nda_msa_coverage_summary`` — count of clients per coverage label.
    * ``packages_awaiting_legal`` — approval packages sitting in
      ``pending_finance_legal`` with no legal decision recorded yet.
    * ``notice_dates_approaching`` — agreements with a ``due_date`` inside
      30 days.
    """

    clients = list((await session.execute(select(Client))).scalars())
    entities = list((await session.execute(select(LegalEntity))).scalars())
    ents_by_client: dict[uuid.UUID, list[LegalEntity]] = defaultdict(list)
    for e in entities:
        ents_by_client[e.client_id].append(e)
    agreements = list((await session.execute(select(Agreement))).scalars())
    ags_by_entity: dict[uuid.UUID, list[Agreement]] = defaultdict(list)
    for a in agreements:
        ags_by_entity[a.legal_entity_id].append(a)
    coverage_counts: dict[str, int] = defaultdict(int)
    for c in clients:
        client_ags: list[Agreement] = []
        for e in ents_by_client.get(c.id, []):
            client_ags.extend(ags_by_entity.get(e.id, []))
        coverage_counts[_coverage_state(client_ags)] += 1

    from app.models.approval import Approval

    pending_pkgs = list(
        (
            await session.execute(
                select(ApprovalPackage)
                .options(selectinload(ApprovalPackage.approvals))
                .where(ApprovalPackage.status == "pending_finance_legal")
                .order_by(ApprovalPackage.submitted_at.asc())
            )
        ).scalars()
    )
    awaiting_legal: list[dict[str, Any]] = []
    for pkg in pending_pkgs:
        legal_decided = any(a.function == "legal" for a in pkg.approvals)
        if not legal_decided:
            awaiting_legal.append(
                {
                    "id": str(pkg.id),
                    "opportunity_id": str(pkg.opportunity_id),
                    "submitted_at": pkg.submitted_at.isoformat()
                    if pkg.submitted_at
                    else None,
                }
            )
    _ = Approval  # future-proof: keep the import discoverable.

    today = date.today()
    cutoff = today + timedelta(days=30)
    approaching_ags = [
        a
        for a in agreements
        if a.due_date is not None and today <= a.due_date <= cutoff
    ]
    notice_dates = [
        {
            "agreement_id": str(a.id),
            "kind": a.kind,
            "state": a.state,
            "due_date": a.due_date.isoformat() if a.due_date else None,
            "next_action": a.next_action,
            "owner_email": a.owner_email,
        }
        for a in approaching_ags
    ]

    return {
        "nda_msa_coverage_summary": dict(coverage_counts),
        "packages_awaiting_legal": awaiting_legal,
        "notice_dates_approaching": notice_dates,
    }


# ---------------------------------------------------------------------------
# Client SOW GM view
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientSowRow:
    opportunity_id: uuid.UUID
    # Nullable since 0028: an opportunity created from a SOW upload has
    # no HubSpot deal behind it. Requiring a string here made every
    # SOW-first opportunity 500 the list it appeared in.
    hubspot_deal_id: str | None
    gm_model_id: uuid.UUID
    engagement_type: str
    revenue_us: Decimal
    revenue_india: Decimal
    cost_us: Decimal
    cost_india: Decimal
    approved_gm: Optional[Decimal]
    forecast_gm: Optional[Decimal]
    actual_gm: Decimal  # zero until Sprint 6
    exception_flag: bool
    start_date: Optional[date]
    end_date: Optional[date]


def _line_dates(model: GmModel) -> tuple[Optional[date], Optional[date]]:
    """Earliest start / latest end across the resource lines, or ``None``."""

    starts = [r.start_date for r in model.resource_lines if r.start_date]
    ends = [r.end_date for r in model.resource_lines if r.end_date]
    return (min(starts) if starts else None, max(ends) if ends else None)


async def client_sow_gm_view(
    session: AsyncSession, client_id: uuid.UUID
) -> dict[str, Any]:
    """Every SOW for a client with the six GM fields the story asks for.

    Rule: **Client GM is total gross profit / total revenue over the same
    period, not a mean of percentages.** The totals row makes this explicit
    — the browser only renders what this returns; the aggregation happens
    here (blueprint §2, CLAUDE.md rule 2).
    """

    opps = list(
        (
            await session.execute(
                select(Opportunity)
                .where(Opportunity.client_id == client_id)
                .order_by(Opportunity.created_at.asc())
            )
        ).scalars()
    )
    if not opps:
        client = await session.get(Client, client_id)
        return {
            "client_id": str(client_id),
            "client_name": client.name if client else None,
            "rows": [],
            "totals": {
                "revenue": "0",
                "cost": "0",
                "gross_profit": "0",
                "client_gm": None,
                "formula": (
                    "client_gm = SUM(gross_profit_us + gross_profit_india) "
                    "/ SUM(revenue_us + revenue_india) — not a mean of percentages"
                ),
            },
        }

    latest = await _load_latest_gm_for_opps(session, [o.id for o in opps])
    released = await _load_released_package_for_opps(session, [o.id for o in opps])

    # Any pending_ceo_exception package = an outstanding exception on the SOW.
    exception_stmt = (
        select(ApprovalPackage)
        .where(ApprovalPackage.opportunity_id.in_([o.id for o in opps]))
        .where(ApprovalPackage.status == "pending_ceo_exception")
    )
    exception_pkgs = list((await session.execute(exception_stmt)).scalars())
    exception_opps = {p.opportunity_id for p in exception_pkgs}

    rows: list[ClientSowRow] = []
    total_rev_us = _ZERO
    total_rev_india = _ZERO
    total_cost_us = _ZERO
    total_cost_india = _ZERO
    for opp in opps:
        model = latest.get(opp.id)
        if model is None:
            continue
        totals = _model_totals(model)
        forecast_gm = _model_gm(model)
        approved_gm = forecast_gm if opp.id in released else None
        start, end = _line_dates(model)
        rows.append(
            ClientSowRow(
                opportunity_id=opp.id,
                hubspot_deal_id=opp.hubspot_deal_id,
                gm_model_id=model.id,
                engagement_type=model.engagement_type,
                revenue_us=totals["revenue_us"],
                revenue_india=totals["revenue_india"],
                cost_us=totals["cost_us"],
                cost_india=totals["cost_india"],
                approved_gm=approved_gm,
                forecast_gm=forecast_gm,
                actual_gm=_ZERO,
                exception_flag=opp.id in exception_opps,
                start_date=start,
                end_date=end,
            )
        )
        total_rev_us += totals["revenue_us"]
        total_rev_india += totals["revenue_india"]
        total_cost_us += totals["cost_us"]
        total_cost_india += totals["cost_india"]

    total_revenue = total_rev_us + total_rev_india
    total_cost = total_cost_us + total_cost_india
    total_gp = total_revenue - total_cost
    # THE aggregation: sum GP / sum revenue, NOT mean of the per-SOW GMs.
    client_gm: Optional[Decimal] = None
    if total_revenue > 0:
        client_gm = total_gp / total_revenue

    client = await session.get(Client, client_id)

    return {
        "client_id": str(client_id),
        "client_name": client.name if client else None,
        "rows": [
            {
                "opportunity_id": str(r.opportunity_id),
                "hubspot_deal_id": r.hubspot_deal_id,
                "gm_model_id": str(r.gm_model_id),
                "engagement_type": r.engagement_type,
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "revenue_us": _fmt(r.revenue_us),
                "revenue_india": _fmt(r.revenue_india),
                "cost_us": _fmt(r.cost_us),
                "cost_india": _fmt(r.cost_india),
                "approved_gm": _fmt(r.approved_gm),
                "forecast_gm": _fmt(r.forecast_gm),
                "actual_gm": _fmt(r.actual_gm),
                "exception_flag": r.exception_flag,
            }
            for r in rows
        ],
        "totals": {
            "revenue_us": _fmt(total_rev_us),
            "revenue_india": _fmt(total_rev_india),
            "revenue": _fmt(total_revenue),
            "cost_us": _fmt(total_cost_us),
            "cost_india": _fmt(total_cost_india),
            "cost": _fmt(total_cost),
            "gross_profit": _fmt(total_gp),
            "client_gm": _fmt(client_gm),
            "formula": (
                "client_gm = SUM(gross_profit_us + gross_profit_india) "
                "/ SUM(revenue_us + revenue_india) — not a mean of percentages"
            ),
        },
    }


__all__ = [
    "ceo_view",
    "client_sow_gm_view",
    "delivery_view",
    "finance_view",
    "hr_view",
    "legal_view",
    "sales_view",
]


# Silence unused-import guards while we deliberately keep the shape available
# for downstream widgets that may look them up.
_ = Sow
_ = datetime
_ = UTC
