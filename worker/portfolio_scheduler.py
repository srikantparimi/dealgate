"""Portfolio scheduler worker (S22 P3-4, P3-5). One tick per EventBridge invocation, nightly.

1. **Renewals (P3-4, D8).** MSP and staff-augmentation engagements whose end
   is within two calendar months (``app.services.renewals.compute_alert_date``,
   month-end clamped) raise the existing renewal item:

   - an engagement created from a deal opens a ``renewal`` row through
     :func:`app.services.renewals.open_renewal` — idempotent per
     (opportunity, term_end); owner task + ``expiry_warning`` notification
     come with it;
   - an engagement with no deal behind it gets the same owner task
     (category ``renewal.review``) + notification, idempotent through the
     ``scheduler_fired`` ledger.

2. **Nightly alert (P3-5).** For every account owner: allocations rolling off
   within 60 days of today with nothing after them, and engagements whose term
   forecast is BELOW FLOOR — one ``daily_digest`` notification per owner per
   day through the notification outbox, never a direct send.

Every write is paired with an ``audit_event`` in the same transaction
(CLAUDE.md rule 5): the renewal / task helpers audit themselves and
``queue_notification`` audits each row. Time is injected via ``DEALGATE_NOW``
like the other schedulers. Nothing here computes a forecast number: the
below-floor test reads the engine's ``status`` from the cached forecast run.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import structlog
from app.audit import append_audit
from app.db import session_factory
from app.models.client import Client
from app.models.engagement import Engagement
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.models.user import User
from app.scheduler import record_trigger
from app.services import engagement_forecast as svc
from app.services.notifications import queue_notification
from app.services.renewals import compute_alert_date, open_renewal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger("worker.portfolio_scheduler")

RENEWAL_TYPES: tuple[str, ...] = ("msp", "staff_augmentation")
ROLLOFF_WINDOW_DAYS = svc.ROLLOFF_WINDOW_DAYS


@dataclass
class TickResult:
    renewals_opened: int = 0
    renewal_tasks_created: int = 0
    digests_queued: int = 0
    triggers_fired: list[str] = field(default_factory=list)
    triggers_skipped: int = 0
    owners_without_findings: int = 0
    engagements_without_owner: int = 0


def _now() -> datetime:
    override = os.environ.get("DEALGATE_NOW")
    if override:
        parsed = datetime.fromisoformat(override.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


# ---- P3-4 · renewals ----------------------------------------------------------


async def process_renewals(session: AsyncSession, today: date, result: TickResult) -> None:
    rows = (
        await session.execute(
            select(Engagement, Client.name)
            .join(Client, Client.id == Engagement.client_id)
            .where(Engagement.type.in_(RENEWAL_TYPES), Engagement.end >= today)
            .order_by(Engagement.end)
        )
    ).all()
    for eng, client_name in rows:
        alert_date = compute_alert_date(eng.end)
        if alert_date > today:
            continue
        correlation = f"portfolio.renewal:{eng.id}"
        if eng.opportunity_id is not None:
            opportunity = await session.get(Opportunity, eng.opportunity_id)
            if opportunity is not None:
                _, created = await open_renewal(
                    session, opportunity=opportunity, term_end=eng.end, correlation_id=correlation
                )
                if created:
                    result.renewals_opened += 1
                    result.triggers_fired.append(f"renewal:{eng.id}")
                else:
                    result.triggers_skipped += 1
                continue
        key = f"portfolio.renewal:{eng.id}:{eng.end.isoformat()}"
        if not await record_trigger(
            session, trigger_key=key, trigger_name="portfolio.renewal", entity="engagement", entity_id=str(eng.id)
        ):
            result.triggers_skipped += 1
            continue
        owner = await session.get(User, eng.owner_user_id) if eng.owner_user_id else None
        subject = f"Renewal review · {client_name} · {eng.name} ends {eng.end.isoformat()}"
        task = Task(
            id=uuid.uuid4(),
            owner_id=owner.id if owner else None,
            subject=subject,
            due_date=eng.end,
            category="renewal.review",
            status="assigned",
        )
        session.add(task)
        await session.flush()
        await append_audit(
            session,
            actor_id=None,
            action="task.created",
            entity="task",
            entity_id=str(task.id),
            before=None,
            after={
                "owner_id": str(owner.id) if owner else None,
                "subject": subject,
                "category": task.category,
                "due_date": eng.end.isoformat(),
                "related_entity": "engagement",
                "related_entity_id": str(eng.id),
                "source": "scheduler.portfolio.renewal",
            },
            correlation_id=correlation,
        )
        result.renewal_tasks_created += 1
        result.triggers_fired.append(key)
        if owner is None:
            result.engagements_without_owner += 1
            continue
        await queue_notification(
            session,
            user_id=owner.id,
            category="expiry_warning",
            subject=subject,
            body_md=(
                f"**{client_name} · {eng.name}** ({eng.type.replace('_', ' ')}) ends on `{eng.end.isoformat()}` — "
                f"two calendar months out from {alert_date.isoformat()}. Extend it, re-price it, or plan the bench.\n\n"
                f"Open the engagement: /engagements/{eng.id}/forecast"
            ),
            related_entity="engagement",
            related_entity_id=str(eng.id),
        )


# ---- P3-5 · nightly roll-off / below-floor digest -----------------------------------


async def process_nightly_digest(session: AsyncSession, today: date, result: TickResult) -> None:
    bundle = await svc.load_calendar(session)
    rows = (
        await session.execute(
            select(Engagement, Client.name)
            .join(Client, Client.id == Engagement.client_id)
            .where(Engagement.end >= today)
            .order_by(Client.name, Engagement.name)
        )
    ).all()
    by_owner: dict[uuid.UUID, list[tuple[Engagement, str]]] = {}
    for eng, client_name in rows:
        if eng.owner_user_id is None:
            result.engagements_without_owner += 1
            continue
        by_owner.setdefault(eng.owner_user_id, []).append((eng, client_name))

    for owner_id, engagements in by_owner.items():
        below: list[str] = []
        for eng, client_name in engagements:
            payload = await svc.forecast_payload(session, eng, bundle=bundle)
            if payload["status"] == "BELOW FLOOR":
                gm = payload["totals"]["gm_pct"]
                shown = "—" if gm is None else f"{gm * 100:.1f}%"
                below.append(f"- {client_name} · {eng.name}: GM {shown} vs floor {bundle.project_floor_pct * 100:.1f}% — /engagements/{eng.id}/forecast")
        rolloffs = await svc.rolloffs_from(session, today, engagement_ids={eng.id for eng, _ in engagements})
        if not below and not rolloffs:
            result.owners_without_findings += 1
            continue
        key = f"portfolio.nightly:{owner_id}:{today.isoformat()}"
        if not await record_trigger(
            session, trigger_key=key, trigger_name="portfolio.nightly", entity="user", entity_id=str(owner_id)
        ):
            result.triggers_skipped += 1
            continue
        lines = [f"Portfolio forecast for {today.isoformat()}.", ""]
        if rolloffs:
            lines.append(f"**Roll-offs in the next {ROLLOFF_WINDOW_DAYS} days** ({len(rolloffs)}):")
            lines.extend(
                f"- {r['resource']} ({r['role']}{' · ' + r['assignment'] if r['assignment'] else ''}) on {r['client']} · {r['engagement']} ends {r['end']} — /engagements/{r['engagement_id']}/allocations"
                for r in rolloffs
            )
            lines.append("")
        if below:
            lines.append(f"**Below the project floor** ({len(below)}):")
            lines.extend(below)
        subject = (
            f"Portfolio forecast · {len(rolloffs)} roll-off{'s' if len(rolloffs) != 1 else ''}, "
            f"{len(below)} below floor"
        )
        await queue_notification(
            session,
            user_id=owner_id,
            category="daily_digest",
            subject=subject,
            body_md="\n".join(lines),
            related_entity=None,
            related_entity_id=None,
        )
        result.digests_queued += 1
        result.triggers_fired.append(key)


# ---- tick ---------------------------------------------------------------------------


async def run_tick(session: AsyncSession, now: datetime | None = None) -> TickResult:
    when = (now or _now()).astimezone(UTC)
    today = when.date()
    result = TickResult()
    await process_renewals(session, today, result)
    await process_nightly_digest(session, today, result)
    await session.commit()
    return result


async def run_once() -> TickResult:
    """Run one EventBridge-owned tick and let the process terminate."""

    async with session_factory() as session:
        summary = await run_tick(session)
    log.info(
        "portfolio_tick",
        renewals_opened=summary.renewals_opened,
        renewal_tasks=summary.renewal_tasks_created,
        digests=summary.digests_queued,
        fired=len(summary.triggers_fired),
        skipped=summary.triggers_skipped,
        owners_quiet=summary.owners_without_findings,
        no_owner=summary.engagements_without_owner,
    )
    return summary


def main() -> None:
    asyncio.run(run_once())


if __name__ == "__main__":
    main()


__all__ = ["RENEWAL_TYPES", "ROLLOFF_WINDOW_DAYS", "TickResult", "main", "process_nightly_digest", "process_renewals", "run_once", "run_tick"]
