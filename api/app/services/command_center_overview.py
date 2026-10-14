"""Authoritative Command Center aggregates over Forecast, Portfolio and CRM.

The account table remains a Stage 5+ HubSpot view.  Company financials do
not: imported engagements are first-class Portfolio records and often have no
``opportunity_id``.  This module deliberately starts from the permitted
engagement ledger and uses the existing forecast engine for every financial
number.
"""

from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_routing import ApprovalAssignment
from app.models.client import Client
from app.models.engagement import (
    Allocation,
    AllocationActual,
    Engagement,
    ForecastPolicy,
    Resource,
)
from app.models.hubspot_pipeline import HubspotStage
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.user import User
from app.services.approval_workflow import active_functions
from app.services.approvals import ListFilters, list_in_review_packages
from app.services.engagement_forecast import (
    allocation_rows,
    effective_cost_per_hour,
    effective_window,
    forecast_payload,
    load_calendar,
    rolloffs_from,
    today,
    visible_client_ids,
)
from app.services.hubspot_pipeline import PipelineFilters, list_opportunities
from app.services.people_demand import DEMAND_READ


ZERO = Decimal("0")
ACTION_ORDER = {
    "Closed-won without engagement": 1,
    "Rolloff without follow-on": 2,
    "Below GM floor": 3,
    "Contract coverage": 4,
    "Billing loss": 5,
    "Your SOW approval": 6,
    "Missing costs": 7,
    "Renewal needed": 8,
}


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Decimal("0.01")), "f")


def _ratio(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _decimal(value) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _month_key(day: date) -> str:
    return day.strftime("%Y-%m")


def _shift_month(day: date, offset: int) -> date:
    index = day.year * 12 + day.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _month_bounds(key: str) -> tuple[date, date]:
    year, month = (int(part) for part in key.split("-"))
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _period_months(period: str, anchor: date) -> tuple[str, ...]:
    count = 3 if period == "this_quarter" else 6
    quarter = date(anchor.year, ((anchor.month - 1) // 3) * 3 + 1, 1)
    start = quarter if period == "this_quarter" else _shift_month(quarter, 3)
    return tuple(_month_key(_shift_month(start, index)) for index in range(count))


def _href(
    path: str,
    *,
    business_unit: str | None,
    owner_id: str | None,
    currency: str,
    month: str | None = None,
    extra: dict | None = None,
) -> str:
    query = {
        "bu": business_unit,
        "owner": owner_id,
        "currency": currency,
        "month": month,
        **(extra or {}),
    }
    encoded = urlencode({key: value for key, value in query.items() if value not in (None, "")})
    return f"{path}?{encoded}" if encoded else path


def _named_person(allocation: Allocation, resource: Resource) -> bool:
    value = (allocation.person or resource.name or "").strip().casefold()
    return bool(value) and value not in {
        "tbc",
        "tbd",
        "to hire",
        "to-hire",
        "unassigned",
        "open seat",
        "open role",
    }


async def _permitted_engagements(
    session: AsyncSession,
    *,
    actor,
    scope: PipelineFilters,
    window_start: date,
    window_end: date,
) -> list[Engagement]:
    stmt = select(Engagement).where(
        Engagement.closed.is_(False),
        Engagement.start <= window_end,
        Engagement.end >= window_start,
    )
    if scope.business_unit:
        stmt = stmt.where(Engagement.business_unit.in_(scope.business_unit))
    if scope.owner:
        owner_rows = list(
            (await session.scalars(select(User).where(User.id.in_(scope.owner)))).all()
        )
        owner_names = {row.name for row in owner_rows if row.name}
        stmt = stmt.where(
            or_(
                Engagement.owner_user_id.in_(scope.owner),
                Engagement.sales_owner.in_(owner_names) if owner_names else False,
                Engagement.delivery_owner.in_(owner_names) if owner_names else False,
            )
        )
    rows = list((await session.scalars(stmt.order_by(Engagement.start, Engagement.id))).all())
    if actor is None or not rows:
        return rows
    allowed = await visible_client_ids(session, actor, (row.client_id for row in rows))
    return [row for row in rows if row.client_id in allowed]


async def _engagement_snapshot(session: AsyncSession, engagement: Engagement, *, bundle) -> dict:
    staffing = await allocation_rows(session, engagement.id, include_superseded=False)
    payload = await forecast_payload(session, engagement, bundle=bundle, store=False)
    return {
        "engagement": engagement,
        "payload": payload,
        "staffing": staffing,
    }


def _monthly_cost_coverage(snapshot: dict, bundle, month: str) -> dict:
    month_start, month_end = _month_bounds(month)
    confirmed = estimated = unresolved = 0
    for allocation, _resource in snapshot["staffing"]:
        start, end = effective_window(snapshot["engagement"], allocation)
        if start > month_end or end < month_start:
            continue
        if allocation.cost_per_hour is not None:
            confirmed += 1
        elif effective_cost_per_hour(allocation, bundle) is not None:
            estimated += 1
        else:
            unresolved += 1
    return {
        "complete": confirmed + estimated > 0 and unresolved == 0,
        "confirmed_rows": confirmed,
        "estimated_rows": estimated,
        "unresolved_rows": unresolved,
    }


def _line(payload: dict, month: str) -> dict | None:
    return next((row for row in payload.get("months", ()) if row.get("month") == month), None)


def _remaining_revenue(line: dict) -> Decimal:
    forecast = _decimal(line.get("total_revenue"))
    actual = line.get("actual_revenue")
    return forecast if actual is None else max(ZERO, forecast - _decimal(actual))


def _comparison(current: Decimal | None, previous: Decimal | None, *, points: bool = False) -> dict:
    if current is None or previous is None:
        return {"value": None, "basis": "Prior-month comparison not recorded"}
    change = current - previous
    return {
        "value": format(change, "f"),
        "basis": "percentage points versus prior month" if points else "versus prior month",
    }


async def _forecast_outlook(session: AsyncSession, actor) -> dict | None:
    if actor is None:
        return None
    try:
        from app.services.forecast_plans import outlook

        return await outlook(session, actor=actor, scenario="expected", future_quarters=2)
    except (HTTPException, ValueError):
        return None


async def build_command_overview(
    session: AsyncSession,
    *,
    scope: PipelineFilters,
    period: str = "this_quarter",
    currency: str = "USD",
    focus: str = "leadership",
    actor=None,
) -> dict:
    anchor = today()
    current_month = _month_key(anchor)
    previous_month = _month_key(_shift_month(anchor, -1))
    next_month = _month_key(_shift_month(anchor, 1))
    months = _period_months(period, anchor)
    month_start, month_end = _month_bounds(current_month)
    previous_start, _ = _month_bounds(previous_month)
    _, horizon_end = _month_bounds(months[-1])
    business_unit = scope.business_unit[0] if len(scope.business_unit) == 1 else None
    owner_id = str(scope.owner[0]) if len(scope.owner) == 1 else None

    opportunities_page = await list_opportunities(
        session,
        filters=scope,
        page=1,
        page_size=10_000,
    )
    opportunities = list(opportunities_page.items)
    engagements = await _permitted_engagements(
        session,
        actor=actor,
        scope=scope,
        window_start=previous_start,
        window_end=date.max,
    )
    client_ids = {row.client_id for row in engagements}
    clients = (
        {
            row.id: row
            for row in (
                await session.scalars(select(Client).where(Client.id.in_(client_ids)))
            ).all()
        }
        if client_ids
        else {}
    )
    bundle = await load_calendar(session) if engagements else None
    snapshots = [await _engagement_snapshot(session, row, bundle=bundle) for row in engagements]

    selected_snapshots = [
        row
        for row in snapshots
        if row["engagement"].currency == currency
        and row["engagement"].start <= horizon_end
        and row["engagement"].end >= _month_bounds(months[0])[0]
    ]
    current_snapshots = [row for row in selected_snapshots if _line(row["payload"], current_month)]
    previous_snapshots = [
        row
        for row in snapshots
        if row["engagement"].currency == currency and _line(row["payload"], previous_month)
    ]

    current_forecast = sum(
        (
            _decimal(_line(row["payload"], current_month).get("total_revenue"))
            for row in current_snapshots
        ),
        ZERO,
    )
    previous_forecast = sum(
        (
            _decimal(_line(row["payload"], previous_month).get("total_revenue"))
            for row in previous_snapshots
        ),
        ZERO,
    )
    current_actual_lines = [
        _line(row["payload"], current_month)
        for row in current_snapshots
        if _line(row["payload"], current_month).get("actual_revenue") is not None
    ]
    current_actual = (
        sum((_decimal(line.get("actual_revenue")) for line in current_actual_lines), ZERO)
        if current_actual_lines
        else None
    )
    scoped_allocation_ids = {
        allocation.id for snapshot in snapshots for allocation, _resource in snapshot["staffing"]
    }
    actual_cutoff = (
        await session.scalar(
            select(func.max(AllocationActual.updated_at)).where(
                AllocationActual.allocation_id.in_(scoped_allocation_ids),
                AllocationActual.month == current_month,
            )
        )
        if current_actual is not None and scoped_allocation_ids
        else None
    )
    actual_months = sorted(
        {
            line["month"]
            for row in snapshots
            for line in row["payload"].get("months", ())
            if line.get("actual_revenue") is not None
        }
    )
    latest_closed_actual_month = max(
        (month for month in actual_months if month < current_month),
        default=None,
    )
    latest_actual = None
    billing_loss = None
    if latest_closed_actual_month:
        latest_lines = [
            _line(row["payload"], latest_closed_actual_month)
            for row in snapshots
            if row["engagement"].currency == currency
            and _line(row["payload"], latest_closed_actual_month)
            and _line(row["payload"], latest_closed_actual_month).get("actual_revenue") is not None
        ]
        latest_actual = sum((_decimal(line.get("actual_revenue")) for line in latest_lines), ZERO)
        billing_loss = sum((_decimal(line.get("billing_loss")) for line in latest_lines), ZERO)

    current_cost_coverage = {
        row["engagement"].id: _monthly_cost_coverage(row, bundle, current_month)
        for row in current_snapshots
    }
    covered = [
        row for row in current_snapshots if current_cost_coverage[row["engagement"].id]["complete"]
    ]
    current_covered_revenue = sum(
        (_decimal(_line(row["payload"], current_month).get("total_revenue")) for row in covered),
        ZERO,
    )
    current_covered_cost = sum(
        (_decimal(_line(row["payload"], current_month).get("total_cost")) for row in covered), ZERO
    )
    current_gm = (
        (current_covered_revenue - current_covered_cost) / current_covered_revenue
        if current_covered_revenue > 0
        else None
    )
    previous_covered = [
        row
        for row in previous_snapshots
        if _monthly_cost_coverage(row, bundle, previous_month)["complete"]
    ]
    prior_revenue = sum(
        (
            _decimal(_line(row["payload"], previous_month).get("total_revenue"))
            for row in previous_covered
        ),
        ZERO,
    )
    prior_cost = sum(
        (
            _decimal(_line(row["payload"], previous_month).get("total_cost"))
            for row in previous_covered
        ),
        ZERO,
    )
    previous_gm = (prior_revenue - prior_cost) / prior_revenue if prior_revenue > 0 else None

    committed_by_month = {month: ZERO for month in months}
    actual_by_month = {month: ZERO for month in months}
    actual_recorded_by_month = {month: False for month in months}
    for snapshot in selected_snapshots:
        for month in months:
            line = _line(snapshot["payload"], month)
            if not line:
                continue
            committed_by_month[month] += _remaining_revenue(line)
            if line.get("actual_revenue") is not None:
                actual_by_month[month] += _decimal(line.get("actual_revenue"))
                actual_recorded_by_month[month] = True
    backlog_snapshots = [
        row
        for row in snapshots
        if row["engagement"].currency == currency and row["engagement"].end >= month_start
    ]
    signed_backlog = sum(
        (
            _remaining_revenue(line)
            for snapshot in backlog_snapshots
            for line in snapshot["payload"].get("months", ())
            if str(line.get("month")) >= current_month
        ),
        ZERO,
    )

    stage_ids = {row.stage_id for row in opportunities if row.stage_id}
    probabilities = (
        dict(
            (
                await session.execute(
                    select(HubspotStage.id, HubspotStage.probability).where(
                        HubspotStage.id.in_(stage_ids)
                    )
                )
            ).all()
        )
        if stage_ids
        else {}
    )
    linked_opportunity_ids = {row.opportunity_id for row in engagements if row.opportunity_id}
    linked_hubspot_ids = {row.hubspot_deal_id for row in engagements if row.hubspot_deal_id}
    open_pipeline = [
        row
        for row in opportunities
        if not row.is_closed_won
        and not row.is_closed_lost
        and row.opportunity_id not in linked_opportunity_ids
        and row.hubspot_deal_id not in linked_hubspot_ids
        and row.currency == currency
    ]
    weighted_pipeline = ZERO
    gross_pipeline = ZERO
    pipeline_missing: list[str] = []
    weighted_by_opportunity: dict[uuid.UUID, Decimal] = {}
    for row in open_pipeline:
        if row.amount is None:
            pipeline_missing.append(f"{row.name or row.hubspot_deal_id}: amount not recorded")
            continue
        gross_pipeline += row.amount
        probability = probabilities.get(row.stage_id)
        if probability is None:
            pipeline_missing.append(
                f"{row.name or row.hubspot_deal_id}: saved stage probability not recorded"
            )
            continue
        weighted = row.amount * probability
        weighted_pipeline += weighted
        weighted_by_opportunity[row.opportunity_id] = weighted

    expected_renewal_by_month = {month: ZERO for month in months}
    likely_renewal_ids: set[uuid.UUID] = set()
    renewal_coverage_months: dict[uuid.UUID, set[str]] = {}
    # The additional renewal planning fields are introduced by migration 0068.
    # ``getattr`` keeps a pre-migration developer database readable while the
    # staging deployment runs the migration before the new API task starts.
    visible_opportunity_ids = {row.opportunity_id for row in opportunities}
    renewals = (
        list(
            (
                await session.scalars(
                    select(Renewal).where(
                        Renewal.status == "open",
                        Renewal.opportunity_id.in_(visible_opportunity_ids),
                    )
                )
            ).all()
        )
        if visible_opportunity_ids
        else []
    )
    renewal_by_opportunity = {row.opportunity_id: row for row in renewals}
    for renewal in renewals:
        if getattr(renewal, "likelihood", "unassessed") != "likely":
            continue
        amount = getattr(renewal, "proposed_amount", None)
        start = getattr(renewal, "proposed_start", None)
        end = getattr(renewal, "proposed_end", None)
        probability = getattr(renewal, "probability", None)
        basis = getattr(renewal, "probability_basis", None)
        renewal_currency = getattr(renewal, "currency", None)
        if None in (amount, start, end, probability) or not basis or renewal_currency != currency:
            continue
        likely_renewal_ids.add(renewal.opportunity_id)
        term_months: list[str] = []
        cursor = date(start.year, start.month, 1)
        term_last = date(end.year, end.month, 1)
        while cursor <= term_last:
            term_months.append(_month_key(cursor))
            cursor = _shift_month(cursor, 1)
        renewal_coverage_months[renewal.opportunity_id] = set(term_months)
        visible_months = [month for month in months if month in term_months]
        if not visible_months:
            continue
        per_month = Decimal(str(amount)) * Decimal(str(probability)) / Decimal(len(term_months))
        for month in visible_months:
            expected_renewal_by_month[month] += per_month

    pipeline_by_month = {month: ZERO for month in months}
    scheduled_opportunities: set[uuid.UUID] = set()
    forecast_view = await _forecast_outlook(session, actor)
    native_signed_sources: set[str] = set()
    uncovered_forecast: dict[uuid.UUID, dict] = {}
    if forecast_view:
        opportunity_by_id = {str(row.opportunity_id): row for row in opportunities}
        engagement_by_opportunity = {
            row.opportunity_id: row for row in engagements if row.opportunity_id
        }
        engagement_by_hubspot = {
            row.hubspot_deal_id: row for row in engagements if row.hubspot_deal_id
        }
        for row in forecast_view.get("rows", ()):
            source_opportunity = row.get("opportunity_id")
            try:
                opportunity_id = uuid.UUID(str(source_opportunity))
            except (TypeError, ValueError):
                continue
            opportunity = opportunity_by_id.get(str(opportunity_id))
            if not opportunity:
                continue
            month_value = row.get("month")
            month = (
                month_value.strftime("%Y-%m")
                if isinstance(month_value, date)
                else str(month_value)[:7]
            )
            linked_engagement = engagement_by_opportunity.get(opportunity_id)
            if linked_engagement is None and opportunity.hubspot_deal_id:
                linked_engagement = engagement_by_hubspot.get(opportunity.hubspot_deal_id)
            if linked_engagement is not None and row.get("lifecycle") != "signed":
                forecast_amount = _decimal(row.get("expected") or row.get("revenue"))
                if (
                    month > _month_key(linked_engagement.end)
                    and forecast_amount > 0
                    and month not in renewal_coverage_months.get(opportunity_id, set())
                ):
                    item = uncovered_forecast.setdefault(
                        opportunity_id,
                        {
                            "opportunity": opportunity,
                            "engagement": linked_engagement,
                            "amount": ZERO,
                            "months": set(),
                        },
                    )
                    item["amount"] += forecast_amount
                    item["months"].add(month)
                continue
            if (
                opportunity_id in linked_opportunity_ids
                or opportunity.hubspot_deal_id in linked_hubspot_ids
            ):
                continue
            if row.get("lifecycle") == "signed":
                if month in committed_by_month:
                    committed_by_month[month] += _decimal(row.get("signed") or row.get("revenue"))
                source_id = str(row.get("source_id"))
                if source_id not in native_signed_sources:
                    signed_backlog += sum(
                        _decimal(candidate.get("signed") or candidate.get("revenue"))
                        for candidate in forecast_view.get("rows", ())
                        if candidate.get("lifecycle") == "signed"
                        and str(candidate.get("source_id")) == source_id
                        and str(candidate.get("month"))[:7] >= current_month
                    )
                    native_signed_sources.add(source_id)
                continue
            if opportunity_id in likely_renewal_ids:
                continue
            if month in pipeline_by_month:
                pipeline_by_month[month] += _decimal(row.get("expected"))
                scheduled_opportunities.add(opportunity_id)
    unscheduled_pipeline = sum(
        (
            amount
            for opportunity_id, amount in weighted_by_opportunity.items()
            if opportunity_id not in scheduled_opportunities
        ),
        ZERO,
    )

    staffing_rows = [
        (snapshot["engagement"], allocation, resource)
        for snapshot in snapshots
        for allocation, resource in snapshot["staffing"]
        if allocation.superseded_by is None
    ]
    current_named = {
        resource.id
        for engagement, allocation, resource in staffing_rows
        if effective_window(engagement, allocation)[0] <= month_end
        and effective_window(engagement, allocation)[1] >= month_start
        and allocation.utilization > 0
        and _named_person(allocation, resource)
    }
    current_fte = sum(
        (
            allocation.utilization
            for engagement, allocation, resource in staffing_rows
            if effective_window(engagement, allocation)[0] <= month_end
            and effective_window(engagement, allocation)[1] >= month_start
            and _named_person(allocation, resource)
        ),
        ZERO,
    )
    previous_named = {
        resource.id
        for engagement, allocation, resource in staffing_rows
        if effective_window(engagement, allocation)[0] <= _month_bounds(previous_month)[1]
        and effective_window(engagement, allocation)[1] >= previous_start
        and allocation.utilization > 0
        and _named_person(allocation, resource)
    }
    open_seats = [
        (engagement, allocation, resource)
        for engagement, allocation, resource in staffing_rows
        if effective_window(engagement, allocation)[0] <= _month_bounds(next_month)[1]
        and effective_window(engagement, allocation)[1] >= _month_bounds(next_month)[0]
        and not _named_person(allocation, resource)
    ]
    rolloffs = await rolloffs_from(
        session,
        month_start,
        engagement_ids={row.id for row in engagements},
    )
    all_active_resources = list(
        (await session.scalars(select(Resource).where(Resource.active.is_(True)))).all()
    )
    allocated_current_ids = {
        resource.id
        for engagement, allocation, resource in staffing_rows
        if effective_window(engagement, allocation)[0] <= month_end
        and effective_window(engagement, allocation)[1] >= month_start
    }
    can_read_company_people = actor is None or bool(
        set(actor.groups) & (DEMAND_READ - {"Sales", "SalesLeader"})
    )
    bench = (
        [resource for resource in all_active_resources if resource.id not in allocated_current_ids]
        if can_read_company_people and not scope.business_unit and not scope.owner
        else None
    )

    capacity_locations: dict[str, dict] = {}
    for engagement, allocation, resource in staffing_rows:
        start, end = effective_window(engagement, allocation)
        next_start, next_end = _month_bounds(next_month)
        if start > next_end or end < next_start:
            continue
        item = capacity_locations.setdefault(
            allocation.location,
            {
                "location": allocation.location,
                "required_fte": ZERO,
                "allocated_fte": ZERO,
                "open_seat_fte": ZERO,
                "people": set(),
                "open_seats": 0,
                "rolloffs": 0,
            },
        )
        item["required_fte"] += allocation.utilization
        if _named_person(allocation, resource):
            item["allocated_fte"] += allocation.utilization
            item["people"].add(resource.id)
        else:
            item["open_seat_fte"] += allocation.utilization
            item["open_seats"] += 1
    allocation_location = {
        str(allocation.id): allocation.location for _, allocation, _ in staffing_rows
    }
    for row in rolloffs:
        location = allocation_location.get(row["allocation_id"])
        if location in capacity_locations:
            capacity_locations[location]["rolloffs"] += 1
    capacity_rows = [
        {
            "location": item["location"],
            "required_fte": _money(item["required_fte"]),
            "allocated_fte": _money(item["allocated_fte"]),
            "open_seat_fte": _money(item["open_seat_fte"]),
            "people": len(item["people"]),
            "open_seats": item["open_seats"],
            "rolloffs": item["rolloffs"],
        }
        for item in sorted(capacity_locations.values(), key=lambda row: row["location"])
    ]
    managed_capacity = None
    if actor is not None and set(actor.groups) & DEMAND_READ and client_ids:
        try:
            from app.services.people_allocation import demand_allocation

            published = await demand_allocation(session, actor=actor)
        except HTTPException:
            published = None
        if published:
            next_start, next_end = _month_bounds(next_month)
            candidates = []
            for interval in published.get("intervals", ()):
                interval_start = date.fromisoformat(str(interval["start"])[:10])
                interval_end = date.fromisoformat(str(interval["end"])[:10])
                if interval_start > next_end or interval_end < next_start:
                    continue
                demands = [
                    row
                    for row in interval.get("demands", ())
                    if row.get("account_id") in {str(identifier) for identifier in client_ids}
                ]
                if not demands:
                    continue
                required = sum((_decimal(row.get("required_fte")) for row in demands), ZERO)
                gap = sum((_decimal(row.get("gap_fte")) for row in demands), ZERO)
                candidates.append((required, gap, demands))
            if candidates:
                required, gap, demand_rows = max(candidates, key=lambda item: (item[0], item[1]))
                sources = published.get("sources") or []
                complete = bool(published.get("complete"))
                managed_capacity = {
                    "required": required,
                    "allocated": required - gap if complete else None,
                    "gap": gap if complete else None,
                    "complete": complete,
                    "as_of": max((source.get("source_as_of") for source in sources), default=None),
                    "source_count": len(sources),
                    "gaps": [
                        {
                            "account": row.get("account_name") or "Account",
                            "title": row.get("title") or "Staffing demand",
                            "role": row.get("role"),
                            "href": row.get("source_url") or "/people/demand",
                            "gap_fte": _money(_decimal(row.get("gap_fte"))),
                        }
                        for row in demand_rows
                        if _decimal(row.get("gap_fte")) > 0
                    ],
                }

    policy = await session.scalar(select(ForecastPolicy).limit(1))
    billing_threshold = policy.billing_loss_threshold_amount if policy else None
    actions: list[dict] = []

    def add_action(
        *,
        identity: str,
        category: str,
        account: str,
        title: str,
        detail: str,
        owner: str | None,
        due: date | None,
        href: str,
        action: str,
        impact: Decimal | None = None,
        impact_label: str | None = None,
        period_label: str | None = None,
        missing_input: str | None = None,
    ):
        actions.append(
            {
                "id": identity,
                "rank": ACTION_ORDER[category],
                "category": category,
                "account": account,
                "title": title,
                "detail": detail,
                "owner": owner,
                "due": due.isoformat() if due else None,
                "href": href,
                "action": action,
                "impact": _money(impact),
                "impact_label": impact_label,
                "period": period_label,
                "missing_input": missing_input,
                "_impact": impact,
            }
        )

    for row in opportunities:
        if (
            not row.is_closed_won
            or row.opportunity_id in linked_opportunity_ids
            or row.hubspot_deal_id in linked_hubspot_ids
        ):
            continue
        current_quarter_start = _month_bounds(_period_months("this_quarter", anchor)[0])[0]
        if row.close_date is None or row.close_date < current_quarter_start:
            continue
        add_action(
            identity=str(row.opportunity_id),
            category="Closed-won without engagement",
            account=row.client_name or "Unlinked account",
            title=row.name or row.hubspot_deal_id or "Closed-won deal",
            detail="Closed-won work has no linked delivery engagement.",
            owner=row.owner_name or row.owner_email,
            due=row.close_date,
            href=f"/deals/{row.opportunity_id}",
            action="Create engagement from deal",
            impact=row.amount,
            impact_label="Contract value",
            period_label="Closed-won deal",
            missing_input=None if row.amount is not None else "Deal amount not recorded",
        )

    snapshot_by_id = {row["engagement"].id: row for row in snapshots}
    for rolloff in rolloffs:
        snapshot = snapshot_by_id.get(uuid.UUID(rolloff["engagement_id"]))
        engagement = snapshot["engagement"] if snapshot else None
        if engagement is None:
            continue
        line = _line(snapshot["payload"], current_month)
        exposure = _decimal(line.get("total_revenue")) if line else None
        add_action(
            identity=f"rolloff:{rolloff['engagement_id']}:{rolloff['allocation_id']}",
            category="Rolloff without follow-on",
            account=rolloff["client"],
            title=rolloff["resource"],
            detail=f"{rolloff['role']} rolls off on {rolloff['end']} with no later allocation.",
            owner=engagement.delivery_owner or engagement.sales_owner,
            due=date.fromisoformat(rolloff["end"]),
            href=f"/engagements/{engagement.id}",
            action="Plan renewal or redeployment",
            impact=exposure,
            impact_label="Current-month revenue exposure" if exposure is not None else None,
            period_label=current_month,
            missing_input=None if exposure is not None else "Current-month revenue unavailable",
        )

    for snapshot in current_snapshots:
        engagement = snapshot["engagement"]
        client = clients.get(engagement.client_id)
        line = _line(snapshot["payload"], current_month)
        if snapshot["payload"].get("status") == "BELOW FLOOR" and line:
            revenue = _decimal(line.get("total_revenue"))
            cost = _decimal(line.get("total_cost"))
            floor = bundle.project_floor_pct
            shortfall = max(ZERO, cost - revenue * (Decimal("1") - floor))
            add_action(
                identity=f"margin:{engagement.id}",
                category="Below GM floor",
                account=client.name if client else "Account",
                title=engagement.name,
                detail=f"Current-month GM is below the configured {floor * 100}% project floor.",
                owner=engagement.delivery_owner or engagement.sales_owner,
                due=None,
                href=f"/engagements/{engagement.id}",
                action="Review margin and corrective action",
                impact=shortfall,
                impact_label="Margin shortfall",
                period_label=current_month,
            )
        cost_coverage = current_cost_coverage[engagement.id]
        if cost_coverage["unresolved_rows"]:
            add_action(
                identity=f"costs:{engagement.id}",
                category="Missing costs",
                account=client.name if client else "Account",
                title=engagement.name,
                detail=f"{cost_coverage['unresolved_rows']} current-month staffing row(s) have no applicable explicit or default cost.",
                owner=engagement.delivery_owner or engagement.sales_owner,
                due=None,
                href=f"/engagements/{engagement.id}",
                action="Complete cost setup",
                impact=_decimal(line.get("total_revenue")) if line else None,
                impact_label="Revenue without cost coverage" if line else None,
                period_label=current_month,
                missing_input="Applicable staffing cost rate",
            )
        renewal = (
            renewal_by_opportunity.get(engagement.opportunity_id)
            if engagement.opportunity_id
            else None
        )
        if anchor <= engagement.end <= anchor + timedelta(days=60) and renewal is None:
            add_action(
                identity=f"renewal:{engagement.id}",
                category="Renewal needed",
                account=client.name if client else "Account",
                title=engagement.name,
                detail=f"Contract ends {engagement.end.isoformat()} and has no renewal item.",
                owner=engagement.sales_owner or engagement.delivery_owner,
                due=engagement.end,
                href=f"/engagements/{engagement.id}",
                action="Plan renewal or redeployment",
                impact=_decimal(line.get("total_revenue")) if line else None,
                impact_label="Current-month revenue exposure" if line else None,
                period_label="Next 60 days",
            )
        if (
            engagement.currency == "USD"
            and latest_closed_actual_month
            and billing_threshold is not None
        ):
            actual_line = _line(snapshot["payload"], latest_closed_actual_month)
            loss = (
                _decimal(actual_line.get("billing_loss"))
                if actual_line and actual_line.get("billing_loss") is not None
                else None
            )
            if loss is not None and loss > billing_threshold:
                add_action(
                    identity=f"billing-loss:{engagement.id}:{latest_closed_actual_month}",
                    category="Billing loss",
                    account=client.name if client else "Account",
                    title=engagement.name,
                    detail="Authoritative billing loss exceeds the configured company threshold.",
                    owner=engagement.sales_owner or engagement.delivery_owner,
                    due=None,
                    href=f"/engagements/{engagement.id}",
                    action="Investigate billing loss",
                    impact=loss,
                    impact_label="Billing loss",
                    period_label=latest_closed_actual_month,
                )

    for item in uncovered_forecast.values():
        opportunity = item["opportunity"]
        engagement = item["engagement"]
        client = clients.get(engagement.client_id)
        months_label = ", ".join(sorted(item["months"]))
        add_action(
            identity=f"contract-coverage:{engagement.id}",
            category="Contract coverage",
            account=client.name if client else "Account",
            title=opportunity.name or engagement.name,
            detail=(
                f"Forecast revenue extends beyond the signed term ending "
                f"{engagement.end.isoformat()} in {months_label}."
            ),
            owner=engagement.sales_owner or engagement.delivery_owner,
            due=engagement.end,
            href=f"/renewals?opportunity_id={opportunity.opportunity_id}",
            action="Review contract coverage",
            impact=item["amount"],
            impact_label="Uncovered forecast",
            period_label=months_label,
            missing_input="Signed renewal or documented renewal coverage",
        )

    if actor is not None:
        try:
            packages, _, _ = await list_in_review_packages(
                session,
                ListFilters(reader_id=actor.id, actor_id=actor.id, page=1, size=200),
            )
        except HTTPException:
            packages = []
        for package in packages:
            assignment = await session.scalar(
                select(ApprovalAssignment).where(
                    ApprovalAssignment.package_id == package.id,
                    ApprovalAssignment.approver_id == actor.id,
                    ApprovalAssignment.function.in_(active_functions(package)),
                )
            )
            if assignment is None:
                continue
            opportunity = await session.get(Opportunity, package.opportunity_id)
            client = (
                await session.get(Client, opportunity.client_id)
                if opportunity and opportunity.client_id
                else None
            )
            add_action(
                identity=f"approval:{package.id}:{assignment.function}",
                category="Your SOW approval",
                account=client.name if client else "Account",
                title=opportunity.name if opportunity else "SOW",
                detail=f"{assignment.function.title()} approval is waiting for you.",
                owner=actor.name,
                due=assignment.due_date,
                href=f"/sows/{package.opportunity_id}/approvals",
                action="Review SOW",
                period_label="Current approval stage",
            )

    actions.sort(
        key=lambda row: (
            row["_impact"] is None,
            -(row["_impact"] or ZERO),
            row["due"] or "9999-12-31",
            row["rank"],
            row["account"],
        )
    )
    for row in actions:
        row.pop("_impact", None)

    largest_risk = next((row for row in actions if row["impact"] is not None), None)
    opportunity_statement = {
        "kind": "opportunity",
        "title": f"{_money(weighted_pipeline)} weighted pipeline across {len(weighted_by_opportunity)} eligible deal(s)",
        "detail": f"{_money(unscheduled_pipeline)} is unscheduled and remains outside monthly revenue.",
        "href": _href(
            "/pipeline", business_unit=business_unit, owner_id=owner_id, currency=currency
        ),
    }
    blockers = [row for row in actions if row["missing_input"]]
    brief = [
        {
            "kind": "risk",
            "title": (
                f"{largest_risk['impact_label']}: {largest_risk['impact']}"
                if largest_risk
                else "No quantified financial risk in this scope"
            ),
            "detail": (
                f"{largest_risk['account']} · {largest_risk['detail']}"
                if largest_risk
                else "Unquantified actions remain listed in the queue."
            ),
            "href": largest_risk["href"]
            if largest_risk
            else _href(
                "/portfolio", business_unit=business_unit, owner_id=owner_id, currency=currency
            ),
        },
        opportunity_statement,
        {
            "kind": "blocker",
            "title": f"{len(blockers)} record(s) need financial inputs"
            if blockers
            else "No consequential data blocker",
            "detail": blockers[0]["missing_input"]
            if blockers
            else "All displayed financial values identify their current evidence basis.",
            "href": blockers[0]["href"] if blockers else "/settings/forecast",
        },
    ]

    lifecycle_counts = {
        "pipeline": sum(
            1
            for row in opportunities
            if not row.is_closed_won
            and not row.is_closed_lost
            and row.sow_count == 0
            and row.opportunity_id not in linked_opportunity_ids
            and row.hubspot_deal_id not in linked_hubspot_ids
        ),
        "sow_in_approval": sum(
            1
            for row in opportunities
            if row.sow_approval_state
            in {"in_review_delivery_hr", "in_review_finance_legal", "ceo_exception"}
        ),
        "signed": sum(1 for row in opportunities if row.sow_approval_state == "signed"),
        "engagement_created": len(engagements),
        "active": sum(1 for row in engagements if row.start <= anchor <= row.end),
        "renewal_due": sum(
            1
            for row in renewals
            if row.opportunity_id in {opp.opportunity_id for opp in opportunities}
        ),
    }
    lifecycle_items = [
        {
            "key": "pipeline",
            "label": "Pipeline",
            "count": lifecycle_counts["pipeline"],
            "entity": "open deals",
            "href": _href(
                "/pipeline", business_unit=business_unit, owner_id=owner_id, currency=currency
            ),
        },
        {
            "key": "sow_in_approval",
            "label": "SOW in approval",
            "count": lifecycle_counts["sow_in_approval"],
            "entity": "SOWs",
            "href": "/sows?state=in_review",
        },
        {
            "key": "signed",
            "label": "Signed",
            "count": lifecycle_counts["signed"],
            "entity": "signed SOWs",
            "href": "/sows?state=signed",
        },
        {
            "key": "engagement_created",
            "label": "Engagement created",
            "count": lifecycle_counts["engagement_created"],
            "entity": "engagements",
            "href": _href(
                "/portfolio", business_unit=business_unit, owner_id=owner_id, currency=currency
            ),
        },
        {
            "key": "active",
            "label": "Active",
            "count": lifecycle_counts["active"],
            "entity": "engagements",
            "href": _href(
                "/projects", business_unit=business_unit, owner_id=owner_id, currency=currency
            ),
        },
        {
            "key": "renewal_due",
            "label": "Renewal due",
            "count": lifecycle_counts["renewal_due"],
            "entity": "renewal items",
            "href": "/renewals?status=open",
        },
    ]

    revenue_months = []
    for month in months:
        committed = committed_by_month[month]
        renewal = expected_renewal_by_month[month]
        pipeline = pipeline_by_month[month]
        revenue_months.append(
            {
                "month": month,
                "actual": _money(actual_by_month[month])
                if actual_recorded_by_month[month]
                else None,
                "committed": _money(committed),
                "expected_renewal": _money(renewal),
                "pipeline_upside": _money(pipeline),
                "committed_total": _money(committed),
                "expected_total": _money(committed + renewal),
                "upside_total": _money(committed + renewal + pipeline),
                # Compatibility with the first redesign contract.
                "remaining_signed": _money(committed),
                "potential_expected": _money(renewal + pipeline),
                "potential_upside": _money(renewal + pipeline),
            }
        )

    failed_notifications = int(
        (
            await session.scalar(
                select(func.count(Notification.id)).where(Notification.status == "failed")
            )
        )
        or 0
    )
    latest_hubspot = max(
        (row.hubspot_last_activity_at for row in opportunities if row.hubspot_last_activity_at),
        default=None,
    )
    missing_cost_engagements = [
        row
        for row in current_snapshots
        if current_cost_coverage[row["engagement"].id]["unresolved_rows"]
    ]
    confirmed_engagements = sum(
        1 for row in covered if current_cost_coverage[row["engagement"].id]["estimated_rows"] == 0
    )
    estimated_engagements = sum(
        1 for row in covered if current_cost_coverage[row["engagement"].id]["estimated_rows"] > 0
    )
    revenue_coverage = current_covered_revenue / current_forecast if current_forecast > 0 else None

    return {
        "scope": {"period": period, "months": list(months), "currency": currency, "focus": focus},
        "tiles": {
            "revenue": {
                "forecast": _money(current_forecast),
                "actual_to_date": _money(current_actual),
                "actual_cutoff": actual_cutoff.isoformat() if actual_cutoff else None,
                "latest_actual_month": latest_closed_actual_month,
                "latest_actual": _money(latest_actual),
                "last_closed_billing_loss": _money(billing_loss),
                "comparison": _comparison(current_forecast, previous_forecast),
                "href": _href(
                    "/forecast",
                    business_unit=business_unit,
                    owner_id=owner_id,
                    currency=currency,
                    month=current_month,
                ),
            },
            "gm": {
                "value": _ratio(current_gm),
                "covered_engagements": len(covered),
                "total_engagements": len(current_snapshots),
                "revenue_coverage_pct": _ratio(revenue_coverage),
                "confirmed_cost_engagements": confirmed_engagements,
                "estimated_cost_engagements": estimated_engagements,
                "missing_cost_engagements": len(missing_cost_engagements),
                "comparison": _comparison(current_gm, previous_gm, points=True),
                "href": _href(
                    "/portfolio",
                    business_unit=business_unit,
                    owner_id=owner_id,
                    currency=currency,
                    month=current_month,
                    extra={"cost_coverage": "covered"},
                ),
                "fix_href": "/settings/forecast",
            },
            "backlog": {
                "amount": _money(signed_backlog),
                "engagements": len(backlog_snapshots) + len(native_signed_sources),
                "comparison": {"value": None, "basis": "Prior-month comparison not recorded"},
                "href": _href(
                    "/forecast",
                    business_unit=business_unit,
                    owner_id=owner_id,
                    currency=currency,
                    extra={"scenario": "committed"},
                ),
            },
            "pipeline": {
                "weighted": _money(weighted_pipeline),
                "gross": _money(gross_pipeline),
                "eligible_deals": len(weighted_by_opportunity),
                "unscheduled_weighted": _money(unscheduled_pipeline),
                "closed_won_gaps": sum(
                    1 for row in actions if row["category"] == "Closed-won without engagement"
                ),
                "missing": sorted(set(pipeline_missing)),
                "comparison": {"value": None, "basis": "Prior-month comparison not recorded"},
                "href": _href(
                    "/pipeline",
                    business_unit=business_unit,
                    owner_id=owner_id,
                    currency=currency,
                    extra={"open_closed": "open"},
                ),
            },
            "people": {
                "billable_people": len(current_named),
                "billable_fte": _money(current_fte),
                "bench_people": len(bench) if bench is not None else None,
                "bench_basis": "active people without a current allocation"
                if bench is not None
                else "Bench is not attributable to the selected BU or owner",
                "rolloffs_60_days": len(rolloffs),
                "open_seats": len(open_seats),
                "open_seat_fte": _money(
                    sum((allocation.utilization for _, allocation, _ in open_seats), ZERO)
                ),
                "comparison": {
                    "value": len(current_named) - len(previous_named),
                    "basis": "billable people versus prior month",
                },
                "billable_href": _href(
                    "/portfolio",
                    business_unit=business_unit,
                    owner_id=owner_id,
                    currency=currency,
                    month=current_month,
                    extra={"people": "billable"},
                ),
                "bench_href": "/people/supply?status=bench",
                "rolloff_href": "/portfolio?view=rolloffs",
            },
        },
        "actions": actions[:50],
        "brief": brief,
        "metrics": {
            "open_opportunity_value": _money(gross_pipeline) if open_pipeline else None,
            "sows_in_progress": sum(
                1 for row in opportunities if row.sow_approval_state not in {"none", "signed"}
            ),
            "committed_revenue": _money(signed_backlog),
            "committed_gm_pct": _ratio(current_gm),
            "planned_people": len(current_named),
        },
        "lifecycle": {
            **lifecycle_counts,
            # Compatibility aliases; the new UI uses ``lifecycle_items``.
            "intake": 0,
            "scope_gm": 0,
            "function_reviews": lifecycle_counts["sow_in_approval"],
            "ceo_exception": 0,
            "signature": lifecycle_counts["signed"],
            "handoff": 0,
        },
        "lifecycle_items": lifecycle_items,
        "revenue": {
            "actual": _money(current_actual),
            "remaining_signed": _money(signed_backlog),
            "potential_expected": _money(
                sum(expected_renewal_by_month.values(), ZERO)
                + sum(pipeline_by_month.values(), ZERO)
            ),
            "potential_upside": _money(
                sum(expected_renewal_by_month.values(), ZERO)
                + sum(pipeline_by_month.values(), ZERO)
            ),
            "unscheduled_weighted_pipeline": _money(unscheduled_pipeline),
            "currency": currency,
            "months": revenue_months,
            "cost_coverage_complete": len(covered) == len(current_snapshots),
            "financial_blockers": sorted(
                {
                    f"{row['engagement'].name}: "
                    f"{current_cost_coverage[row['engagement'].id]['unresolved_rows']} "
                    "current-month staffing row(s) need a cost rate"
                    for row in missing_cost_engagements
                }
            ),
        },
        "capacity": {
            "month": next_month,
            "locations": capacity_rows,
            "required_fte": _money(
                managed_capacity["required"]
                if managed_capacity
                else sum((Decimal(row["required_fte"]) for row in capacity_rows), ZERO)
            ),
            "allocated_fte": _money(
                managed_capacity["allocated"]
                if managed_capacity
                else sum((Decimal(row["allocated_fte"]) for row in capacity_rows), ZERO)
            ),
            "gap_fte": _money(
                managed_capacity["gap"]
                if managed_capacity
                else sum((Decimal(row["open_seat_fte"]) for row in capacity_rows), ZERO)
            ),
            "status": (
                "unknown"
                if managed_capacity and not managed_capacity["complete"]
                else "attention"
                if (managed_capacity and managed_capacity["gap"] > 0)
                or (not managed_capacity and open_seats)
                else "current"
            ),
            "message": (
                "Published workforce evidence is incomplete; allocated and gap FTE are withheld."
                if managed_capacity and not managed_capacity["complete"]
                else f"{_money(managed_capacity['gap'])} FTE remains uncovered at peak demand."
                if managed_capacity and managed_capacity["gap"] > 0
                else f"{len(open_seats)} open seat(s) and {len(rolloffs)} roll-off(s) are visible for planning."
            ),
            "gaps": managed_capacity["gaps"] if managed_capacity else [],
            "source_status": (
                "unknown"
                if managed_capacity and not managed_capacity["complete"]
                else "current"
                if managed_capacity or staffing_rows
                else "empty"
            ),
            "source_as_of": managed_capacity["as_of"] if managed_capacity else None,
            "source_detail": (
                f"{managed_capacity['source_count']} managed workforce source(s); "
                + (
                    "publication has unresolved inputs"
                    if not managed_capacity["complete"]
                    else "allocation ledger shown by location"
                )
                if managed_capacity
                else f"{len(staffing_rows)} current allocation row(s); TBC rows are open demand, not people"
            ),
        },
        "recent_changes": [],
        "sources": [
            {
                "name": "Portfolio engagement ledger",
                "status": "current" if engagements else "empty",
                "as_of": None,
                "detail": f"{len(engagements)} permitted open engagement(s), including imported records",
            },
            {
                "name": "Forecast calculation service",
                "status": "attention" if missing_cost_engagements else "current",
                "as_of": None,
                "detail": f"{len(covered)} of {len(current_snapshots)} current-month engagement(s) have complete financial inputs",
            },
            {
                "name": "Workforce supply",
                "status": (
                    "attention"
                    if managed_capacity and not managed_capacity["complete"]
                    else "current"
                    if managed_capacity or staffing_rows
                    else "empty"
                ),
                "as_of": managed_capacity["as_of"] if managed_capacity else None,
                "detail": (
                    f"{managed_capacity['source_count']} managed source(s) "
                    + (
                        "have unresolved inputs"
                        if not managed_capacity["complete"]
                        else "reconciled with the allocation ledger"
                    )
                    if managed_capacity
                    else f"{len(staffing_rows)} dated allocation row(s)"
                ),
            },
            {
                "name": "HubSpot pipeline mirror",
                "status": "current" if opportunities else "empty",
                "as_of": latest_hubspot.isoformat() if latest_hubspot else None,
                "detail": f"{len(opportunities)} role-scoped deal(s)",
            },
            {
                "name": "Notifications",
                "status": "attention" if failed_notifications else "current",
                "as_of": None,
                "detail": f"{failed_notifications} failed delivery attempt(s)",
                "href": "/settings/system-health",
            },
        ],
        "configuration_gaps": (
            ["Configure a company billing-loss threshold before billing-loss alerts can be ranked"]
            if billing_threshold is None
            else []
        ),
    }
