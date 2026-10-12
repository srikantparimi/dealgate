"""S22 — the thin layer between the ledger tables and the forecast engine.

DB rows → engine dataclasses → :func:`app.services.forecast.compute` →
``Forecast`` → JSON per docs/reference/openapi-forecast.yaml.

**No arithmetic lives here.** Every hour, every dollar and every percentage
in a response is read off the engine's ``Forecast``; this module only maps
rows to dataclasses, formats Decimals for the wire, aggregates engine rows
(sums of ``AllocationMonth`` lines, exactly as the golden test does) and
asks the engine's own ``MonthLine.gm_pct`` for any margin percentage it
needs on an aggregate. If a number here disagrees with the engine, this
module is wrong (directive S22 §1).

``forecast_run`` caches the serialised ``Forecast`` under a SHA-256 of
every input (engagement row, all allocation rows including superseded
history, costs, calendar). Any change produces a new hash, so a stale run
is never served.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.client import Client
from app.models.engagement import (
    COST_FREQUENCIES,
    EMPLOYMENT_TYPES,
    ENGAGEMENT_TYPES,
    SENIORITIES,
    Allocation,
    CalendarLocation,
    CostRateCard,
    Engagement,
    EngagementCost,
    ForecastPolicy,
    ForecastRun,
    Holiday,
    Resource,
)
from app.models.user import User
from app.services import forecast as engine

HOURLY_TYPES = engine.HOURLY_TYPES
ROLLOFF_WINDOW_DAYS = 60


# ----------------------------------------------------------------------------- errors
class ForecastInputError(HTTPException):
    """422 whose body lists each problem in the user's words (contract: ``body.missing``)."""

    def __init__(self, missing: list[str]):
        super().__init__(status_code=422, detail={"missing": list(missing)})
        self.missing = list(missing)


# ----------------------------------------------------------------------------- clock
def today() -> date:
    """Business ``today``; honours ``DEALGATE_NOW`` like the schedulers do."""

    raw = os.environ.get("DEALGATE_NOW")
    if raw:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    return date.today()


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = (int(part) for part in month.split("-"))
    return date(year, mon, 1), date(year, mon, monthrange(year, mon)[1])


def last_day_of_month(day: date) -> date:
    return date(day.year, day.month, monthrange(day.year, day.month)[1])


# ----------------------------------------------------------------------------- wire formatting
def money(value: Decimal | None) -> str | None:
    """Two-place money string; the quantisation is the engine's own ``money()``."""

    return None if value is None else format(engine.money(value), "f")


def pct(value: Decimal | None) -> float | None:
    return None if value is None else float(round(value, 6))


def num(value: Decimal | None) -> float | None:
    return None if value is None else float(round(value, 6))


def margin_pct(revenue: Decimal, cost: Decimal) -> Decimal | None:
    """GM % of an aggregate (revenue, cost) pair.

    Delegated to the engine's ``MonthLine.gm_pct`` so the margin formula has
    exactly one home (engine README: "margin arithmetic in Forecast is
    simple enough to stay here").
    """

    line = engine.MonthLine("", engine.ZERO, 0, engine.ZERO, revenue, cost, engine.ZERO, engine.ZERO, engine.ZERO)
    return line.gm_pct


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ForecastInputError([f"{value!r} is not a number"]) from exc


# ----------------------------------------------------------------------------- calendar
@dataclass(frozen=True)
class CalendarBundle:
    hours_per_day: Decimal
    project_floor_pct: Decimal
    locations: tuple[CalendarLocation, ...]
    holidays: dict[str, tuple[date, ...]]
    rate_card: dict[tuple[str, str, str], Decimal]  # (seniority, location, employment_type)

    def engine_calendar(self) -> engine.Calendar:
        burden: dict[tuple[str, str], Decimal] = {}
        floors: dict[str, Decimal] = {}
        for loc in self.locations:
            burden[(loc.name, "w2_employee")] = loc.burden_pct_w2
            burden[(loc.name, "contractor_1099")] = loc.burden_pct_1099
            floors[loc.name] = loc.resource_floor_pct
        return engine.Calendar(
            hours_per_day=self.hours_per_day,
            project_floor_pct=self.project_floor_pct,
            burden_pct=burden,
            resource_floor_pct=floors,
            holidays={name: set(days) for name, days in self.holidays.items()},
        )

    def burden_pct(self, location: str, employment_type: str) -> Decimal | None:
        return self.engine_calendar().burden_pct.get((location, employment_type))

    def resource_floor(self, location: str) -> Decimal:
        return self.engine_calendar().resource_floor_pct.get(location, self.project_floor_pct)

    def rate_card_cost(self, seniority: str | None, location: str, employment_type: str) -> Decimal | None:
        if seniority is None:
            return None
        return self.rate_card.get((seniority, location, employment_type))

    def location_names(self) -> list[str]:
        return [loc.name for loc in self.locations]

    def contract(self) -> dict[str, Any]:
        """``Calendar`` schema of the OpenAPI contract (GET /settings/forecast)."""

        return {
            "hours_per_day": num(self.hours_per_day),
            "project_floor_pct": pct(self.project_floor_pct),
            "locations": [
                {
                    "name": loc.name,
                    "burden_pct_w2": pct(loc.burden_pct_w2),
                    "burden_pct_1099": pct(loc.burden_pct_1099),
                    "resource_floor_pct": pct(loc.resource_floor_pct),
                }
                for loc in self.locations
            ],
            "rate_card": [
                {
                    "seniority": seniority,
                    "location": location,
                    "employment_type": employment_type,
                    "cost_per_hour": money(cost),
                }
                for (seniority, location, employment_type), cost in sorted(
                    self.rate_card.items(),
                    key=lambda item: (SENIORITIES.index(item[0][0]) if item[0][0] in SENIORITIES else 99, item[0]),
                )
            ],
            "holidays": {name: [day.isoformat() for day in days] for name, days in self.holidays.items()},
        }

    def fingerprint(self) -> dict[str, Any]:
        return {
            "hours_per_day": str(self.hours_per_day),
            "project_floor_pct": str(self.project_floor_pct),
            "locations": [
                [loc.name, str(loc.burden_pct_w2), str(loc.burden_pct_1099), str(loc.resource_floor_pct)]
                for loc in self.locations
            ],
            "rate_card": sorted([list(key), str(cost)] for key, cost in self.rate_card.items()),
            "holidays": {name: [day.isoformat() for day in days] for name, days in self.holidays.items()},
        }


async def load_calendar(session: AsyncSession) -> CalendarBundle:
    policy = (await session.execute(select(ForecastPolicy).order_by(ForecastPolicy.updated_at.desc()).limit(1))).scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=503, detail="forecast_policy is not seeded — run migrations")
    locations = tuple((await session.execute(select(CalendarLocation).order_by(CalendarLocation.name))).scalars().all())
    by_id = {loc.id: loc.name for loc in locations}
    holidays: dict[str, list[date]] = {loc.name: [] for loc in locations}
    for hol in (await session.execute(select(Holiday).order_by(Holiday.day))).scalars().all():
        name = by_id.get(hol.location_id)
        if name is not None:
            holidays[name].append(hol.day)
    rate_card: dict[tuple[str, str, str], Decimal] = {}
    for cell in (await session.execute(select(CostRateCard))).scalars().all():
        name = by_id.get(cell.location_id)
        if name is not None:
            rate_card[(cell.seniority, name, cell.employment_type)] = cell.cost_per_hour
    return CalendarBundle(
        hours_per_day=policy.hours_per_day,
        project_floor_pct=policy.project_floor_pct,
        locations=locations,
        holidays={name: tuple(days) for name, days in holidays.items()},
        rate_card=rate_card,
    )


async def save_calendar(session: AsyncSession, *, actor: AuthUser, body: dict[str, Any]) -> CalendarBundle:
    """PUT /settings/forecast — replace the calendar, audit it, re-run every active engagement."""

    before = (await load_calendar(session)).contract()
    problems: list[str] = []
    hours = _dec(body.get("hours_per_day"))
    floor = _dec(body.get("project_floor_pct"))
    if hours is None or hours <= 0:
        problems.append("hours per working day must be greater than 0")
    if floor is None or not (Decimal("0") <= floor <= Decimal("1")):
        problems.append("project GM floor must be a fraction between 0 and 1")
    locations_in = body.get("locations") or []
    if not locations_in:
        problems.append("at least one location is required")
    names: list[str] = []
    for loc in locations_in:
        name = (loc.get("name") or "").strip()
        if not name:
            problems.append("every location needs a name")
            continue
        if name in names:
            problems.append(f"{name}: location listed twice")
        names.append(name)
        for key in ("burden_pct_w2", "burden_pct_1099", "resource_floor_pct"):
            value = _dec(loc.get(key))
            if value is None or not (Decimal("0") <= value <= Decimal("1")):
                problems.append(f"{name}: {key.replace('_', ' ')} must be a fraction between 0 and 1")
    for cell in body.get("rate_card") or []:
        if cell.get("location") not in names:
            problems.append(f"rate card: unknown location {cell.get('location')!r}")
        if cell.get("employment_type") not in EMPLOYMENT_TYPES:
            problems.append(f"rate card: unknown employment type {cell.get('employment_type')!r}")
        if _dec(cell.get("cost_per_hour")) is None:
            problems.append(f"rate card: {cell.get('seniority')} × {cell.get('location')} × {cell.get('employment_type')} needs a cost per hour")
    for name, days in (body.get("holidays") or {}).items():
        if name not in names:
            problems.append(f"holidays: unknown location {name!r}")
        for raw in days:
            try:
                date.fromisoformat(str(raw))
            except ValueError:
                problems.append(f"holidays: {name} {raw!r} is not a YYYY-MM-DD date")
    if problems:
        raise ForecastInputError(problems)

    policy = (await session.execute(select(ForecastPolicy).limit(1))).scalar_one_or_none()
    if policy is None:
        policy = ForecastPolicy(id=uuid.uuid4(), hours_per_day=hours, project_floor_pct=floor)
        session.add(policy)
    policy.hours_per_day = hours
    policy.project_floor_pct = floor
    policy.updated_by = actor.id

    existing = {loc.name: loc for loc in (await session.execute(select(CalendarLocation))).scalars().all()}
    kept: dict[str, CalendarLocation] = {}
    for loc in locations_in:
        name = loc["name"].strip()
        row = existing.get(name) or CalendarLocation(id=uuid.uuid4(), name=name)
        row.burden_pct_w2 = _dec(loc["burden_pct_w2"])
        row.burden_pct_1099 = _dec(loc["burden_pct_1099"])
        row.resource_floor_pct = _dec(loc["resource_floor_pct"])
        session.add(row)
        kept[name] = row
    for name, row in existing.items():
        if name not in kept:
            await session.delete(row)
    await session.flush()

    for cell in (await session.execute(select(CostRateCard))).scalars().all():
        await session.delete(cell)
    for hol in (await session.execute(select(Holiday))).scalars().all():
        await session.delete(hol)
    await session.flush()
    seen_cells: set[tuple[str, str, str]] = set()
    for cell in body.get("rate_card") or []:
        key = (cell["seniority"], cell["location"], cell["employment_type"])
        if key in seen_cells:
            continue
        seen_cells.add(key)
        session.add(
            CostRateCard(
                id=uuid.uuid4(),
                seniority=cell["seniority"],
                location_id=kept[cell["location"]].id,
                employment_type=cell["employment_type"],
                cost_per_hour=_dec(cell["cost_per_hour"]),
            )
        )
    for name, days in (body.get("holidays") or {}).items():
        for day in sorted({date.fromisoformat(str(raw)) for raw in days}):
            session.add(Holiday(id=uuid.uuid4(), location_id=kept[name].id, day=day))
    await session.flush()

    bundle = await load_calendar(session)
    await append_audit(
        session,
        actor_id=actor.id,
        action="forecast.settings_updated",
        entity="forecast_policy",
        entity_id=str(policy.id),
        before=before,
        after=bundle.contract(),
    )
    # The contract: changing the calendar creates a new forecast_run for every active engagement.
    now = today()
    active = (
        await session.execute(select(Engagement).where(Engagement.end >= now))
    ).scalars().all()
    for eng in active:
        await forecast_payload(session, eng, bundle=bundle)
    return bundle


# ----------------------------------------------------------------------------- mapper (rows → engine)
def engine_engagement(row: Engagement) -> engine.Engagement:
    return engine.Engagement(
        id=str(row.id),
        type=row.type,
        start=row.start,
        end=row.end,
        total_price=row.total_price,
        monthly_fee=row.monthly_fee,
        same_dates_for_all=row.same_dates_for_all,
        additional_costs_flag=row.additional_costs_flag,
    )


def effective_cost_per_hour(row: Allocation, bundle: CalendarBundle) -> Decimal | None:
    """The value the engine uses: the row's override, else the rate-card cell."""

    if row.cost_per_hour is not None:
        return row.cost_per_hour
    return bundle.rate_card_cost(row.seniority, row.location, row.employment_type)


def engine_allocation(row: Allocation, resource_name: str, bundle: CalendarBundle) -> engine.Allocation:
    cost = effective_cost_per_hour(row, bundle)
    return engine.Allocation(
        id=str(row.id),
        resource=resource_name,
        location=row.location,
        employment_type=row.employment_type,
        cost_per_hour=cost if cost is not None else engine.ZERO,
        assignment=row.assignment or None,
        utilization=row.utilization,
        bill_rate=row.bill_rate,
        start=row.start,
        end=row.end,
        hours_override=row.hours_override,
    )


def engine_cost(row: EngagementCost) -> engine.EngagementCost:
    return engine.EngagementCost(
        description=row.description,
        amount=row.amount,
        frequency=row.frequency,
        billed_to_client=row.billed_to_client,
    )


def effective_window(eng: Engagement, row: Allocation) -> tuple[date, date]:
    """The engine's defaulting rule for a row's dates (same_dates_for_all / NULL = engagement window)."""

    start = eng.start if (eng.same_dates_for_all or row.start is None) else row.start
    end = eng.end if (eng.same_dates_for_all or row.end is None) else row.end
    return start, end


# ----------------------------------------------------------------------------- loading
async def load_engagement(session: AsyncSession, engagement_id: uuid.UUID) -> Engagement:
    row = await session.get(Engagement, engagement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    return row


async def load_allocation(session: AsyncSession, allocation_id: uuid.UUID) -> Allocation:
    row = await session.get(Allocation, allocation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="allocation not found")
    return row


async def allocation_rows(
    session: AsyncSession, engagement_id: uuid.UUID, *, include_superseded: bool
) -> list[tuple[Allocation, Resource]]:
    stmt = (
        select(Allocation, Resource)
        .join(Resource, Resource.id == Allocation.resource_id)
        .where(Allocation.engagement_id == engagement_id)
        .order_by(Allocation.created_at, Allocation.id)
    )
    if not include_superseded:
        stmt = stmt.where(Allocation.superseded_by.is_(None))
    return [(alloc, res) for alloc, res in (await session.execute(stmt)).all()]


async def cost_rows(session: AsyncSession, engagement_id: uuid.UUID) -> list[EngagementCost]:
    stmt = (
        select(EngagementCost)
        .where(EngagementCost.engagement_id == engagement_id)
        .order_by(EngagementCost.created_at, EngagementCost.id)
    )
    return list((await session.execute(stmt)).scalars().all())


# ----------------------------------------------------------------------------- compute + cache
def _input_hash(eng: Engagement, rows: list[tuple[Allocation, Resource]], costs: list[EngagementCost], bundle: CalendarBundle) -> str:
    canonical = {
        "engagement": {
            "type": eng.type,
            "start": eng.start.isoformat(),
            "end": eng.end.isoformat(),
            "total_price": None if eng.total_price is None else str(eng.total_price),
            "monthly_fee": None if eng.monthly_fee is None else str(eng.monthly_fee),
            "same_dates_for_all": eng.same_dates_for_all,
            "additional_costs_flag": eng.additional_costs_flag,
        },
        "allocations": sorted(
            [
                str(alloc.id),
                res.name,
                alloc.location,
                alloc.employment_type,
                alloc.seniority or "",
                alloc.assignment or "",
                str(alloc.utilization),
                None if alloc.bill_rate is None else str(alloc.bill_rate),
                None if alloc.cost_per_hour is None else str(alloc.cost_per_hour),
                None if alloc.start is None else alloc.start.isoformat(),
                None if alloc.end is None else alloc.end.isoformat(),
                None if alloc.hours_override is None else str(alloc.hours_override),
            ]
            for alloc, res in rows
        ),
        "costs": sorted(
            [cost.description, str(cost.amount), cost.frequency, cost.billed_to_client] for cost in costs
        ),
        "calendar": bundle.fingerprint(),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()


def compute_forecast(
    eng: Engagement, rows: list[tuple[Allocation, Resource]], costs: list[EngagementCost], bundle: CalendarBundle
) -> engine.Forecast:
    return engine.compute(
        engine_engagement(eng),
        [engine_allocation(alloc, res.name, bundle) for alloc, res in rows],
        [engine_cost(cost) for cost in costs],
        bundle.engine_calendar(),
    )


def _staffing_totals(forecast: engine.Forecast) -> dict[str, Any]:
    """Footer of the allocations grid — the same sums the golden test performs over AllocationMonth rows."""

    hours = sum((am.hours for am in forecast.allocation_months), engine.ZERO)
    revenue = sum((am.revenue for am in forecast.allocation_months), engine.ZERO)
    loaded = sum((am.loaded_cost for am in forecast.allocation_months), engine.ZERO)
    return {
        "hours": num(hours),
        "revenue": money(revenue),
        "loaded_cost": money(loaded),
        "gm_pct": pct(margin_pct(revenue, loaded)),
    }


def _assignment_totals(months: dict[str, dict[str, Any]]) -> dict[str, Any]:
    hours = sum((line["hours"] for line in months.values()), engine.ZERO)
    revenue = sum((line["revenue"] for line in months.values()), engine.ZERO)
    loaded = sum((line["loaded_cost"] for line in months.values()), engine.ZERO)
    return {
        "people": max((line["people"] for line in months.values()), default=0),
        "hours": num(hours),
        "revenue": money(revenue),
        "loaded_cost": money(loaded),
        "gm_pct": pct(margin_pct(revenue, loaded)),
    }


def serialize_forecast(forecast: engine.Forecast, resource_names: dict[str, str], project_floor_pct: Decimal) -> dict[str, Any]:
    """The ``Forecast`` schema of the contract — a serialisation of the engine's result and nothing else."""

    return {
        "engagement_id": forecast.engagement_id,
        "duration_months": num(forecast.duration_months),
        "status": forecast.status,
        "project_floor_pct": pct(project_floor_pct),
        "monthly_required": forecast.monthly_required,
        "missing": list(forecast.missing),
        "totals": {
            "hours": num(forecast.hours),
            "labour_cost": money(forecast.labour_cost),
            "burden_cost": money(forecast.burden_cost),
            # loaded cost = labour + burden, the engine's AllocationMonth.loaded_cost definition
            "loaded_cost": money(forecast.labour_cost + forecast.burden_cost),
            "additional_costs": money(forecast.additional_costs),
            "pass_through_revenue": money(forecast.pass_through_revenue),
            "total_revenue": money(forecast.total_revenue),
            "total_cost": money(forecast.total_cost),
            # gm $ = total revenue − total cost, the engine's MonthLine.gm definition
            "gm": money(forecast.total_revenue - forecast.total_cost),
            "gm_pct": pct(forecast.gm_pct),
        },
        # The allocations grid footer: sums of the engine's AllocationMonth rows (labour revenue, loaded cost).
        "staffing_totals": _staffing_totals(forecast),
        "months": [
            {
                "month": line.month,
                "share_of_month": num(line.share_of_month),
                "people": line.people,
                "hours": num(line.hours),
                "revenue": money(line.revenue),
                "labour_cost": money(line.labour_cost),
                "burden_cost": money(line.burden_cost),
                "loaded_cost": money(line.labour_cost + line.burden_cost),
                "additional_costs": money(line.additional_costs),
                "pass_through_revenue": money(line.pass_through_revenue),
                "total_revenue": money(line.total_revenue),
                "total_cost": money(line.total_cost),
                "gm": money(line.gm),
                "gm_pct": pct(line.gm_pct),
            }
            for line in forecast.months
        ],
        "by_assignment_totals": {
            assignment: _assignment_totals(months) for assignment, months in sorted(forecast.by_assignment.items())
        },
        "by_assignment": {
            assignment: {
                month: {
                    "people": line["people"],
                    "hours": num(line["hours"]),
                    "revenue": money(line["revenue"]),
                    "loaded_cost": money(line["loaded_cost"]),
                    "gm_pct": pct(margin_pct(line["revenue"], line["loaded_cost"])),
                }
                for month, line in sorted(months.items())
            }
            for assignment, months in sorted(forecast.by_assignment.items())
        },
        "allocation_months": [
            {
                "allocation_id": am.allocation_id,
                "resource_name": resource_names.get(am.allocation_id, ""),
                "assignment": am.assignment,
                "month": am.month,
                "working_days": am.working_days,
                "hours": num(am.hours),
                "revenue": money(am.revenue),
                "loaded_cost": money(am.loaded_cost),
            }
            for am in forecast.allocation_months
        ],
        "location_check": {
            location: {
                "revenue": money(check["revenue"]),
                "loaded_cost": money(check["loaded_cost"]),
                "gm_pct": pct(check["gm_pct"]),
                "floor": pct(check["floor"]),
                "ok": bool(check["ok"]),
            }
            for location, check in forecast.location_check.items()
        },
    }


async def forecast_payload(
    session: AsyncSession, eng: Engagement, *, bundle: CalendarBundle | None = None, store: bool = True
) -> dict[str, Any]:
    """GET /engagements/{id}/forecast: cached by input hash, else compute + store a ``forecast_run``."""

    bundle = bundle or await load_calendar(session)
    rows = await allocation_rows(session, eng.id, include_superseded=True)
    costs = await cost_rows(session, eng.id)
    digest = _input_hash(eng, rows, costs, bundle)
    cached = (
        await session.execute(
            select(ForecastRun)
            .where(ForecastRun.engagement_id == eng.id, ForecastRun.input_hash == digest)
            .order_by(ForecastRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if cached is not None:
        return cached.payload
    forecast = compute_forecast(eng, rows, costs, bundle)
    payload = serialize_forecast(forecast, {str(alloc.id): res.name for alloc, res in rows}, bundle.project_floor_pct)
    if store:
        session.add(ForecastRun(id=uuid.uuid4(), engagement_id=eng.id, input_hash=digest, payload=payload))
        await session.flush()
    return payload


# ----------------------------------------------------------------------------- engagements
def engagement_status(row: Engagement, on: date | None = None) -> str:
    on = on or today()
    if row.end < on:
        return "ended"
    if row.start > on:
        return "draft"
    return "active"


def _status_case(on: date):
    return case(
        (Engagement.end < on, "ended"),
        (Engagement.start > on, "draft"),
        else_="active",
    )


def serialize_engagement(row: Engagement, client_name: str, owner_name: str | None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": client_name,
        "hubspot_deal_id": row.hubspot_deal_id,
        "opportunity_id": None if row.opportunity_id is None else str(row.opportunity_id),
        "name": row.name,
        "type": row.type,
        "start": row.start.isoformat(),
        "end": row.end.isoformat(),
        "total_price": money(row.total_price),
        "monthly_fee": money(row.monthly_fee),
        "currency": row.currency,
        "additional_costs_flag": row.additional_costs_flag,
        "same_dates_for_all": row.same_dates_for_all,
        "owner_user_id": None if row.owner_user_id is None else str(row.owner_user_id),
        "owner_name": owner_name,
        "status": engagement_status(row),
        "duration_months": num(engine.duration_months(row.start, row.end)),
    }


async def engagement_detail(session: AsyncSession, row: Engagement) -> dict[str, Any]:
    client = await session.get(Client, row.client_id)
    owner = await session.get(User, row.owner_user_id) if row.owner_user_id else None
    return serialize_engagement(row, client.name if client else "", owner.name if owner else None)


async def list_engagements(
    session: AsyncSession,
    *,
    client_id: uuid.UUID | None,
    type_: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[int, list[dict[str, Any]]]:
    """Single query service: filters, total before pagination, then the page."""

    on = today()
    conditions = []
    if client_id is not None:
        conditions.append(Engagement.client_id == client_id)
    if type_:
        conditions.append(Engagement.type == type_)
    if status:
        conditions.append(_status_case(on) == status)
    total = (
        await session.execute(select(func.count()).select_from(Engagement).where(*conditions))
    ).scalar_one()
    page_stmt = (
        select(Engagement, Client.name, User.name)
        .join(Client, Client.id == Engagement.client_id)
        .join(User, User.id == Engagement.owner_user_id, isouter=True)
        .where(*conditions)
        .order_by(Engagement.start.desc(), Engagement.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        serialize_engagement(row, client_name, owner_name)
        for row, client_name, owner_name in (await session.execute(page_stmt)).all()
    ]
    return total, items


def _validate_engagement(eng: Engagement, bundle: CalendarBundle) -> None:
    """422 with the engine's own ``missing`` strings for the project block."""

    missing = engine.compute(engine_engagement(eng), [], [], bundle.engine_calendar()).missing
    if missing:
        raise ForecastInputError(missing)


def _engagement_snapshot(row: Engagement) -> dict[str, Any]:
    return {
        "client_id": str(row.client_id),
        "hubspot_deal_id": row.hubspot_deal_id,
        "opportunity_id": None if row.opportunity_id is None else str(row.opportunity_id),
        "name": row.name,
        "type": row.type,
        "start": row.start.isoformat(),
        "end": row.end.isoformat(),
        "total_price": None if row.total_price is None else str(row.total_price),
        "monthly_fee": None if row.monthly_fee is None else str(row.monthly_fee),
        "currency": row.currency,
        "additional_costs_flag": row.additional_costs_flag,
        "same_dates_for_all": row.same_dates_for_all,
        "owner_user_id": None if row.owner_user_id is None else str(row.owner_user_id),
    }


async def create_engagement(session: AsyncSession, *, actor: AuthUser, body: dict[str, Any]) -> Engagement:
    client = await session.get(Client, body["client_id"])
    if client is None:
        raise ForecastInputError(["client not found"])
    if body["type"] not in ENGAGEMENT_TYPES:
        raise ForecastInputError([f"unknown engagement type {body['type']!r}"])
    opportunity_id = body.get("opportunity_id")
    row = Engagement(
        id=uuid.uuid4(),
        client_id=client.id,
        opportunity_id=opportunity_id,
        hubspot_deal_id=body.get("hubspot_deal_id"),
        name=body["name"].strip(),
        type=body["type"],
        start=body["start"],
        end=body["end"],
        total_price=_dec(body.get("total_price")),
        monthly_fee=_dec(body.get("monthly_fee")),
        currency=(body.get("currency") or "USD").upper(),
        additional_costs_flag=bool(body["additional_costs_flag"]),
        same_dates_for_all=bool(body["same_dates_for_all"]),
        owner_user_id=body.get("owner_user_id"),
        created_by=actor.id,
    )
    if not row.name:
        raise ForecastInputError(["engagement name is required"])
    bundle = await load_calendar(session)
    _validate_engagement(row, bundle)
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="engagement.created",
        entity="engagement",
        entity_id=str(row.id),
        before=None,
        after=_engagement_snapshot(row),
    )
    return row


async def update_engagement(session: AsyncSession, *, actor: AuthUser, row: Engagement, body: dict[str, Any]) -> Engagement:
    before = _engagement_snapshot(row)
    if "client_id" in body and body["client_id"] is not None:
        if await session.get(Client, body["client_id"]) is None:
            raise ForecastInputError(["client not found"])
        row.client_id = body["client_id"]
    for key in ("hubspot_deal_id", "opportunity_id", "owner_user_id"):
        if key in body:
            setattr(row, key, body[key])
    if body.get("name") is not None:
        row.name = body["name"].strip()
    if body.get("type") is not None:
        if body["type"] not in ENGAGEMENT_TYPES:
            raise ForecastInputError([f"unknown engagement type {body['type']!r}"])
        row.type = body["type"]
    for key in ("start", "end"):
        if body.get(key) is not None:
            setattr(row, key, body[key])
    for key in ("total_price", "monthly_fee"):
        if key in body:
            setattr(row, key, _dec(body[key]))
    if body.get("currency"):
        row.currency = body["currency"].upper()
    for key in ("additional_costs_flag", "same_dates_for_all"):
        if body.get(key) is not None:
            setattr(row, key, bool(body[key]))
    bundle = await load_calendar(session)
    _validate_engagement(row, bundle)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="engagement.updated",
        entity="engagement",
        entity_id=str(row.id),
        before=before,
        after=_engagement_snapshot(row),
    )
    return row


# ----------------------------------------------------------------------------- resources + clients
async def list_resources(session: AsyncSession, *, active_only: bool = True) -> list[Resource]:
    stmt = select(Resource).order_by(Resource.name)
    if active_only:
        stmt = stmt.where(Resource.active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


def serialize_resource(row: Resource) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "location": row.location,
        "employment_type": row.employment_type,
        "seniority": row.seniority,
        "email": row.email,
        "active": row.active,
    }


async def create_resource(session: AsyncSession, *, actor: AuthUser, body: dict[str, Any], bundle: CalendarBundle | None = None) -> Resource:
    bundle = bundle or await load_calendar(session)
    problems: list[str] = []
    name = (body.get("name") or "").strip()
    if not name:
        problems.append("person name is required")
    if body.get("location") not in bundle.location_names():
        problems.append(f"{name or 'person'}: unknown location {body.get('location')!r}")
    if body.get("employment_type") not in EMPLOYMENT_TYPES:
        problems.append(f"{name or 'person'}: unknown employment type")
    if body.get("seniority") is not None and body["seniority"] not in SENIORITIES:
        problems.append(f"{name or 'person'}: seniority must be one of {', '.join(SENIORITIES)}")
    if problems:
        raise ForecastInputError(problems)
    row = Resource(
        id=uuid.uuid4(),
        name=name,
        location=body["location"],
        employment_type=body["employment_type"],
        seniority=body.get("seniority"),
        email=(body.get("email") or None),
        active=True,
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="resource.created",
        entity="resource",
        entity_id=str(row.id),
        before=None,
        after=serialize_resource(row),
    )
    return row


async def load_resource(session: AsyncSession, resource_id: uuid.UUID) -> Resource:
    row = await session.get(Resource, resource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="person not found")
    return row


async def delete_resource(session: AsyncSession, *, actor: AuthUser, row: Resource) -> None:
    allocated = await session.scalar(
        select(func.count()).select_from(Allocation).where(Allocation.resource_id == row.id)
    )
    if allocated:
        raise HTTPException(status_code=409, detail="person still has allocations — close or remove those first")
    before = serialize_resource(row)
    await session.delete(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="resource.removed",
        entity="resource",
        entity_id=str(row.id),
        before=before,
        after=None,
    )


async def create_manual_client(session: AsyncSession, *, actor: AuthUser, name: str) -> Client:
    """POST /clients — a client by name when no HubSpot company matches (never a mirror row)."""

    name = name.strip()
    if not name:
        raise ForecastInputError(["client name is required"])
    existing = (
        await session.execute(select(Client).where(func.lower(Client.name) == name.lower()).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Client(id=uuid.uuid4(), name=name, hubspot_company_id=None)
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="client.created",
        entity="client",
        entity_id=str(row.id),
        before=None,
        after={"name": name, "source": "manual"},
    )
    return row


def client_source(row: Client) -> str:
    return "hubspot" if row.hubspot_company_id else "manual"


# ----------------------------------------------------------------------------- allocations
def _allocation_snapshot(row: Allocation) -> dict[str, Any]:
    return {
        "engagement_id": str(row.engagement_id),
        "resource_id": str(row.resource_id),
        "role": row.role,
        "seniority": row.seniority,
        "location": row.location,
        "employment_type": row.employment_type,
        "assignment": row.assignment,
        "utilization": str(row.utilization),
        "bill_rate": None if row.bill_rate is None else str(row.bill_rate),
        "cost_per_hour": None if row.cost_per_hour is None else str(row.cost_per_hour),
        "start": None if row.start is None else row.start.isoformat(),
        "end": None if row.end is None else row.end.isoformat(),
        "hours_override": None if row.hours_override is None else str(row.hours_override),
        "superseded_by": None if row.superseded_by is None else str(row.superseded_by),
    }


def _own_problems(eng: Engagement, row: Allocation, resource_name: str, bundle: CalendarBundle) -> list[str]:
    """The engine's ``missing`` strings that this row alone introduces."""

    cal = bundle.engine_calendar()
    base = set(engine.compute(engine_engagement(eng), [], [], cal).missing)
    with_row = engine.compute(engine_engagement(eng), [engine_allocation(row, resource_name, bundle)], [], cal).missing
    problems = [message for message in with_row if message not in base]
    if row.cost_per_hour is None and bundle.rate_card_cost(row.seniority, row.location, row.employment_type) is None:
        problems.append(
            f"{resource_name}: cost per hour required — no rate card cell for "
            f"{row.seniority or 'unknown seniority'} × {row.location} × {row.employment_type}"
        )
    if row.location not in bundle.location_names():
        problems.append(f"{resource_name}: unknown location {row.location!r} — add it on the Settings page")
    return problems


def _apply_allocation_fields(row: Allocation, body: dict[str, Any], resource: Resource) -> None:
    if "role" in body and body["role"] is not None:
        row.role = body["role"].strip() or row.role
    if "seniority" in body:
        row.seniority = body["seniority"] if body["seniority"] else None
    if body.get("location"):
        row.location = body["location"]
    if body.get("employment_type"):
        row.employment_type = body["employment_type"]
    if "assignment" in body:
        row.assignment = (body["assignment"] or "").strip() or None
    if body.get("utilization") is not None:
        row.utilization = _dec(body["utilization"])
    if "bill_rate" in body:
        row.bill_rate = _dec(body["bill_rate"])
    if "cost_per_hour" in body:
        row.cost_per_hour = _dec(body["cost_per_hour"])
    if "start" in body:
        row.start = body["start"]
    if "end" in body:
        row.end = body["end"]
    if "hours_override" in body:
        row.hours_override = _dec(body["hours_override"])


async def add_allocation(session: AsyncSession, *, actor: AuthUser, eng: Engagement, body: dict[str, Any]) -> Allocation:
    resource = await session.get(Resource, body["resource_id"])
    if resource is None:
        raise ForecastInputError(["person not found — pick an existing person or add one first"])
    bundle = await load_calendar(session)
    row = Allocation(
        id=uuid.uuid4(),
        engagement_id=eng.id,
        resource_id=resource.id,
        role=(body.get("role") or resource.name).strip(),
        seniority=body.get("seniority") or resource.seniority,
        location=body.get("location") or resource.location,
        employment_type=body.get("employment_type") or resource.employment_type,
        assignment=(body.get("assignment") or "").strip() or None,
        utilization=_dec(body.get("utilization")) if body.get("utilization") is not None else Decimal("1"),
        bill_rate=_dec(body.get("bill_rate")),
        cost_per_hour=_dec(body.get("cost_per_hour")),
        start=body.get("start"),
        end=body.get("end"),
        hours_override=_dec(body.get("hours_override")),
    )
    problems = _own_problems(eng, row, resource.name, bundle)
    if problems:
        raise ForecastInputError(problems)
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="allocation.created",
        entity="allocation",
        entity_id=str(row.id),
        before=None,
        after=_allocation_snapshot(row),
    )
    return row


async def patch_allocation(session: AsyncSession, *, actor: AuthUser, row: Allocation, body: dict[str, Any]) -> Allocation:
    """Edit an open row. A rate change after the row has started supersedes it (new row from today)."""

    if row.superseded_by is not None:
        raise HTTPException(status_code=409, detail="row was superseded — edit the current row")
    eng = await load_engagement(session, row.engagement_id)
    resource = await session.get(Resource, row.resource_id)
    bundle = await load_calendar(session)
    now = today()
    start, end = effective_window(eng, row)
    rate_changed = any(
        key in body and _dec(body[key]) != getattr(row, key) for key in ("bill_rate", "cost_per_hour")
    )
    started = start < now <= end
    before = _allocation_snapshot(row)
    if rate_changed and started:
        successor = Allocation(
            id=uuid.uuid4(),
            engagement_id=row.engagement_id,
            resource_id=row.resource_id,
            role=row.role,
            seniority=row.seniority,
            location=row.location,
            employment_type=row.employment_type,
            assignment=row.assignment,
            utilization=row.utilization,
            bill_rate=row.bill_rate,
            cost_per_hour=row.cost_per_hour,
            start=now,
            end=row.end,
            hours_override=row.hours_override,
        )
        _apply_allocation_fields(successor, {k: v for k, v in body.items() if k not in ("start",)}, resource)
        successor.start = now
        problems = _own_problems(eng, successor, resource.name, bundle)
        if problems:
            raise ForecastInputError(problems)
        session.add(successor)
        await session.flush()
        row.end = now - timedelta(days=1)
        row.superseded_by = successor.id
        if eng.same_dates_for_all:
            eng.same_dates_for_all = False
        await session.flush()
        await append_audit(
            session,
            actor_id=actor.id,
            action="allocation.superseded",
            entity="allocation",
            entity_id=str(row.id),
            before=before,
            after={"superseded_by": str(successor.id), "closed_at": row.end.isoformat(), "successor": _allocation_snapshot(successor)},
        )
        return successor

    _apply_allocation_fields(row, body, resource)
    problems = _own_problems(eng, row, resource.name, bundle)
    if problems:
        raise ForecastInputError(problems)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="allocation.updated",
        entity="allocation",
        entity_id=str(row.id),
        before=before,
        after=_allocation_snapshot(row),
    )
    return row


async def close_allocation(session: AsyncSession, *, actor: AuthUser, row: Allocation, end: date | None) -> Allocation:
    """Leaver: set the end date (default = last day of the current month)."""

    eng = await load_engagement(session, row.engagement_id)
    before = _allocation_snapshot(row)
    start, _ = effective_window(eng, row)
    new_end = end or last_day_of_month(today())
    if new_end < start:
        raise ForecastInputError([f"{row.role}: end before start"])
    row.end = new_end
    if eng.same_dates_for_all:
        # The prototype's rule: a leaver turns "same dates for everyone" off, otherwise row dates are ignored.
        eng.same_dates_for_all = False
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="allocation.closed",
        entity="allocation",
        entity_id=str(row.id),
        before=before,
        after=_allocation_snapshot(row),
    )
    return row


async def rehire_allocation(
    session: AsyncSession,
    *,
    actor: AuthUser,
    row: Allocation,
    start: date | None,
    bill_rate: Any = None,
    cost_per_hour: Any = None,
) -> Allocation:
    """Re-hire / extension: copy the row as a new allocation from the day after the old end."""

    eng = await load_engagement(session, row.engagement_id)
    resource = await session.get(Resource, row.resource_id)
    bundle = await load_calendar(session)
    _, old_end = effective_window(eng, row)
    new_start = start or (old_end + timedelta(days=1))
    successor = Allocation(
        id=uuid.uuid4(),
        engagement_id=row.engagement_id,
        resource_id=row.resource_id,
        role=row.role,
        seniority=row.seniority,
        location=row.location,
        employment_type=row.employment_type,
        assignment=row.assignment,
        utilization=row.utilization,
        bill_rate=_dec(bill_rate) if bill_rate is not None else row.bill_rate,
        cost_per_hour=_dec(cost_per_hour) if cost_per_hour is not None else row.cost_per_hour,
        start=new_start,
        end=None,
        hours_override=None,
    )
    if new_start > eng.end:
        raise ForecastInputError([f"{row.role}: re-hire start {new_start.isoformat()} is after the engagement end {eng.end.isoformat()}"])
    problems = _own_problems(eng, successor, resource.name, bundle)
    if problems:
        raise ForecastInputError(problems)
    session.add(successor)
    if eng.same_dates_for_all:
        eng.same_dates_for_all = False
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="allocation.rehired",
        entity="allocation",
        entity_id=str(successor.id),
        before={"from_allocation": str(row.id)},
        after=_allocation_snapshot(successor),
    )
    return successor


async def delete_allocation(session: AsyncSession, *, actor: AuthUser, row: Allocation) -> None:
    """Remove a row that never started; a started row is closed instead (409)."""

    eng = await load_engagement(session, row.engagement_id)
    start, _ = effective_window(eng, row)
    if start <= today():
        raise HTTPException(status_code=409, detail="Row has started — use /close")
    before = _allocation_snapshot(row)
    await session.delete(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="allocation.removed",
        entity="allocation",
        entity_id=str(row.id),
        before=before,
        after=None,
    )


def serialize_allocation(
    eng: Engagement,
    row: Allocation,
    resource: Resource,
    forecast: dict[str, Any],
    bundle: CalendarBundle,
) -> dict[str, Any]:
    """``Allocation`` schema: the row plus this row's share of the engine's allocation_months."""

    start, end = effective_window(eng, row)
    mine = [am for am in forecast["allocation_months"] if am["allocation_id"] == str(row.id)]
    working_days = sum(am["working_days"] for am in mine)
    hours = sum((Decimal(str(am["hours"])) for am in mine), engine.ZERO)
    revenue = sum((Decimal(am["revenue"]) for am in mine), engine.ZERO)
    loaded_cost = sum((Decimal(am["loaded_cost"]) for am in mine), engine.ZERO)
    hourly = eng.type in HOURLY_TYPES
    row_gm = margin_pct(revenue, loaded_cost) if hourly else None
    floor = bundle.resource_floor(row.location)
    return {
        "id": str(row.id),
        "engagement_id": str(row.engagement_id),
        "resource_id": str(row.resource_id),
        "resource_name": resource.name,
        "role": row.role,
        "seniority": row.seniority,
        "location": row.location,
        "employment_type": row.employment_type,
        "assignment": row.assignment,
        "utilization": num(row.utilization),
        "bill_rate": money(row.bill_rate),
        "cost_per_hour": money(row.cost_per_hour),
        "cost_per_hour_effective": money(effective_cost_per_hour(row, bundle)),
        "burden_pct": pct(bundle.burden_pct(row.location, row.employment_type)),
        "start": None if row.start is None else row.start.isoformat(),
        "end": None if row.end is None else row.end.isoformat(),
        "effective_start": start.isoformat(),
        "effective_end": end.isoformat(),
        "hours_override": num(row.hours_override),
        "superseded_by": None if row.superseded_by is None else str(row.superseded_by),
        "totals": {
            "working_days": working_days,
            "hours": num(hours),
            "revenue": money(revenue),
            "loaded_cost": money(loaded_cost),
            "row_gm_pct": pct(row_gm),
            "under_resource_floor": bool(hourly and row_gm is not None and row_gm < floor),
        },
    }


async def list_allocations(session: AsyncSession, eng: Engagement) -> list[dict[str, Any]]:
    bundle = await load_calendar(session)
    forecast = await forecast_payload(session, eng, bundle=bundle)
    rows = await allocation_rows(session, eng.id, include_superseded=False)
    return [serialize_allocation(eng, alloc, res, forecast, bundle) for alloc, res in rows]


async def allocation_detail(session: AsyncSession, row: Allocation) -> dict[str, Any]:
    eng = await load_engagement(session, row.engagement_id)
    resource = await session.get(Resource, row.resource_id)
    bundle = await load_calendar(session)
    forecast = await forecast_payload(session, eng, bundle=bundle)
    return serialize_allocation(eng, row, resource, forecast, bundle)


# ----------------------------------------------------------------------------- costs
def serialize_cost(row: EngagementCost) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "engagement_id": str(row.engagement_id),
        "description": row.description,
        "category": row.category,
        "location": row.location,
        "amount": money(row.amount),
        "frequency": row.frequency,
        "billed_to_client": row.billed_to_client,
    }


async def add_cost(session: AsyncSession, *, actor: AuthUser, eng: Engagement, body: dict[str, Any]) -> EngagementCost:
    problems: list[str] = []
    description = (body.get("description") or "").strip()
    if not description:
        problems.append("cost description is required")
    amount = _dec(body.get("amount"))
    if amount is None or amount < 0:
        problems.append(f"{description or 'cost'}: amount is required")
    frequency = body.get("frequency") or "one_time"
    if frequency not in COST_FREQUENCIES:
        problems.append(f"{description or 'cost'}: frequency must be one_time or monthly")
    if body.get("billed_to_client") is None:
        problems.append(f"{description or 'cost'}: billed to client Y/N is required")
    if problems:
        raise ForecastInputError(problems)
    row = EngagementCost(
        id=uuid.uuid4(),
        engagement_id=eng.id,
        description=description,
        category=body.get("category"),
        location=body.get("location"),
        amount=amount,
        frequency=frequency,
        billed_to_client=bool(body["billed_to_client"]),
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="engagement_cost.created",
        entity="engagement_cost",
        entity_id=str(row.id),
        before=None,
        after=serialize_cost(row),
    )
    return row


async def update_cost(session: AsyncSession, *, actor: AuthUser, row: EngagementCost, body: dict[str, Any]) -> EngagementCost:
    before = serialize_cost(row)
    problems: list[str] = []
    if "description" in body and body["description"] is not None:
        row.description = body["description"].strip() or row.description
    for key in ("category", "location"):
        if key in body:
            setattr(row, key, body[key] or None)
    if "amount" in body and body["amount"] is not None:
        amount = _dec(body["amount"])
        if amount is None or amount < 0:
            problems.append(f"{row.description}: amount is required")
        else:
            row.amount = amount
    if body.get("frequency") is not None:
        if body["frequency"] not in COST_FREQUENCIES:
            problems.append(f"{row.description}: frequency must be one_time or monthly")
        else:
            row.frequency = body["frequency"]
    if body.get("billed_to_client") is not None:
        row.billed_to_client = bool(body["billed_to_client"])
    if problems:
        raise ForecastInputError(problems)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="engagement_cost.updated",
        entity="engagement_cost",
        entity_id=str(row.id),
        before=before,
        after=serialize_cost(row),
    )
    return row


async def delete_cost(session: AsyncSession, *, actor: AuthUser, row: EngagementCost) -> None:
    before = serialize_cost(row)
    await session.delete(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="engagement_cost.removed",
        entity="engagement_cost",
        entity_id=str(row.id),
        before=before,
        after=None,
    )


# ----------------------------------------------------------------------------- portfolio (single query service)
async def portfolio_month(
    session: AsyncSession,
    *,
    month: str,
    type_: str | None = None,
    client_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """GET /portfolio/forecast — every engagement for one month plus the four cards.

    One pass produces the rows, the totals, the roll-off list and the bench
    list; each card is the count (or total) of the list it opens, so the
    numbers cannot disagree.
    """

    month_start, month_end = month_bounds(month)
    bundle = await load_calendar(session)
    stmt = (
        select(Engagement, Client.name)
        .join(Client, Client.id == Engagement.client_id)
        .where(Engagement.start <= month_end, Engagement.end >= month_start)
        .order_by(Client.name, Engagement.name)
    )
    if type_:
        stmt = stmt.where(Engagement.type == type_)
    if client_id is not None:
        stmt = stmt.where(Engagement.client_id == client_id)
    engagements = (await session.execute(stmt)).all()

    rows: list[dict[str, Any]] = []
    people_total = 0
    revenue_total = engine.ZERO
    cost_total = engine.ZERO
    below_floor = 0
    for eng, client_name in engagements:
        payload = await forecast_payload(session, eng, bundle=bundle)
        line = next((m for m in payload["months"] if m["month"] == month), None)
        if line is None:
            continue
        if payload["status"] == "BELOW FLOOR":
            below_floor += 1
        people_total += line["people"]
        revenue_total += Decimal(line["total_revenue"])
        cost_total += Decimal(line["total_cost"])
        rows.append(
            {
                "engagement_id": str(eng.id),
                "client_name": client_name,
                "name": eng.name,
                "type": eng.type,
                "start": eng.start.isoformat(),
                "end": eng.end.isoformat(),
                "people": line["people"],
                "revenue_month": line["total_revenue"],
                "cost_month": line["total_cost"],
                "gm_pct_month": line["gm_pct"],
                "gm_pct_term": payload["totals"]["gm_pct"],
                "status": payload["status"],
            }
        )

    rolloffs = await rolloffs_from(session, month_start, engagement_ids={uuid.UUID(r["engagement_id"]) for r in rows})
    bench = await _bench(session, month_start, month_end)
    portfolio_gm = margin_pct(revenue_total, cost_total)
    return {
        "month": month,
        "project_floor_pct": pct(bundle.project_floor_pct),
        "cards": {
            "portfolio_gm_pct": pct(portfolio_gm),
            "below_floor": below_floor,
            "rolloffs_60d": len(rolloffs),
            "bench": len(bench),
        },
        "rows": rows,
        "totals": {
            "people": people_total,
            "revenue": money(revenue_total),
            "cost": money(cost_total),
            "gm_pct": pct(portfolio_gm),
        },
        "rolloffs": rolloffs,
        "bench_list": bench,
    }


async def _current_allocations_with_context(session: AsyncSession) -> list[tuple[Allocation, Resource, Engagement, str]]:
    stmt = (
        select(Allocation, Resource, Engagement, Client.name)
        .join(Resource, Resource.id == Allocation.resource_id)
        .join(Engagement, Engagement.id == Allocation.engagement_id)
        .join(Client, Client.id == Engagement.client_id)
        .where(Allocation.superseded_by.is_(None))
    )
    return [tuple(r) for r in (await session.execute(stmt)).all()]


async def rolloffs_from(session: AsyncSession, month_start: date, *, engagement_ids: set[uuid.UUID]) -> list[dict[str, Any]]:
    """Allocations ending within 60 days of the month start with no later allocation for the same resource."""

    cutoff = month_start + timedelta(days=ROLLOFF_WINDOW_DAYS)
    rows = await _current_allocations_with_context(session)
    windows = [(alloc, res, eng, client, *effective_window(eng, alloc)) for alloc, res, eng, client in rows]
    out: list[dict[str, Any]] = []
    for alloc, res, eng, client, start, end in windows:
        if eng.id not in engagement_ids or not (month_start <= end <= cutoff):
            continue
        later = any(
            other_res.id == res.id and other_start > end
            for _, other_res, _, _, other_start, _ in windows
        )
        if later:
            continue
        out.append(
            {
                "engagement_id": str(eng.id),
                "engagement": eng.name,
                "allocation_id": str(alloc.id),
                "client": client,
                "resource": res.name,
                "role": alloc.role,
                "assignment": alloc.assignment,
                "end": end.isoformat(),
            }
        )
    out.sort(key=lambda r: (r["end"], r["client"], r["resource"]))
    return out


async def _bench(session: AsyncSession, month_start: date, month_end: date) -> list[dict[str, Any]]:
    """Active resources with no allocation in the month; free_from = day after their last earlier allocation."""

    resources = await list_resources(session, active_only=True)
    rows = await _current_allocations_with_context(session)
    windows_by_resource: dict[uuid.UUID, list[tuple[date, date]]] = {}
    for alloc, res, eng, _ in rows:
        windows_by_resource.setdefault(res.id, []).append(effective_window(eng, alloc))
    out: list[dict[str, Any]] = []
    for res in resources:
        windows = windows_by_resource.get(res.id, [])
        if any(start <= month_end and end >= month_start for start, end in windows):
            continue
        earlier = [end for _, end in windows if end < month_start]
        free_from = (max(earlier) + timedelta(days=1)) if earlier else month_start
        out.append(
            {
                "resource_id": str(res.id),
                "resource": res.name,
                "location": res.location,
                "employment_type": res.employment_type,
                "seniority": res.seniority,
                "free_from": free_from.isoformat(),
            }
        )
    return out


def portfolio_csv(view: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["Client", "Engagement", "Type", "Start", "End", "People", "Revenue · month", "Cost · month", "GM % · month", "GM % · term", "Status"]
    )
    for row in view["rows"]:
        writer.writerow(
            [
                row["client_name"], row["name"], row["type"], row["start"], row["end"], row["people"],
                row["revenue_month"], row["cost_month"],
                "" if row["gm_pct_month"] is None else row["gm_pct_month"],
                "" if row["gm_pct_term"] is None else row["gm_pct_term"],
                row["status"],
            ]
        )
    totals = view["totals"]
    writer.writerow(
        [f"Portfolio · {view['month']}", "", "", "", "", totals["people"], totals["revenue"], totals["cost"],
         "" if totals["gm_pct"] is None else totals["gm_pct"], "", ""]
    )
    return buf.getvalue()


# ----------------------------------------------------------------------------- importer (workbook staffing table)
_IMPORT_COLUMNS: dict[str, tuple[str, ...]] = {
    # canonical field -> accepted header prefixes (lower-cased, before any '(' or '*')
    "name": ("name", "person", "resource"),
    "role": ("role",),
    "seniority": ("seniority",),
    "location": ("location",),
    "employment_type": ("employment type", "employment"),
    "assignment": ("assignment / project", "assignment"),
    "utilization": ("utilization %", "utilization", "util %", "util"),
    "bill_rate": ("bill rate",),
    "cost_per_hour": ("our cost / hour", "our cost/hour", "our cost per hour", "cost / hour", "cost/hour", "cost per hour", "our cost"),
    "start": ("start",),
    "end": ("end",),
    "hours_override": ("hours override",),
}
_EMPLOYMENT_LABELS = {
    "w-2 / employee": "w2_employee",
    "w-2": "w2_employee",
    "w2": "w2_employee",
    "w2_employee": "w2_employee",
    "employee": "w2_employee",
    "1099 / contractor": "contractor_1099",
    "1099": "contractor_1099",
    "contractor": "contractor_1099",
    "contractor_1099": "contractor_1099",
}


def _header_key(header: str) -> str:
    text = header.strip().lower()
    for stop in ("(", "*", "\n"):
        text = text.split(stop)[0]
    return text.strip()


def map_import_headers(headers: Iterable[str]) -> dict[str, int]:
    """Workbook column header → canonical field, by prefix match (longest prefix wins)."""

    mapping: dict[str, int] = {}
    for index, header in enumerate(headers):
        key = _header_key(header or "")
        if not key:
            continue
        best: tuple[int, str] | None = None
        for field, prefixes in _IMPORT_COLUMNS.items():
            for prefix in prefixes:
                if (key == prefix or key.startswith(prefix)) and (best is None or len(prefix) > best[0]):
                    best = (len(prefix), field)
        if best is not None and best[1] not in mapping:
            mapping[best[1]] = index
    return mapping


def _parse_date(raw: str | None) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_utilization(raw: str | None) -> Decimal:
    if raw is None or not str(raw).strip():
        return Decimal("1")
    text = str(raw).strip().rstrip("%")
    value = Decimal(text)
    if value > 1:
        value = value / Decimal("100")  # "100" or "50%" in the sheet → fraction the engine expects
    return value


async def import_allocations_csv(
    session: AsyncSession, *, actor: AuthUser, eng: Engagement, text: str
) -> dict[str, Any]:
    """POST /allocations/import — the workbook's staffing table as CSV, its own column headers."""

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any((cell or "").strip() for cell in r)]
    if not rows:
        raise ForecastInputError(["the CSV is empty"])
    header_index = next((i for i, r in enumerate(rows) if "role" in map_import_headers(r)), None)
    if header_index is None:
        raise ForecastInputError(["no header row with a 'Role' column was found"])
    mapping = map_import_headers(rows[header_index])
    bundle = await load_calendar(session)
    created: list[Allocation] = []
    problems: list[str] = []
    for line_no, raw in enumerate(rows[header_index + 1 :], start=header_index + 2):
        get = lambda field: (raw[mapping[field]].strip() if field in mapping and mapping[field] < len(raw) else "")  # noqa: E731
        role = get("role")
        if not role:
            continue  # the workbook: a row with no Role is ignored
        label = f"row {line_no} ({role})"
        location = get("location")
        employment = _EMPLOYMENT_LABELS.get(get("employment_type").lower())
        if employment is None:
            problems.append(f"{label}: employment type must be W-2 / Employee or 1099 / Contractor")
            continue
        if location not in bundle.location_names():
            problems.append(f"{label}: unknown location {location!r}")
            continue
        seniority = get("seniority") or None
        if seniority is not None and seniority not in SENIORITIES:
            problems.append(f"{label}: seniority must be one of {', '.join(SENIORITIES)}")
            continue
        name = get("name") or role
        resource = (
            await session.execute(
                select(Resource).where(
                    func.lower(Resource.name) == name.lower(),
                    Resource.location == location,
                    Resource.employment_type == employment,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if resource is None:
            resource = Resource(id=uuid.uuid4(), name=name, location=location, employment_type=employment, seniority=seniority, active=True)
            session.add(resource)
            await session.flush()
        try:
            alloc = Allocation(
                id=uuid.uuid4(),
                engagement_id=eng.id,
                resource_id=resource.id,
                role=role,
                seniority=seniority,
                location=location,
                employment_type=employment,
                assignment=get("assignment") or None,
                utilization=_parse_utilization(get("utilization")),
                bill_rate=_dec(get("bill_rate").replace("$", "").replace(",", "")),
                cost_per_hour=_dec(get("cost_per_hour").replace("$", "").replace(",", "")),
                start=_parse_date(get("start")),
                end=_parse_date(get("end")),
                hours_override=_dec(get("hours_override").replace(",", "")),
            )
        except (InvalidOperation, ForecastInputError):
            problems.append(f"{label}: a number column could not be read")
            continue
        own = _own_problems(eng, alloc, resource.name, bundle)
        if own:
            problems.extend(f"{label}: {message}" for message in own)
            continue
        session.add(alloc)
        created.append(alloc)
    if problems:
        raise ForecastInputError(problems)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="allocation.imported",
        entity="engagement",
        entity_id=str(eng.id),
        before=None,
        after={"rows": len(created), "allocation_ids": [str(a.id) for a in created]},
    )
    return {"created": len(created), "allocation_ids": [str(a.id) for a in created]}
