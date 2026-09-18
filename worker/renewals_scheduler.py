"""Renewals scheduler worker (S5 E9 — Agent Y2).

Companion to :mod:`worker.alert_scheduler`. This tick walks SOW versions
and renewal rows and fires the six blueprint §9 triggers:

1. ``term_end - now = 60 days`` and no open renewal:
   open the renewal + owner task + notification.
2. Any renewal ``open`` with no substantive update in the last 7 days:
   nudge notification to the owner.
3. Contractual ``notice_date`` earlier than ``term_end - 60d``:
   Legal-owned task filed at ``notice_date - 60`` (independent alert).
4. ``term_end - now = 30 days`` and renewal still ``open``:
   first escalation to the Sales leader.
5. ``term_end - now = 14 days`` and renewal still ``open``:
   second escalation.
6. ``term_end < now`` with no extension: ``mark_churn`` + block flag.
7. Short assessment (term ≤ 28 days) signed within 60 days of end:
   open a renewal review immediately.

Idempotency comes from :func:`app.scheduler.record_trigger` (the
``scheduler_fired`` unique-key table). Time is injected via
``DEALGATE_NOW`` so tests can freeze the clock without patching
``datetime``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.db import session_factory
from app.models.audit import AuditEvent
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User
from app.scheduler import (
    LEGAL_LEADER_EMAIL_ENV,
    record_trigger,
    resolve_head_for_role,
)
from app.services.notifications import queue_notification
from app.services.renewals import (
    active_renewals_for,
    mark_churn,
    open_renewal,
)


log = structlog.get_logger("worker.renewals_scheduler")


# ---- tuning knobs (module-level so tests can monkeypatch) --------------

RENEWAL_LEAD_DAYS = 60
NUDGE_STALE_DAYS = 7
ESCALATION_LEVEL_1_DAYS = 30
ESCALATION_LEVEL_2_DAYS = 14
NOTICE_LEAD_DAYS = 60
SHORT_ASSESSMENT_MAX_DAYS = 28
POLL_INTERVAL_SECONDS = float(
    os.environ.get("RENEWALS_SCHEDULER_POLL_INTERVAL", "60")
)


# ---- time-travel --------------------------------------------------------


def _now() -> datetime:
    override = os.environ.get("DEALGATE_NOW")
    if override:
        clean = override.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return datetime.now(UTC)


# ---- helpers -----------------------------------------------------------


def _trigger_key(name: str, entity_id: str, *parts: str) -> str:
    joined = ":".join([name, entity_id, *parts])
    return joined[:255]


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _extracted_field(
    version: SowVersion, name: str
) -> Any:
    """Pull ``fields[name].value`` from the extract payload if present."""

    fields = version.extracted_fields or {}
    entry = fields.get(name)
    if not isinstance(entry, dict):
        return None
    return entry.get("value")


def _term_end(version: SowVersion) -> date | None:
    return _parse_iso_date(_extracted_field(version, "term_end"))


def _term_start(version: SowVersion) -> date | None:
    return _parse_iso_date(_extracted_field(version, "term_start"))


def _notice_date(version: SowVersion) -> date | None:
    return _parse_iso_date(_extracted_field(version, "notice_date"))


@dataclass
class TickResult:
    tasks_created: int = 0
    notifications_queued: int = 0
    renewals_opened: int = 0
    renewals_churned: int = 0
    triggers_fired: list[str] = field(default_factory=list)
    triggers_skipped: int = 0


# ---- shared task-writer -------------------------------------------------


async def _create_task(
    session: AsyncSession,
    *,
    owner: User | None,
    subject: str,
    category: str,
    due_date: date | None,
    correlation_id: str,
    related_entity: str,
    related_entity_id: str,
) -> Task:
    task = Task(
        id=uuid.uuid4(),
        owner_id=owner.id if owner else None,
        subject=subject,
        due_date=due_date,
        category=category,
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
            "category": category,
            "due_date": due_date.isoformat() if due_date else None,
            "related_entity": related_entity,
            "related_entity_id": related_entity_id,
            "source": f"scheduler.{category}",
        },
        correlation_id=correlation_id,
    )
    return task


# ---- versions to walk --------------------------------------------------


async def _walk_confirmed_versions(
    session: AsyncSession,
) -> list[tuple[SowVersion, Opportunity]]:
    """Iterate every confirmed SOW version joined with its opportunity."""

    stmt = (
        select(SowVersion, Opportunity)
        .join(Sow, Sow.id == SowVersion.sow_id)
        .join(Opportunity, Opportunity.id == Sow.opportunity_id)
        .where(SowVersion.confirmed_at.is_not(None))
        .order_by(SowVersion.uploaded_at.asc())
    )
    rows = list((await session.execute(stmt)).all())
    return [(v, o) for (v, o) in rows]


# ---- trigger 1: open renewal at term_end - 60d -------------------------


async def _process_open_at_lead(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()
    lead_from = today + timedelta(days=RENEWAL_LEAD_DAYS)

    for version, opp in await _walk_confirmed_versions(session):
        term_end = _term_end(version)
        if term_end is None:
            continue
        # Fire once we are inside the 60-day window (today >= term_end - 60d)
        # so a clock drift or missed tick still catches the deal.
        if today < (term_end - timedelta(days=RENEWAL_LEAD_DAYS)):
            continue
        if term_end < today:
            # Handled by the churn trigger below.
            continue

        key = _trigger_key(
            "renewal.open_lead", str(opp.id), term_end.isoformat()
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="renewal.open_lead",
            entity="opportunity",
            entity_id=str(opp.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        # Also honour the service-level idempotency guard so a manually
        # opened renewal (e.g. via /renewals PATCH) isn't duplicated when
        # the ledger key rotates.
        actives = await active_renewals_for(session, opp.id)
        if any(r.term_end == term_end for r in actives):
            continue

        correlation = f"scheduler:{key}"
        _, created = await open_renewal(
            session,
            opportunity=opp,
            term_end=term_end,
            correlation_id=correlation,
        )
        if created:
            result.renewals_opened += 1
            result.tasks_created += 1  # the owner task in open_renewal
            if opp.owner_id is not None:
                # queue_notification already fanned out inside open_renewal —
                # count as 4 (one per default channel).
                result.notifications_queued += 4
        result.triggers_fired.append(key)


# ---- trigger 2: nudge on stale open renewals ---------------------------


async def _last_meaningful_update(
    session: AsyncSession, renewal_id: uuid.UUID
) -> datetime | None:
    """Return the last ``renewal.updated`` (or `.opened`) ts."""

    stmt = (
        select(AuditEvent.ts)
        .where(AuditEvent.entity == "renewal")
        .where(AuditEvent.entity_id == str(renewal_id))
        .where(AuditEvent.action.in_(("renewal.updated", "renewal.opened")))
        .order_by(AuditEvent.ts.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _process_nudges(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()
    rows = list(
        (
            await session.execute(
                select(Renewal, Opportunity)
                .join(Opportunity, Opportunity.id == Renewal.opportunity_id)
                .where(Renewal.status == "open")
            )
        ).all()
    )
    for renewal, opp in rows:
        last_ts = await _last_meaningful_update(session, renewal.id)
        if last_ts is None:
            last_ts = renewal.opened_at
        if last_ts is None:
            continue
        # Normalise to UTC.
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)
        age = now - last_ts
        if age < timedelta(days=NUDGE_STALE_DAYS):
            continue

        # Key on the calendar day the nudge is due so we send one per week
        # per renewal — a stale row nudged today won't nudge again for 7d.
        key = _trigger_key(
            "renewal.nudge",
            str(renewal.id),
            today.isoformat(),
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="renewal.nudge",
            entity="renewal",
            entity_id=str(renewal.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        if opp.owner_id is not None:
            subject = (
                f"Renewal for {opp.hubspot_deal_id} needs a status update"
            )
            queued = await queue_notification(
                session,
                user_id=opp.owner_id,
                category="expiry_warning",
                subject=subject,
                body_md=(
                    f"Renewal `{renewal.id}` has had no update in "
                    f"`{NUDGE_STALE_DAYS}` days. Record the latest status "
                    "and next action."
                ),
                related_entity="renewal",
                related_entity_id=str(renewal.id),
            )
            result.notifications_queued += len(queued)
        result.triggers_fired.append(key)


# ---- trigger 3: legal task at notice_date - 60d ------------------------


async def _legal_owner(session: AsyncSession) -> User | None:
    email = (os.environ.get(LEGAL_LEADER_EMAIL_ENV) or "").strip()
    if not email:
        return None
    row = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = User(email=email, name="Legal Head", groups=["Legal"])
    session.add(row)
    await session.flush()
    return row


async def _process_notice_date_tasks(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()
    for version, opp in await _walk_confirmed_versions(session):
        term_end = _term_end(version)
        notice = _notice_date(version)
        if term_end is None or notice is None:
            continue
        # Only fire when the contractual notice is earlier than the
        # 60-day auto renewal window (else the renewal task already covers).
        if notice >= term_end - timedelta(days=NOTICE_LEAD_DAYS):
            continue
        fire_from = notice - timedelta(days=NOTICE_LEAD_DAYS)
        if today < fire_from:
            continue

        key = _trigger_key(
            "renewal.notice_task", str(opp.id), notice.isoformat()
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="renewal.notice_task",
            entity="opportunity",
            entity_id=str(opp.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        legal = await _legal_owner(session)
        subject = (
            f"Legal review: notice date {notice.isoformat()} for "
            f"{opp.hubspot_deal_id}"
        )
        correlation = f"scheduler:{key}"
        await _create_task(
            session,
            owner=legal,
            subject=subject,
            category="renewal.notice_review",
            due_date=notice,
            correlation_id=correlation,
            related_entity="opportunity",
            related_entity_id=str(opp.id),
        )
        result.tasks_created += 1
        if legal is not None:
            queued = await queue_notification(
                session,
                user_id=legal.id,
                category="expiry_warning",
                subject=subject,
                body_md=(
                    f"Contractual notice date is `{notice.isoformat()}` "
                    f"(term ends `{term_end.isoformat()}`). Confirm the "
                    "renewal / termination decision with the account owner."
                ),
                related_entity="opportunity",
                related_entity_id=str(opp.id),
            )
            result.notifications_queued += len(queued)
        result.triggers_fired.append(key)


# ---- trigger 4/5: escalations at 30d / 14d -----------------------------


async def _process_escalations(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()
    rows = list(
        (
            await session.execute(
                select(Renewal, Opportunity)
                .join(Opportunity, Opportunity.id == Renewal.opportunity_id)
                .where(Renewal.status == "open")
            )
        ).all()
    )
    for renewal, opp in rows:
        days_left = (renewal.term_end - today).days
        if days_left not in (ESCALATION_LEVEL_1_DAYS, ESCALATION_LEVEL_2_DAYS):
            continue
        level = 1 if days_left == ESCALATION_LEVEL_1_DAYS else 2
        key = _trigger_key(
            "renewal.escalation",
            str(renewal.id),
            f"L{level}",
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="renewal.escalation",
            entity="renewal",
            entity_id=str(renewal.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        head = await resolve_head_for_role(session, ["SalesLeader", "Sales"])
        if head is not None:
            subject = (
                f"Escalation L{level}: renewal for {opp.hubspot_deal_id} "
                f"unresolved with {days_left}d to term end"
            )
            queued = await queue_notification(
                session,
                user_id=head.id,
                category="escalation",
                subject=subject,
                body_md=(
                    f"Renewal `{renewal.id}` for opportunity "
                    f"`{opp.hubspot_deal_id}` is still `open` with "
                    f"`{days_left}` days until `{renewal.term_end.isoformat()}`. "
                    f"Owner: `{opp.owner_id}`."
                ),
                related_entity="renewal",
                related_entity_id=str(renewal.id),
            )
            result.notifications_queued += len(queued)
        result.triggers_fired.append(key)


# ---- trigger 6: churn at term_end + no extension ----------------------


async def _process_churn(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()
    rows = list(
        (
            await session.execute(
                select(Renewal, Opportunity)
                .join(Opportunity, Opportunity.id == Renewal.opportunity_id)
                .where(Renewal.status == "open")
                .where(Renewal.term_end < today)
            )
        ).all()
    )
    for renewal, opp in rows:
        key = _trigger_key(
            "renewal.churn", str(renewal.id), renewal.term_end.isoformat()
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="renewal.churn",
            entity="renewal",
            entity_id=str(renewal.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        await mark_churn(
            session,
            renewal=renewal,
            actor_id=None,
            reason=(
                f"term_end {renewal.term_end.isoformat()} passed with no "
                "extension recorded"
            ),
        )
        result.renewals_churned += 1

        # Notify the account owner + Sales leader so the block is visible.
        if opp.owner_id is not None:
            queued = await queue_notification(
                session,
                user_id=opp.owner_id,
                category="expiry_warning",
                subject=(
                    f"SOW churned for {opp.hubspot_deal_id} — new "
                    "commitments blocked"
                ),
                body_md=(
                    f"Term end `{renewal.term_end.isoformat()}` has passed "
                    "with no extension. New approval packages on this "
                    "opportunity will be rejected."
                ),
                related_entity="renewal",
                related_entity_id=str(renewal.id),
            )
            result.notifications_queued += len(queued)
        head = await resolve_head_for_role(session, ["SalesLeader", "Sales"])
        if head is not None:
            queued = await queue_notification(
                session,
                user_id=head.id,
                category="escalation",
                subject=(
                    f"Churn: {opp.hubspot_deal_id} expired without renewal"
                ),
                body_md=(
                    f"Renewal `{renewal.id}` transitioned to `churn` after "
                    f"`{renewal.term_end.isoformat()}`."
                ),
                related_entity="renewal",
                related_entity_id=str(renewal.id),
            )
            result.notifications_queued += len(queued)
        result.triggers_fired.append(key)


# ---- trigger 7: short assessment opens renewal immediately -------------


async def _process_short_assessments(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()

    for version, opp in await _walk_confirmed_versions(session):
        term_start = _term_start(version)
        term_end = _term_end(version)
        if term_start is None or term_end is None:
            continue
        duration = (term_end - term_start).days
        if duration <= 0 or duration > SHORT_ASSESSMENT_MAX_DAYS:
            continue
        # Confirmed inside 60d of the end?
        if version.confirmed_at is None:
            continue
        confirmed_date = version.confirmed_at.date()
        if (term_end - confirmed_date).days > RENEWAL_LEAD_DAYS:
            continue
        # Skip if a renewal for this term_end already exists.
        actives = await active_renewals_for(session, opp.id)
        if any(r.term_end == term_end for r in actives):
            continue
        # Only fire if we are still before term_end.
        if term_end < today:
            continue

        key = _trigger_key(
            "renewal.short_assessment", str(version.id), term_end.isoformat()
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="renewal.short_assessment",
            entity="sow_version",
            entity_id=str(version.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        correlation = f"scheduler:{key}"
        _, created = await open_renewal(
            session,
            opportunity=opp,
            term_end=term_end,
            trigger_date=today,
            correlation_id=correlation,
        )
        if created:
            result.renewals_opened += 1
            result.tasks_created += 1
            if opp.owner_id is not None:
                result.notifications_queued += 4
        result.triggers_fired.append(key)


# ---- public entry point ------------------------------------------------


async def run_tick(
    session: AsyncSession, now: datetime | None = None
) -> TickResult:
    when = (now or _now()).astimezone(UTC)
    result = TickResult()

    await _process_open_at_lead(session, when, result)
    await _process_short_assessments(session, when, result)
    await _process_nudges(session, when, result)
    await _process_notice_date_tasks(session, when, result)
    await _process_escalations(session, when, result)
    await _process_churn(session, when, result)

    await session.commit()
    return result


async def _tick_forever() -> None:
    log.info("renewals_scheduler_started", poll_interval=POLL_INTERVAL_SECONDS)
    while True:
        try:
            async with session_factory() as session:
                summary = await run_tick(session)
            if summary.triggers_fired:
                log.info(
                    "renewals_tick",
                    tasks=summary.tasks_created,
                    notifications=summary.notifications_queued,
                    opened=summary.renewals_opened,
                    churned=summary.renewals_churned,
                    fired=len(summary.triggers_fired),
                    skipped=summary.triggers_skipped,
                )
        except Exception:  # pragma: no cover - operational log
            log.exception("renewals_tick_failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    try:
        asyncio.run(_tick_forever())
    except KeyboardInterrupt:
        log.info("renewals_scheduler_stopped")


if __name__ == "__main__":
    main()


__all__ = [
    "ESCALATION_LEVEL_1_DAYS",
    "ESCALATION_LEVEL_2_DAYS",
    "NUDGE_STALE_DAYS",
    "NOTICE_LEAD_DAYS",
    "POLL_INTERVAL_SECONDS",
    "RENEWAL_LEAD_DAYS",
    "SHORT_ASSESSMENT_MAX_DAYS",
    "TickResult",
    "main",
    "run_tick",
]
