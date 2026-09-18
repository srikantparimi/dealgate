"""S6 E9 — weekly forecast update service.

Delivery lead updates ``remaining_hours`` per resource line each week; the
system freezes a ``forecast_period`` snapshot with the resulting forecast
cost + GM per US / India component. Revenue is the pinned contract
revenue from the GM model (unchanged week-to-week). Cost is derived from
``remaining_hours * hourly_cost * allocation_pct`` for each line.

Rule 4 (CLAUDE.md): every ``forecast_period`` row is immutable — a second
POST for the same (gm_model, week_ending) surfaces as 409. The router
never patches an existing row.

Rule 2: all math flows through the pure ``app.gm`` library —
:func:`app.gm.core.gross_margin` computes the ratios; the service just
aggregates totals per component. Money is ``Decimal``.

Rule 5: every ``update_forecast`` writes a ``forecast.updated`` audit row
in the same transaction and, when a component drops below its policy
floor, files a ``recovery`` task + fans a notification out to the Delivery
lead so the CEO dashboard picks it up next tick.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.gm.core import gross_margin
from app.models.approval import ApprovalPackage
from app.models.forecast import ForecastPeriod
from app.models.gm_model import GmModel, ResourceLine
from app.models.task import Task
from app.services.notifications import queue_notification
from app.services.policy import active_policy


# ---- errors --------------------------------------------------------------


class ForecastError(HTTPException):
    """Base error the router turns into a JSON response."""


# ---- clock ---------------------------------------------------------------


def _now() -> datetime:
    """Return "now", honouring ``DEALGATE_NOW`` for deterministic tests."""

    override = os.environ.get("DEALGATE_NOW")
    if override:
        clean = override.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return datetime.now(UTC)


def _week_ending_sunday(day: date) -> date:
    """Return the Sunday on-or-after ``day``.

    ISO weekday: Monday=1..Sunday=7. This matches "week ending Sunday"
    from build-guide §8 — the story ties every forecast row to the ISO
    week's end so weekly cadences line up regardless of when in the week
    the Delivery lead posts.
    """

    weekday = day.isoweekday()  # 1=Mon..7=Sun
    days_until_sunday = 7 - weekday
    return day + timedelta(days=days_until_sunday)


# ---- gm_model helpers ----------------------------------------------------


async def _load_gm_model(session: AsyncSession, gm_model_id: uuid.UUID) -> GmModel:
    stmt = (
        select(GmModel)
        .options(selectinload(GmModel.resource_lines))
        .where(GmModel.id == gm_model_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ForecastError(status_code=404, detail=f"gm_model {gm_model_id} not found")
    return row


async def _assert_released(session: AsyncSession, gm_model_id: uuid.UUID) -> None:
    """409 unless the gm_model belongs to a ``released`` approval package.

    "Released" is the post-distribution state (S5 E8) — the project is
    live, so weekly forecasts have a well-defined baseline.
    """

    stmt = (
        select(ApprovalPackage)
        .where(ApprovalPackage.gm_model_id == gm_model_id)
        .where(ApprovalPackage.status == "released")
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ForecastError(
            status_code=409,
            detail=(
                "forecast requires a released approval package for this gm_model"
            ),
        )


# ---- history helpers -----------------------------------------------------


async def _prev_forecast(
    session: AsyncSession, gm_model_id: uuid.UUID
) -> ForecastPeriod | None:
    stmt = (
        select(ForecastPeriod)
        .where(ForecastPeriod.gm_model_id == gm_model_id)
        .order_by(ForecastPeriod.week_ending.desc(), ForecastPeriod.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _prev_hours_by_line(prev: ForecastPeriod | None) -> dict[str, Decimal]:
    if prev is None or not prev.forecast_lines_json:
        return {}
    out: dict[str, Decimal] = {}
    for line in prev.forecast_lines_json:
        rid = str(line.get("resource_line_id"))
        raw = line.get("remaining_hours")
        if raw is None:
            continue
        try:
            out[rid] = Decimal(str(raw))
        except Exception:  # pragma: no cover — defensive
            continue
    return out


# ---- compute -------------------------------------------------------------


def _compute_totals(
    resource_lines: Iterable[ResourceLine],
    remaining_by_id: dict[str, Decimal],
) -> tuple[Decimal, Decimal, Decimal, list[dict[str, Any]]]:
    """Fold resource lines into (revenue, cost_us, cost_india, snapshot).

    Revenue is the pinned contract revenue (bill_rate * billable_hours *
    allocation) — unchanged week to week. Cost is derived from the
    ``remaining_hours`` per line * ``hourly_cost`` * allocation. Missing
    ``hourly_cost`` (unvalidated) counts as zero cost for the forecast —
    the story treats those lines as "no committed spend yet", separate
    from the ratified GM math where a missing cost blocks approval.
    """

    revenue = Decimal("0")
    cost_us = Decimal("0")
    cost_india = Decimal("0")
    snapshot: list[dict[str, Any]] = []
    for line in resource_lines:
        rid = str(line.id)
        remaining = remaining_by_id.get(rid, Decimal("0"))
        rev = (
            line.billable_hours
            * line.hourly_bill_rate
            * (line.allocation_pct or Decimal("0"))
        )
        cost_per_hour = line.hourly_cost if line.hourly_cost is not None else Decimal(
            "0"
        )
        cost = remaining * cost_per_hour * (line.allocation_pct or Decimal("0"))
        revenue += rev
        if line.location == "India":
            cost_india += cost
        else:
            cost_us += cost
        snapshot.append(
            {
                "resource_line_id": rid,
                "role": line.role,
                "seniority": line.seniority,
                "location": line.location,
                "remaining_hours": format(remaining, "f"),
                "hourly_cost": (
                    format(line.hourly_cost, "f")
                    if line.hourly_cost is not None
                    else None
                ),
                "allocation_pct": format(line.allocation_pct or Decimal("0"), "f"),
            }
        )
    return revenue, cost_us, cost_india, snapshot


def _component_gm(revenue_component: Decimal, cost_component: Decimal) -> Optional[Decimal]:
    """GM ratio for a single geo component, or ``None`` when revenue is 0."""

    if revenue_component <= 0:
        return None
    return gross_margin(revenue_component, cost_component)


# ---- write path ----------------------------------------------------------


async def update_forecast(
    session: AsyncSession,
    *,
    actor: Any,  # AuthUser — kept as Any to dodge circular imports
    gm_model_id: uuid.UUID,
    lines: list[dict[str, Any]],
) -> ForecastPeriod:
    """Create the week's ``forecast_period`` row.

    ``lines`` is a partial list of ``{resource_line_id, remaining_hours}``
    entries — any resource line missing from the payload retains its last
    known remaining hours (from the previous ``forecast_period`` snapshot;
    zero if this is the first forecast for the gm_model).

    Steps:
      1. Assert the gm_model belongs to a ``released`` package (409 else).
      2. Load all resource lines + the previous forecast's snapshot.
      3. Merge the caller's overrides on top of the previous per-line map.
      4. Split revenue by geography (US default when only one side has revenue).
      5. Compute forecast cost US / India + component GMs via the pure lib.
      6. Insert the immutable ``forecast_period`` row (UNIQUE → 409 on dupe).
      7. Emit ``forecast.updated`` audit.
      8. When a component drops below its floor, file a ``recovery`` task
         for the gm_model's creator + queue an ``escalation`` notification.
    """

    if actor is None or getattr(actor, "id", None) is None:
        raise ForecastError(status_code=401, detail="actor required")

    await _assert_released(session, gm_model_id)

    gm_model = await _load_gm_model(session, gm_model_id)

    # Merge overrides on top of last week's snapshot.
    prev = await _prev_forecast(session, gm_model_id)
    remaining_by_id: dict[str, Decimal] = _prev_hours_by_line(prev)

    valid_ids = {str(rl.id) for rl in gm_model.resource_lines}
    for entry in lines or []:
        raw_id = entry.get("resource_line_id") if isinstance(entry, dict) else None
        raw_hours = entry.get("remaining_hours") if isinstance(entry, dict) else None
        if raw_id is None or raw_hours is None:
            raise ForecastError(
                status_code=422,
                detail="each line requires resource_line_id + remaining_hours",
            )
        rid = str(raw_id)
        if rid not in valid_ids:
            raise ForecastError(
                status_code=422,
                detail=f"resource_line {rid} does not belong to gm_model {gm_model_id}",
            )
        try:
            hours = Decimal(str(raw_hours))
        except Exception as exc:
            raise ForecastError(
                status_code=422,
                detail=f"remaining_hours not a number: {raw_hours!r}",
            ) from exc
        if hours < 0:
            raise ForecastError(
                status_code=422, detail="remaining_hours must be >= 0"
            )
        remaining_by_id[rid] = hours

    # Revenue is the pinned contract revenue split by geography.
    # We compute per-line + total revenue here; cost is derived from the
    # merged remaining-hours map.
    revenue_total, cost_us, cost_india, snapshot = _compute_totals(
        gm_model.resource_lines, remaining_by_id
    )
    revenue_us = gm_model.revenue_us or Decimal("0")
    revenue_india = gm_model.revenue_india or Decimal("0")
    # Fall back to the freshly-computed per-line totals when the gm_model
    # snapshot columns are zero (older rows may not have populated them).
    if revenue_us == 0 and revenue_india == 0 and revenue_total > 0:
        # Split by geography using the resource lines.
        for line in gm_model.resource_lines:
            rev = (
                line.billable_hours
                * line.hourly_bill_rate
                * (line.allocation_pct or Decimal("0"))
            )
            if line.location == "India":
                revenue_india += rev
            else:
                revenue_us += rev

    gm_us = _component_gm(revenue_us, cost_us)
    gm_india = _component_gm(revenue_india, cost_india)

    week_ending = _week_ending_sunday(_now().date())

    row = ForecastPeriod(
        id=uuid.uuid4(),
        gm_model_id=gm_model_id,
        week_ending=week_ending,
        forecast_lines_json=snapshot,
        forecast_revenue=(revenue_us + revenue_india),
        forecast_cost_us=cost_us,
        forecast_cost_india=cost_india,
        forecast_gm_us=gm_us,
        forecast_gm_india=gm_india,
        updated_by=actor.id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ForecastError(
            status_code=409,
            detail=(
                f"forecast_period already exists for gm_model {gm_model_id} "
                f"week ending {week_ending.isoformat()}"
            ),
        ) from exc

    await append_audit(
        session,
        actor_id=actor.id,
        action="forecast.updated",
        entity="forecast_period",
        entity_id=str(row.id),
        before=None,
        after={
            "gm_model_id": str(gm_model_id),
            "week_ending": week_ending.isoformat(),
            "forecast_revenue": format(row.forecast_revenue, "f"),
            "forecast_cost_us": format(cost_us, "f"),
            "forecast_cost_india": format(cost_india, "f"),
            "forecast_gm_us": (format(gm_us, "f") if gm_us is not None else None),
            "forecast_gm_india": (
                format(gm_india, "f") if gm_india is not None else None
            ),
            "line_count": len(snapshot),
        },
    )

    # Recovery task + escalation notification if any component fails floor.
    policy = await active_policy(session)
    us_fails = gm_us is not None and gm_us < policy.us_floor
    india_fails = gm_india is not None and gm_india < policy.india_floor
    if us_fails or india_fails:
        failing: list[str] = []
        if us_fails:
            failing.append("US")
        if india_fails:
            failing.append("India")

        delivery_lead_id = gm_model.created_by
        if delivery_lead_id is not None:
            subject = (
                f"Recovery required — forecast GM below floor "
                f"({', '.join(failing)}) for gm_model {gm_model_id}"
            )
            task = Task(
                id=uuid.uuid4(),
                owner_id=delivery_lead_id,
                subject=subject,
                due_date=week_ending,
                category="forecast.recovery",
                status="assigned",
            )
            session.add(task)
            await session.flush()
            await append_audit(
                session,
                actor_id=actor.id,
                action="task.created",
                entity="task",
                entity_id=str(task.id),
                before=None,
                after={
                    "owner_id": str(delivery_lead_id),
                    "subject": subject,
                    "category": task.category,
                    "due_date": week_ending.isoformat(),
                    "related_entity": "forecast_period",
                    "related_entity_id": str(row.id),
                    "source": "forecast.recovery",
                },
            )
            await queue_notification(
                session,
                user_id=delivery_lead_id,
                category="escalation",
                subject=subject,
                body_md=(
                    f"Weekly forecast for gm_model `{gm_model_id}` fell below "
                    f"the policy floor on {', '.join(failing)} component"
                    f"{'s' if len(failing) > 1 else ''}. File a recovery "
                    "plan on the deal detail."
                ),
                related_entity="forecast_period",
                related_entity_id=str(row.id),
            )

    await session.commit()
    await session.refresh(row)
    return row


# ---- read paths ----------------------------------------------------------


async def latest_forecast(
    session: AsyncSession, gm_model_id: uuid.UUID
) -> ForecastPeriod | None:
    """Newest ``forecast_period`` for the gm_model, if any."""

    return await _prev_forecast(session, gm_model_id)


async def forecast_history(
    session: AsyncSession, gm_model_id: uuid.UUID, *, limit: int = 52
) -> list[ForecastPeriod]:
    """Trend data — oldest → newest, capped at ``limit`` rows."""

    stmt = (
        select(ForecastPeriod)
        .where(ForecastPeriod.gm_model_id == gm_model_id)
        .order_by(ForecastPeriod.week_ending.desc(), ForecastPeriod.id.desc())
        .limit(max(1, min(limit, 260)))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()
    return rows


# ---- serialisation -------------------------------------------------------


def serialize(row: ForecastPeriod) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "gm_model_id": str(row.gm_model_id),
        "week_ending": row.week_ending.isoformat(),
        "forecast_lines_json": row.forecast_lines_json,
        "forecast_revenue": format(row.forecast_revenue, "f"),
        "forecast_cost_us": format(row.forecast_cost_us, "f"),
        "forecast_cost_india": format(row.forecast_cost_india, "f"),
        "forecast_gm_us": (
            format(row.forecast_gm_us, "f") if row.forecast_gm_us is not None else None
        ),
        "forecast_gm_india": (
            format(row.forecast_gm_india, "f")
            if row.forecast_gm_india is not None
            else None
        ),
        "updated_by": str(row.updated_by) if row.updated_by else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


__all__ = [
    "ForecastError",
    "forecast_history",
    "latest_forecast",
    "serialize",
    "update_forecast",
]
