"""Alert scheduler worker (S2-E3 Wave 2).

Every tick the scheduler walks a small set of triggers over the database and
produces two side effects:

1. A task row that surfaces to the "My tasks" view of the person who owns
   the work (Agreements → Legal, Opportunities → Sales, Overdue tasks →
   escalate to the function head).
2. A notification queued via :func:`app.services.notifications.queue_notification`
   which the sender worker (also in this package) drains via SES.

Every write is paired with an ``audit_event`` in the same transaction
(CLAUDE.md rule 5). Idempotency comes from the ``scheduler_fired`` table:
each trigger computes a deterministic key and inserts it before the
side-effect writes; a duplicate insert (unique-constraint failure) skips
the trigger silently. That makes it safe to run the scheduler every 5
minutes, or to re-run a tick after a crash.

Time is injected via ``DEALGATE_NOW`` (ISO-8601 UTC). The main loop reads
the env var each tick so integration tests can freeze the clock without
patching ``datetime``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.db import session_factory
from app.models.audit import AuditEvent
from app.models.client import Agreement, LegalEntity
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.models.user import User
from app.scheduler import (
    LEGAL_LEADER_EMAIL_ENV,
    record_trigger,
    resolve_head_for_role,
)
from app.services.business_days import add_business_days
from app.services.notifications import queue_notification

log = structlog.get_logger("worker.alert_scheduler")


# ---- tuning knobs (kept module-level so tests can monkeypatch) ---------

EXPIRY_WARNING_WINDOW_DAYS = 60
OPPORTUNITY_OVERDUE_BUSINESS_DAYS = 3
MAX_TASK_ESCALATION_LEVEL = 3
POLL_INTERVAL_SECONDS = float(os.environ.get("SCHEDULER_POLL_INTERVAL", "60"))


# ---- time-travel -------------------------------------------------------


def _now() -> datetime:
    """Return "now" honouring ``DEALGATE_NOW`` for deterministic tests."""

    override = os.environ.get("DEALGATE_NOW")
    if override:
        # Accept both "2026-09-17T00:00:00Z" and "2026-09-17T00:00:00+00:00".
        clean = override.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return datetime.now(UTC)


# ---- business-day helpers ---------------------------------------------


def _business_days_between(earlier: date, later: date) -> int:
    """Count business days (Mon-Fri) strictly between ``earlier`` and ``later``.

    Half-open: the earlier day itself is not counted, the later day is.
    Returns 0 for later <= earlier so the caller doesn't need to guard.
    """

    if later <= earlier:
        return 0
    days = 0
    cursor = earlier
    while cursor < later:
        cursor = cursor + timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days


# ---- trigger key helpers ----------------------------------------------


def _trigger_key(name: str, entity_id: str, *parts: str) -> str:
    """Human-readable key used by the ledger's UNIQUE constraint.

    Example: ``opportunity.overdue_checkin:<uuid>:2026-09-13`` — the date is
    the ``next_client_date`` window so a fresh next-action-update produces a
    new key (and therefore a new alert).
    """

    joined = ":".join([name, entity_id, *parts])
    # Cap length so a pathological entity_id can't overflow the column.
    return joined[:255]


# ---- tick result summary ---------------------------------------------


@dataclass
class TickResult:
    """Structured output so tests + ops can see what a tick did."""

    tasks_created: int = 0
    notifications_queued: int = 0
    triggers_fired: list[str] = field(default_factory=list)
    triggers_skipped: int = 0


# ---- task creation helper (audited) -----------------------------------


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


# ---- trigger 1 + 2: agreement expiry warning + expired ---------------


async def _agreement_owner_user(
    session: AsyncSession, agreement: Agreement
) -> User | None:
    """Resolve the Legal owner for an agreement.

    Preference order: the row's own ``owner_email`` (Legal set this in the
    Agreements UI); the ``LEGAL_LEADER_EMAIL`` env var (function head);
    no owner (task lands unassigned so Legal sees it in the leader view).
    """

    email = (agreement.owner_email or "").strip()
    if not email:
        email = (os.environ.get(LEGAL_LEADER_EMAIL_ENV) or "").strip()
    if not email:
        return None
    row = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = User(email=email, name="Legal Owner", groups=["Legal"])
    session.add(row)
    await session.flush()
    return row


def _agreement_expiry_date(agreement: Agreement) -> date | None:
    """Return the canonical expiry, tolerating the S1 vs S2 column names."""

    return agreement.expiry or agreement.expiry_date


async def _process_agreement_expiries(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    """Trigger 1 (60-day warning) and trigger 2 (already expired)."""

    today = now.date()
    warn_cutoff = today + timedelta(days=EXPIRY_WARNING_WINDOW_DAYS)

    rows = list(
        (
            await session.execute(
                select(Agreement).where(Agreement.state == "executed")
            )
        )
        .scalars()
        .all()
    )
    for agreement in rows:
        expiry = _agreement_expiry_date(agreement)
        if expiry is None:
            continue

        if today <= expiry <= warn_cutoff:
            key = _trigger_key("agreement.expiry_warning", str(agreement.id))
            fired = await record_trigger(
                session,
                trigger_key=key,
                trigger_name="agreement.expiry_warning",
                entity="agreement",
                entity_id=str(agreement.id),
            )
            if not fired:
                result.triggers_skipped += 1
                continue

            owner = await _agreement_owner_user(session, agreement)
            correlation = f"scheduler:{key}"
            subject = (
                f"{agreement.kind} agreement expires {expiry.isoformat()} — start renewal"
            )
            await _create_task(
                session,
                owner=owner,
                subject=subject,
                category="agreement.expiry_warning",
                due_date=expiry,
                correlation_id=correlation,
                related_entity="agreement",
                related_entity_id=str(agreement.id),
            )
            result.tasks_created += 1
            if owner is not None:
                queued = await queue_notification(
                    session,
                    user_id=owner.id,
                    category="expiry_warning",
                    subject=subject,
                    body_md=(
                        f"The **{agreement.kind}** agreement expires on "
                        f"`{expiry.isoformat()}`. Start the renewal or "
                        "confirm no further engagement is required."
                    ),
                    related_entity="agreement",
                    related_entity_id=str(agreement.id),
                )
                result.notifications_queued += len(queued)
            result.triggers_fired.append(key)
            continue

        if expiry < today:
            key = _trigger_key("agreement.expired", str(agreement.id))
            fired = await record_trigger(
                session,
                trigger_key=key,
                trigger_name="agreement.expired",
                entity="agreement",
                entity_id=str(agreement.id),
            )
            if not fired:
                result.triggers_skipped += 1
                continue

            owner = await _agreement_owner_user(session, agreement)
            correlation = f"scheduler:{key}"
            subject = f"{agreement.kind} agreement expired on {expiry.isoformat()}"
            await _create_task(
                session,
                owner=owner,
                subject=subject,
                category="agreement.expired",
                due_date=today,
                correlation_id=correlation,
                related_entity="agreement",
                related_entity_id=str(agreement.id),
            )
            result.tasks_created += 1
            if owner is not None:
                queued = await queue_notification(
                    session,
                    user_id=owner.id,
                    category="expiry_warning",
                    subject=subject,
                    body_md=(
                        f"The **{agreement.kind}** agreement expired on "
                        f"`{expiry.isoformat()}`. Coverage is now broken."
                    ),
                    related_entity="agreement",
                    related_entity_id=str(agreement.id),
                )
                result.notifications_queued += len(queued)
            result.triggers_fired.append(key)


# ---- trigger 3: opportunity overdue check-in ---------------------------


async def _last_next_action_update(
    session: AsyncSession, opportunity_id: uuid.UUID, since: datetime
) -> datetime | None:
    """Return the latest ``opportunity.next_action_updated`` audit ts >= since.

    "Intervening" in the AC means "after ``next_client_date``" — the story
    text mentions the next_action must have been touched since the date
    passed, else the check-in is overdue.
    """

    stmt = (
        select(AuditEvent.ts)
        .where(AuditEvent.entity == "opportunity")
        .where(AuditEvent.entity_id == str(opportunity_id))
        .where(AuditEvent.action == "opportunity.next_action_updated")
        .where(AuditEvent.ts >= since)
        .order_by(AuditEvent.ts.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row


async def _process_opportunity_overdue(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()
    rows = list(
        (
            await session.execute(
                select(Opportunity).where(Opportunity.next_client_date.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    for opp in rows:
        assert opp.next_client_date is not None
        overdue_by = _business_days_between(opp.next_client_date, today)
        if overdue_by < OPPORTUNITY_OVERDUE_BUSINESS_DAYS:
            continue

        # An update after `next_client_date` clears the alert until the
        # date itself changes.
        since = datetime.combine(opp.next_client_date, time.min, tzinfo=UTC)
        last_update = await _last_next_action_update(session, opp.id, since)
        if last_update is not None:
            continue

        key = _trigger_key(
            "opportunity.overdue_checkin",
            str(opp.id),
            opp.next_client_date.isoformat(),
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="opportunity.overdue_checkin",
            entity="opportunity",
            entity_id=str(opp.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        owner = (
            await session.execute(select(User).where(User.id == opp.owner_id))
        ).scalar_one_or_none() if opp.owner_id else None
        correlation = f"scheduler:{key}"
        subject = (
            f"Opportunity {opp.hubspot_deal_id} overdue for client check-in"
        )
        await _create_task(
            session,
            owner=owner,
            subject=subject,
            category="opportunity.overdue_checkin",
            due_date=today,
            correlation_id=correlation,
            related_entity="opportunity",
            related_entity_id=str(opp.id),
        )
        result.tasks_created += 1

        # Escalation goes to the Sales leader (function head for Sales role).
        head = await resolve_head_for_role(session, ["Sales"])
        if head is not None:
            queued = await queue_notification(
                session,
                user_id=head.id,
                category="escalation",
                subject=subject,
                body_md=(
                    f"Opportunity `{opp.hubspot_deal_id}` has no client "
                    f"update since `{opp.next_client_date.isoformat()}` "
                    f"({overdue_by} business days). Owner: "
                    f"`{opp.owner_id}`."
                ),
                related_entity="opportunity",
                related_entity_id=str(opp.id),
            )
            result.notifications_queued += len(queued)
        result.triggers_fired.append(key)


# ---- trigger 4: task overdue → escalate --------------------------------


async def _process_task_escalations(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    today = now.date()
    stmt = (
        select(Task)
        .where(Task.due_date.is_not(None))
        .where(Task.due_date < today)
        .where(Task.status.in_(["assigned", "in_progress", "Open"]))
        .where(Task.escalation_level < MAX_TASK_ESCALATION_LEVEL)
    )
    rows = list((await session.execute(stmt)).scalars().all())

    for task in rows:
        next_level = task.escalation_level + 1
        # Bump at most once per calendar day per task. That satisfies "two
        # ticks with the same escalation_level do not double-bump" (the
        # ledger key stays constant within a day) and still lets successive
        # days walk the task up to :data:`MAX_TASK_ESCALATION_LEVEL`.
        key = _trigger_key(
            "task.escalation", str(task.id), today.isoformat()
        )
        fired = await record_trigger(
            session,
            trigger_key=key,
            trigger_name="task.escalation",
            entity="task",
            entity_id=str(task.id),
        )
        if not fired:
            result.triggers_skipped += 1
            continue

        owner = (
            await session.execute(select(User).where(User.id == task.owner_id))
        ).scalar_one_or_none() if task.owner_id else None
        before = {"escalation_level": task.escalation_level}
        task.escalation_level = next_level
        await session.flush()
        await append_audit(
            session,
            actor_id=None,
            action="task.escalated",
            entity="task",
            entity_id=str(task.id),
            before=before,
            after={
                "escalation_level": next_level,
                "due_date": task.due_date.isoformat() if task.due_date else None,
            },
            correlation_id=f"scheduler:{key}",
        )

        head = await resolve_head_for_role(
            session, owner.groups if owner is not None else None
        )
        if head is not None:
            subject = (
                f"Escalation L{next_level}: task overdue since "
                f"{task.due_date.isoformat() if task.due_date else 'unknown'}"
            )
            queued = await queue_notification(
                session,
                user_id=head.id,
                category="escalation",
                subject=subject,
                body_md=(
                    f"Task **{task.subject}** (owner `{task.owner_id}`) is "
                    f"past due and has been escalated to level "
                    f"`{next_level}`."
                ),
                related_entity="task",
                related_entity_id=str(task.id),
            )
            result.notifications_queued += len(queued)
        result.triggers_fired.append(key)


# ---- trigger 5: approval SLA nudge + escalation (S7 C) ----------------


async def _process_approval_sla(
    session: AsyncSession, now: datetime, result: TickResult
) -> None:
    """Nudge approvers 1 business day before due, escalate past due.

    Reads every ``approval.awaiting`` task that is still open and:

    - Between ``due_date - 1 business day`` and ``due_date`` → queue an
      ``approval_pending`` "approver nudge" notification to the assignee.
      Idempotent via the scheduler_fired ledger (one nudge per task per
      calendar day).
    - Past ``due_date`` with ``escalation_level == 0`` → bump to 1 and
      queue an ``escalation`` notification to the function head. The
      existing overdue-task trigger handles subsequent bumps every
      business day up to ``MAX_TASK_ESCALATION_LEVEL``.
    """

    today = now.date()
    stmt = (
        select(Task)
        .where(Task.category == "approval.awaiting")
        .where(Task.due_date.is_not(None))
        .where(Task.status.in_(["assigned", "in_progress", "Open"]))
    )
    rows = list((await session.execute(stmt)).scalars().all())

    for task in rows:
        assert task.due_date is not None
        # Nudge window: [due - 1 biz day, due).
        nudge_start = add_business_days(task.due_date, 0)  # normalise weekend
        # Walk 1 business day back from due_date; equivalent to
        # "the previous business day".
        nudge_start = _prev_business_day(task.due_date)
        if nudge_start <= today < task.due_date:
            key = _trigger_key(
                "approval.nudge", str(task.id), today.isoformat()
            )
            fired = await record_trigger(
                session,
                trigger_key=key,
                trigger_name="approval.nudge",
                entity="task",
                entity_id=str(task.id),
            )
            if not fired:
                result.triggers_skipped += 1
            else:
                owner = (
                    await session.execute(
                        select(User).where(User.id == task.owner_id)
                    )
                ).scalar_one_or_none() if task.owner_id else None
                if owner is not None:
                    subject = (
                        f"Approval due {task.due_date.isoformat()} — please review"
                    )
                    queued = await queue_notification(
                        session,
                        user_id=owner.id,
                        category="approval_pending",
                        subject=subject,
                        body_md=(
                            f"Task **{task.subject}** is due on "
                            f"`{task.due_date.isoformat()}`. Please record "
                            "your decision before the SLA elapses."
                        ),
                        related_entity="task",
                        related_entity_id=str(task.id),
                    )
                    result.notifications_queued += len(queued)
                result.triggers_fired.append(key)

        # Escalation on day-past-due for level 0. Higher levels are
        # handled by the generic task.escalation loop below.
        if today >= task.due_date and task.escalation_level == 0:
            key = _trigger_key(
                "approval.escalation", str(task.id), today.isoformat()
            )
            fired = await record_trigger(
                session,
                trigger_key=key,
                trigger_name="approval.escalation",
                entity="task",
                entity_id=str(task.id),
            )
            if not fired:
                result.triggers_skipped += 1
                continue

            before = {"escalation_level": task.escalation_level}
            task.escalation_level = 1
            await session.flush()
            await append_audit(
                session,
                actor_id=None,
                action="task.escalated",
                entity="task",
                entity_id=str(task.id),
                before=before,
                after={
                    "escalation_level": 1,
                    "due_date": task.due_date.isoformat(),
                    "reason": "approval.awaiting past due_date",
                },
                correlation_id=f"scheduler:{key}",
            )

            owner = (
                await session.execute(
                    select(User).where(User.id == task.owner_id)
                )
            ).scalar_one_or_none() if task.owner_id else None
            head = await resolve_head_for_role(
                session, owner.groups if owner is not None else None
            )
            if head is not None:
                subject = (
                    f"Escalation L1: approval overdue since "
                    f"{task.due_date.isoformat()}"
                )
                queued = await queue_notification(
                    session,
                    user_id=head.id,
                    category="escalation",
                    subject=subject,
                    body_md=(
                        f"Approval task **{task.subject}** has passed its "
                        f"SLA (due `{task.due_date.isoformat()}`) and has "
                        "been escalated to level `1`."
                    ),
                    related_entity="task",
                    related_entity_id=str(task.id),
                )
                result.notifications_queued += len(queued)
            result.triggers_fired.append(key)


def _prev_business_day(day: date) -> date:
    """Return the business day immediately before ``day``."""

    cursor = day - timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor = cursor - timedelta(days=1)
    return cursor


# ---- public entry point -----------------------------------------------


async def run_tick(session: AsyncSession, now: datetime | None = None) -> TickResult:
    """Run one scheduler tick against ``session``.

    The caller commits: this function only flushes and audits so an
    exception in one trigger rolls the whole tick back cleanly.
    """

    when = (now or _now()).astimezone(UTC)
    result = TickResult()
    await _process_agreement_expiries(session, when, result)
    await _process_opportunity_overdue(session, when, result)
    await _process_approval_sla(session, when, result)
    await _process_task_escalations(session, when, result)
    await session.commit()
    return result


async def _tick_forever() -> None:
    log.info("scheduler_started", poll_interval=POLL_INTERVAL_SECONDS)
    while True:
        try:
            async with session_factory() as session:
                summary = await run_tick(session)
            if summary.triggers_fired:
                log.info(
                    "scheduler_tick",
                    tasks=summary.tasks_created,
                    notifications=summary.notifications_queued,
                    fired=len(summary.triggers_fired),
                    skipped=summary.triggers_skipped,
                )
        except Exception:  # pragma: no cover - operational log
            log.exception("scheduler_tick_failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    try:
        asyncio.run(_tick_forever())
    except KeyboardInterrupt:
        log.info("scheduler_stopped")


if __name__ == "__main__":
    main()


__all__ = [
    "EXPIRY_WARNING_WINDOW_DAYS",
    "MAX_TASK_ESCALATION_LEVEL",
    "OPPORTUNITY_OVERDUE_BUSINESS_DAYS",
    "POLL_INTERVAL_SECONDS",
    "TickResult",
    "main",
    "run_tick",
]
