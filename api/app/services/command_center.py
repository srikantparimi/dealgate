"""Read models for the operational Command Center.

The Accounts & engagements population is deliberately implemented here,
server-side. It is a HubSpot sales-stage view and never infers eligibility
from a SOW or project stage.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.engagement import Engagement
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.notification import Notification
from app.models.user import User
from app.services.hubspot_pipeline import PipelineFilters, matching_opportunity_ids
from app.services.hubspot_pipeline import list_opportunities


STAGE5_SCOPE_LABEL = "HubSpot deals · Stage 5 and above"


@dataclass(frozen=True)
class CommandAccountFilters:
    search: str | None = None
    page: int = 1
    page_size: int = 25
    period: str = "this_quarter"
    health: str = "all"
    watched_opportunity_ids: tuple[uuid.UUID, ...] = ()
    watched_client_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class CommandAccountRow:
    opportunity_id: uuid.UUID
    hubspot_deal_id: str
    account_id: uuid.UUID | None
    account_name: str
    engagement_id: uuid.UUID | None
    engagement_name: str
    business_unit: str | None
    pipeline_id: str
    stage_id: str
    stage_label: str
    stage_order: int
    is_closed_won: bool
    sow_stage: str
    currency: str | None
    deal_value: Decimal | None
    owner_id: uuid.UUID | None
    owner_name: str | None
    owner_email: str | None
    next_action: str | None
    next_action_due: str | None
    period_revenue: Decimal | None = None
    forecast_gm_pct: Decimal | None = None
    assigned_fte: Decimal | None = None
    required_fte: Decimal | None = None
    financial_status: str = "unavailable"
    financial_blockers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommandAccountsPage:
    items: tuple[CommandAccountRow, ...]
    total: int
    page: int
    page_size: int
    scope_label: str
    configuration_gaps: tuple[str, ...]


async def _configuration_gaps(session: AsyncSession) -> tuple[str, ...]:
    stage_counts = (
        await session.execute(
            select(
                HubspotPipeline.id,
                HubspotPipeline.label,
                func.count(HubspotStage.id),
            )
            .join(
                HubspotStage,
                and_(
                    HubspotStage.pipeline_id == HubspotPipeline.id,
                    HubspotStage.archived.is_(False),
                ),
                isouter=True,
            )
            .where(HubspotPipeline.archived.is_(False))
            .group_by(HubspotPipeline.id, HubspotPipeline.label)
        )
    ).all()
    known = {pipeline_id for pipeline_id, _, _ in stage_counts}
    missing_definitions = set(
        (
            await session.scalars(
                select(Opportunity.hubspot_pipeline_id)
                .where(
                    Opportunity.source == "hubspot",
                    Opportunity.archived_at.is_(None),
                    Opportunity.hubspot_pipeline_id.is_not(None),
                )
                .distinct()
            )
        ).all()
    ) - known
    gaps = [
        f"{label} has no identifiable Stage 5 threshold"
        for _, label, count in stage_counts
        if int(count or 0) < 5
    ]
    gaps.extend(
        f"Pipeline {pipeline_id} has no identifiable Stage 5 threshold"
        for pipeline_id in sorted(missing_definitions)
    )
    return tuple(sorted(gaps))


def _stage5_thresholds():
    ranked = (
        select(
            HubspotStage.pipeline_id.label("pipeline_id"),
            HubspotStage.display_order.label("display_order"),
            func.row_number()
            .over(
                partition_by=HubspotStage.pipeline_id,
                order_by=(HubspotStage.display_order.asc(), HubspotStage.id.asc()),
            )
            .label("stage_number"),
        )
        .join(HubspotPipeline, HubspotPipeline.id == HubspotStage.pipeline_id)
        .where(
            HubspotStage.archived.is_(False),
            HubspotPipeline.archived.is_(False),
        )
        .cte("command_ranked_stages")
    )
    return (
        select(ranked.c.pipeline_id, ranked.c.display_order)
        .where(ranked.c.stage_number == 5)
        .cte("command_stage5_thresholds")
    )


def _period_months(period: str, today: date | None = None) -> tuple[str, ...]:
    today = today or date.today()
    quarter_start = ((today.month - 1) // 3) * 3 + 1
    if period == "next_two_quarters":
        start_year = today.year + (1 if quarter_start + 3 > 12 else 0)
        start_month = ((quarter_start + 2) % 12) + 1
        count = 6
    else:
        start_year = today.year
        start_month = quarter_start
        count = 3
    months = []
    year, month = start_year, start_month
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(months)


async def _engagement_financials(
    session: AsyncSession,
    engagement: Engagement,
    *,
    months: tuple[str, ...],
) -> dict:
    from app.services.engagement_forecast import (
        ForecastInputError,
        forecast_payload,
        margin_pct,
    )

    try:
        payload = await forecast_payload(session, engagement, store=False)
    except ForecastInputError as error:
        detail = error.detail if isinstance(error.detail, list) else [str(error.detail)]
        return {
            "status": "incomplete",
            "blockers": tuple(str(item) for item in detail),
            "actual": None,
            "remaining": None,
            "cost": None,
            "gm_pct": None,
            "people": None,
            "monthly": {},
        }

    selected = [line for line in payload.get("months", []) if line.get("month") in months]
    actual = Decimal("0")
    remaining = Decimal("0")
    cost = Decimal("0")
    monthly: dict[str, dict[str, Decimal | int]] = {}
    for line in selected:
        actual_value = line.get("actual_revenue")
        planned = Decimal(str(line.get("total_revenue") or "0"))
        actual_amount = Decimal(str(actual_value)) if actual_value is not None else Decimal("0")
        remaining_amount = Decimal("0") if actual_value is not None else planned
        month_cost = Decimal(str(line.get("total_cost") or "0"))
        actual += actual_amount
        remaining += remaining_amount
        cost += month_cost
        monthly[str(line["month"])] = {
            "actual": actual_amount,
            "signed": remaining_amount,
            "cost": month_cost,
            "people": int(line.get("people") or 0),
        }
    revenue = actual + remaining
    missing = tuple(str(item) for item in payload.get("missing") or ())
    complete = payload.get("status") != "INCOMPLETE" and not missing
    return {
        "status": "complete" if complete else "incomplete",
        "blockers": missing,
        "actual": actual,
        "remaining": remaining,
        "cost": cost if complete else None,
        "gm_pct": margin_pct(revenue, cost) if complete else None,
        "people": max((int(line.get("people") or 0) for line in selected), default=0),
        "monthly": monthly,
    }
async def list_command_accounts(
    session: AsyncSession,
    *,
    scope: PipelineFilters,
    filters: CommandAccountFilters | None = None,
) -> CommandAccountsPage:
    filters = filters or CommandAccountFilters()
    page = max(1, filters.page)
    page_size = min(100, max(1, filters.page_size))
    scoped = replace(scope, include_closed=True, open_closed="any")
    allowed_ids = await matching_opportunity_ids(session, scoped)
    gaps = await _configuration_gaps(session)
    if not allowed_ids:
        return CommandAccountsPage((), 0, page, page_size, STAGE5_SCOPE_LABEL, gaps)

    thresholds = _stage5_thresholds()
    stmt = (
        select(Opportunity, Client, User, HubspotStage)
        .join(Client, Client.id == Opportunity.client_id, isouter=True)
        .join(User, User.id == Opportunity.owner_id, isouter=True)
        .join(
            HubspotStage,
            and_(
                HubspotStage.id == Opportunity.hubspot_stage_id,
                HubspotStage.pipeline_id == Opportunity.hubspot_pipeline_id,
            ),
        )
        .join(thresholds, thresholds.c.pipeline_id == Opportunity.hubspot_pipeline_id)
        .where(
            Opportunity.id.in_(allowed_ids),
            Opportunity.source == "hubspot",
            Opportunity.hubspot_deal_id.is_not(None),
            Opportunity.archived_at.is_(None),
            Opportunity.is_closed_lost.is_(False),
            HubspotStage.archived.is_(False),
            HubspotStage.display_order >= thresholds.c.display_order,
        )
    )
    query = (filters.search or "").strip().lower()
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(Client.name, "")).like(like),
                func.lower(func.coalesce(Opportunity.name, "")).like(like),
                func.lower(func.coalesce(Opportunity.hubspot_deal_id, "")).like(like),
                func.lower(func.coalesce(User.name, "")).like(like),
            )
        )
    if filters.health == "at_risk":
        stmt = stmt.where(
            or_(
                Opportunity.owner_id.is_(None),
                Opportunity.next_client_date < date.today(),
            )
        )
    elif filters.health == "watching":
        watched = []
        if filters.watched_opportunity_ids:
            watched.append(Opportunity.id.in_(filters.watched_opportunity_ids))
        if filters.watched_client_ids:
            watched.append(Opportunity.client_id.in_(filters.watched_client_ids))
        stmt = stmt.where(or_(*watched) if watched else Opportunity.id == uuid.UUID(int=0))

    total = int(
        (
            await session.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
        )
        or 0
    )
    stmt = stmt.order_by(
        Client.name.asc(),
        Opportunity.name.asc(),
        Opportunity.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)
    records = (await session.execute(stmt)).all()

    opportunity_ids = [opp.id for opp, _, _, _ in records]
    engagements = (
        (
            await session.scalars(
                select(Engagement)
                .where(
                    Engagement.opportunity_id.in_(opportunity_ids),
                    Engagement.closed.is_(False),
                )
                .order_by(Engagement.created_at.desc(), Engagement.id.desc())
            )
        ).all()
        if opportunity_ids
        else []
    )
    engagement_by_opportunity: dict[uuid.UUID, Engagement] = {}
    for engagement in engagements:
        if engagement.opportunity_id is not None:
            engagement_by_opportunity.setdefault(engagement.opportunity_id, engagement)

    months = _period_months(filters.period)
    financials: dict[uuid.UUID, dict] = {}
    for engagement in engagement_by_opportunity.values():
        financials[engagement.id] = await _engagement_financials(
            session, engagement, months=months
        )

    items = []
    for opportunity, client, owner, stage in records:
        engagement = engagement_by_opportunity.get(opportunity.id)
        finance = financials.get(engagement.id) if engagement else None
        period_revenue = None
        if finance and finance["actual"] is not None and finance["remaining"] is not None:
            period_revenue = finance["actual"] + finance["remaining"]
        items.append(
            CommandAccountRow(
                opportunity_id=opportunity.id,
                hubspot_deal_id=opportunity.hubspot_deal_id,
                account_id=client.id if client else None,
                account_name=client.name if client else "Unlinked account",
                engagement_id=engagement.id if engagement else None,
                engagement_name=(engagement.name if engagement else opportunity.name)
                or opportunity.hubspot_deal_id,
                business_unit=(engagement.business_unit if engagement else None)
                or opportunity.business_unit_value
                or (client.business_unit_value if client else None),
                pipeline_id=opportunity.hubspot_pipeline_id,
                stage_id=stage.id,
                stage_label=stage.label,
                stage_order=stage.display_order,
                is_closed_won=opportunity.is_closed_won,
                sow_stage=opportunity.governance_status,
                currency=opportunity.currency,
                deal_value=opportunity.amount,
                owner_id=owner.id if owner else None,
                owner_name=owner.name if owner else None,
                owner_email=owner.email if owner else None,
                next_action=opportunity.next_client_action,
                next_action_due=(
                    opportunity.next_client_date.isoformat()
                    if opportunity.next_client_date
                    else None
                ),
                period_revenue=period_revenue,
                forecast_gm_pct=finance["gm_pct"] if finance else None,
                assigned_fte=(
                    Decimal(str(finance["people"]))
                    if finance and finance["people"] is not None
                    else None
                ),
                required_fte=None,
                financial_status=finance["status"] if finance else "unavailable",
                financial_blockers=finance["blockers"] if finance else (),
            )
        )

    return CommandAccountsPage(
        tuple(items), total, page, page_size, STAGE5_SCOPE_LABEL, gaps
    )


async def command_accounts_csv(
    session: AsyncSession,
    *,
    scope: PipelineFilters,
    filters: CommandAccountFilters | None = None,
) -> str:
    filters = filters or CommandAccountFilters()
    page_number = 1
    rows: list[CommandAccountRow] = []
    total = 0
    while page_number == 1 or len(rows) < total:
        page = await list_command_accounts(
            session,
            scope=scope,
            filters=replace(filters, page=page_number, page_size=100),
        )
        total = page.total
        rows.extend(page.items)
        if not page.items:
            break
        page_number += 1
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Account",
            "Engagement",
            "HubSpot deal",
            "Pipeline",
            "Sales stage",
            "Business unit",
            "Currency",
            "Deal value",
            "Owner",
            "Next action",
            "Due",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.account_name,
                row.engagement_name,
                row.hubspot_deal_id,
                row.pipeline_id,
                row.stage_label,
                row.business_unit or "",
                row.currency or "",
                "" if row.deal_value is None else format(row.deal_value, "f"),
                row.owner_name or row.owner_email or "",
                row.next_action or "",
                row.next_action_due or "",
            ]
        )
    return output.getvalue()


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


async def build_command_overview(
    session: AsyncSession,
    *,
    scope: PipelineFilters,
    period: str = "this_quarter",
    currency: str = "USD",
    focus: str = "leadership",
) -> dict:
    """Build the non-table sections from canonical pipeline and forecast data."""

    months = _period_months(period)
    scoped = replace(scope, include_closed=True, open_closed="any")
    opportunities_page = await list_opportunities(
        session, filters=scoped, page=1, page_size=10_000
    )
    opportunities = list(opportunities_page.items)
    opportunity_ids = [row.opportunity_id for row in opportunities]

    engagements = (
        (
            await session.scalars(
                select(Engagement)
                .where(
                    Engagement.opportunity_id.in_(opportunity_ids),
                    Engagement.closed.is_(False),
                )
                .order_by(Engagement.created_at.desc(), Engagement.id.desc())
            )
        ).all()
        if opportunity_ids
        else []
    )
    first_engagement_by_opportunity: dict[uuid.UUID, Engagement] = {}
    for engagement in engagements:
        if engagement.opportunity_id is not None:
            first_engagement_by_opportunity.setdefault(
                engagement.opportunity_id, engagement
            )

    financial_rows: list[tuple[Engagement, dict]] = []
    for engagement in first_engagement_by_opportunity.values():
        financial_rows.append(
            (
                engagement,
                await _engagement_financials(session, engagement, months=months),
            )
        )

    monthly = {
        month: {
            "month": month,
            "actual": Decimal("0"),
            "remaining_signed": Decimal("0"),
            "potential_expected": Decimal("0"),
            "potential_upside": Decimal("0"),
        }
        for month in months
    }
    actual = Decimal("0")
    remaining = Decimal("0")
    signed_cost = Decimal("0")
    has_signed_revenue = False
    complete_costs = True
    planned_people = 0
    financial_blockers: list[str] = []
    for engagement, finance in financial_rows:
        if engagement.currency != currency:
            continue
        if finance["actual"] is not None and finance["remaining"] is not None:
            has_signed_revenue = True
            actual += finance["actual"]
            remaining += finance["remaining"]
        if finance["cost"] is None:
            complete_costs = False
            financial_blockers.extend(finance["blockers"])
        else:
            signed_cost += finance["cost"]
        planned_people = max(planned_people, int(finance["people"] or 0))
        for month, values in finance["monthly"].items():
            if month in monthly:
                monthly[month]["actual"] += values["actual"]
                monthly[month]["remaining_signed"] += values["signed"]

    stage_ids = {row.stage_id for row in opportunities if row.stage_id}
    stage_probability = dict(
        (
            await session.execute(
                select(HubspotStage.id, HubspotStage.probability).where(
                    HubspotStage.id.in_(stage_ids)
                )
            )
        ).all()
    ) if stage_ids else {}
    potential_expected = Decimal("0")
    potential_upside = Decimal("0")
    potential_complete = True
    for row in opportunities:
        if row.is_closed_won or row.is_closed_lost or row.currency != currency:
            continue
        if row.amount is None:
            potential_complete = False
            continue
        potential_upside += row.amount
        probability = stage_probability.get(row.stage_id)
        if probability is None:
            potential_complete = False
        else:
            potential_expected += row.amount * probability
        close_month = row.close_date.strftime("%Y-%m") if row.close_date else None
        if close_month in monthly:
            monthly[close_month]["potential_upside"] += row.amount
            if probability is not None:
                monthly[close_month]["potential_expected"] += row.amount * probability

    signed_revenue = actual + remaining
    gm_pct = None
    if has_signed_revenue and complete_costs and signed_revenue != 0:
        gm_pct = (signed_revenue - signed_cost) / signed_revenue

    lifecycle = {
        "pipeline": 0,
        "intake": 0,
        "scope_gm": 0,
        "function_reviews": 0,
        "ceo_exception": 0,
        "signature": 0,
        "handoff": 0,
        "active": len(first_engagement_by_opportunity),
    }
    for row in opportunities:
        state = row.sow_approval_state
        if row.sow_count == 0:
            lifecycle["pipeline"] += 1
        elif state == "draft":
            lifecycle["intake"] += 1
        elif state in {"none", "changes_requested"}:
            lifecycle["scope_gm"] += 1
        elif state in {"in_review_delivery_hr", "in_review_finance_legal"}:
            lifecycle["function_reviews"] += 1
        elif state == "ceo_exception":
            lifecycle["ceo_exception"] += 1
        elif state in {"approved", "awaiting_signature"}:
            lifecycle["signature"] += 1
        elif state == "signed":
            lifecycle["handoff"] += 1

    focus_flags = {
        "delivery": {"pending_approval", "closed_won_not_released"},
        "sales": {"overdue_action", "no_owner", "stalled"},
        "finance": {"pending_approval"},
        "leadership": {
            "overdue_action",
            "no_owner",
            "stalled",
            "pending_approval",
            "closed_won_not_released",
        },
    }.get(focus, set())
    flag_rank = {
        "overdue_action": 1,
        "pending_approval": 2,
        "closed_won_not_released": 3,
        "no_owner": 4,
        "stalled": 5,
    }
    actions = []
    for row in opportunities:
        flags = [flag for flag in row.attention_flags if not focus_flags or flag in focus_flags]
        if not flags and not row.next_action_open_count:
            continue
        flag = min(flags, key=lambda item: flag_rank.get(item, 99)) if flags else "next_action"
        actions.append(
            {
                "id": str(row.opportunity_id),
                "rank": flag_rank.get(flag, 6),
                "category": flag.replace("_", " ").title(),
                "account": row.client_name or "Unlinked account",
                "title": row.name or row.hubspot_deal_id or "HubSpot deal",
                "detail": row.latest_comment_body or row.stage_label or "Review this record",
                "owner": row.owner_name or row.owner_email,
                "due": row.next_action_min_due.isoformat() if row.next_action_min_due else None,
                "href": f"/deals/{row.opportunity_id}",
                "action": "Open record",
            }
        )
    actions.sort(key=lambda item: (item["rank"], item["due"] or "9999", item["account"]))

    open_rows = [row for row in opportunities if not row.is_closed_won and not row.is_closed_lost]
    pipeline_value = sum(
        (row.amount for row in open_rows if row.currency == currency and row.amount is not None),
        Decimal("0"),
    )
    pipeline_value_known = any(row.currency == currency and row.amount is not None for row in open_rows)
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
    recent = sorted(
        (
            {
                "id": str(row.opportunity_id),
                "account": row.client_name or "Unlinked account",
                "text": row.latest_comment_body or f"{row.name or 'Deal'} is in {row.stage_label or 'an unknown stage'}",
                "at": (row.latest_comment_at or row.hubspot_last_activity_at).isoformat()
                if (row.latest_comment_at or row.hubspot_last_activity_at)
                else None,
                "href": f"/deals/{row.opportunity_id}",
            }
            for row in opportunities
            if row.latest_comment_at or row.hubspot_last_activity_at
        ),
        key=lambda item: item["at"] or "",
        reverse=True,
    )[:8]

    return {
        "scope": {
            "period": period,
            "months": months,
            "currency": currency,
            "focus": focus,
        },
        "actions": actions[:8],
        "metrics": {
            "open_opportunity_value": _decimal_text(pipeline_value) if pipeline_value_known else None,
            "sows_in_progress": sum(1 for row in opportunities if row.sow_approval_state not in {"none", "signed"}),
            "committed_revenue": _decimal_text(signed_revenue) if has_signed_revenue else None,
            "committed_gm_pct": _decimal_text(gm_pct),
            "planned_people": planned_people if financial_rows else None,
        },
        "lifecycle": lifecycle,
        "revenue": {
            "actual": _decimal_text(actual) if has_signed_revenue else None,
            "remaining_signed": _decimal_text(remaining) if has_signed_revenue else None,
            "potential_expected": _decimal_text(potential_expected) if potential_complete else None,
            "potential_upside": _decimal_text(potential_upside),
            "currency": currency,
            "months": [
                {key: _decimal_text(value) if isinstance(value, Decimal) else value for key, value in row.items()}
                for row in monthly.values()
            ],
            "cost_coverage_complete": complete_costs,
            "financial_blockers": sorted(set(financial_blockers)),
        },
        "capacity": {
            "planned_fte": planned_people if financial_rows else None,
            "required_fte": None,
            "available_fte": None,
            "status": "unknown",
            "message": "Required demand and available workforce remain unknown until current publications are present.",
        },
        "recent_changes": recent,
        "sources": [
            {
                "name": "HubSpot pipeline mirror",
                "status": "current" if opportunities else "empty",
                "as_of": latest_hubspot.isoformat() if latest_hubspot else None,
                "detail": f"{len(opportunities)} role-scoped deal(s)",
            },
            {
                "name": "Delivery forecast",
                "status": "current" if financial_rows and complete_costs else "attention",
                "as_of": None,
                "detail": f"{len(financial_rows)} linked engagement calculation(s)",
            },
            {
                "name": "Workforce supply",
                "status": "unknown",
                "as_of": None,
                "detail": "No compatible dated supply evidence in this command scope",
            },
            {
                "name": "Notifications",
                "status": "attention" if failed_notifications else "current",
                "as_of": None,
                "detail": f"{failed_notifications} failed delivery attempt(s)",
                "href": "/settings/system-health",
            },
        ],
        "configuration_gaps": await _configuration_gaps(session),
    }
