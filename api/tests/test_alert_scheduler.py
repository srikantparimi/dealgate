"""Acceptance tests for the alert scheduler (worker.alert_scheduler).

Covers every Given/When/Then in docs/backlog/s2-e3-alert-scheduler.md plus
the extra escalation trigger the story picks up in Wave 2.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import append_audit, verify_chain
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client, LegalEntity
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.models.user import User

# Importing the scheduler package registers `scheduler_fired` on Base.metadata
# so `create_all` in the shared conftest picks the table up.
from app.scheduler.ledger import SchedulerFired  # noqa: F401 — register mapper

from worker.alert_scheduler import (
    EXPIRY_WARNING_WINDOW_DAYS,
    _business_days_between,
    run_tick,
)


FIXED_NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)  # a Thursday
LEGAL_LEADER = "legal-head@smartek21.com"
SALES_LEADER = "sales-head@smartek21.com"


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_NOW", FIXED_NOW.isoformat())
    monkeypatch.setenv("SALES_LEADER_EMAIL", SALES_LEADER)
    monkeypatch.setenv("LEGAL_LEADER_EMAIL", LEGAL_LEADER)


@pytest_asyncio.fixture
async def legal_user(session):
    u = User(
        id=_uid(LEGAL_LEADER),
        email=LEGAL_LEADER,
        name="Legal Head",
        groups=["Legal"],
    )
    session.add(u)
    await session.commit()
    return u


@pytest_asyncio.fixture
async def sales_leader(session):
    u = User(
        id=_uid(SALES_LEADER),
        email=SALES_LEADER,
        name="Sales Head",
        groups=["SalesLeader"],
    )
    session.add(u)
    await session.commit()
    return u


async def _seed_agreement(
    session, *, expiry: date, owner_email: str | None = None, state: str = "executed"
) -> Agreement:
    client = Client(id=uuid.uuid4(), name="Acme Corp")
    entity = LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Acme US")
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=entity.id,
        kind="MSA",
        state=state,
        owner_email=owner_email,
        expiry=expiry,
    )
    session.add_all([client, entity, agreement])
    await session.commit()
    return agreement


async def _seed_opportunity(
    session, *, owner: User, next_client_date: date
) -> Opportunity:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"deal-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        next_client_date=next_client_date,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return opp


def _prev_business_day(from_date: date, business_days: int) -> date:
    """Return a date exactly `business_days` business days before `from_date`."""

    d = from_date
    left = business_days
    while left > 0:
        d = d - timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


# ---- business day helper is critical enough to warrant its own test ----


def test_business_days_between_handles_weekend_wraparound():
    # Thu 2026-09-17 → Wed 2026-09-23: 4 business days (Fri, Mon, Tue, Wed).
    assert _business_days_between(date(2026, 9, 17), date(2026, 9, 23)) == 4
    # Same day → 0.
    assert _business_days_between(date(2026, 9, 17), date(2026, 9, 17)) == 0
    # Reversed range → 0 (guard).
    assert _business_days_between(date(2026, 9, 18), date(2026, 9, 17)) == 0


# ---- agreement expiry warning -----------------------------------------


async def test_expiry_within_window_creates_task_and_notifies_owner(
    session, legal_user
):
    expiry = FIXED_NOW.date() + timedelta(days=EXPIRY_WARNING_WINDOW_DAYS)
    agreement = await _seed_agreement(session, expiry=expiry, owner_email=LEGAL_LEADER)

    result = await run_tick(session)

    assert result.tasks_created == 1
    tasks = list(
        (
            await session.execute(
                select(Task).where(Task.category == "agreement.expiry_warning")
            )
        )
        .scalars()
        .all()
    )
    assert len(tasks) == 1
    assert tasks[0].owner_id == legal_user.id
    assert tasks[0].due_date == expiry

    notifs = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.related_entity == "agreement",
                    Notification.related_entity_id == str(agreement.id),
                    Notification.category == "expiry_warning",
                )
            )
        )
        .scalars()
        .all()
    )
    # Fan-out across the four channels (email, teams, slack, inapp).
    assert {n.channel for n in notifs} == {"email", "teams", "slack", "inapp"}
    assert all(n.user_id == legal_user.id for n in notifs)
    assert await verify_chain(session) is True


async def test_expiry_trigger_is_idempotent_across_ticks(session, legal_user):
    expiry = FIXED_NOW.date() + timedelta(days=30)
    await _seed_agreement(session, expiry=expiry, owner_email=LEGAL_LEADER)

    first = await run_tick(session)
    second = await run_tick(session)

    assert first.tasks_created == 1
    assert second.tasks_created == 0
    assert second.triggers_skipped >= 1

    tasks = list((await session.execute(select(Task))).scalars().all())
    assert len(tasks) == 1


async def test_expiry_outside_window_creates_nothing(session, legal_user):
    expiry = FIXED_NOW.date() + timedelta(days=90)
    await _seed_agreement(session, expiry=expiry, owner_email=LEGAL_LEADER)

    result = await run_tick(session)
    assert result.tasks_created == 0
    tasks = list((await session.execute(select(Task))).scalars().all())
    assert tasks == []


async def test_expired_agreement_creates_expired_task(session, legal_user):
    expiry = FIXED_NOW.date() - timedelta(days=1)
    await _seed_agreement(session, expiry=expiry, owner_email=LEGAL_LEADER)

    result = await run_tick(session)
    assert result.tasks_created == 1
    task = (
        await session.execute(select(Task).where(Task.category == "agreement.expired"))
    ).scalar_one()
    assert task.owner_id == legal_user.id
    # Second tick does not re-create.
    again = await run_tick(session)
    assert again.tasks_created == 0


async def test_non_executed_agreement_is_ignored(session, legal_user):
    # `drafting` should never enter the expiry pipeline even with a near date.
    await _seed_agreement(
        session,
        expiry=FIXED_NOW.date() + timedelta(days=10),
        owner_email=LEGAL_LEADER,
        state="drafting",
    )
    result = await run_tick(session)
    assert result.tasks_created == 0


# ---- opportunity overdue check-in --------------------------------------


async def test_opportunity_overdue_creates_task_and_escalates(
    session, sales_leader
):
    owner = User(
        id=_uid("rep@smartek21.com"),
        email="rep@smartek21.com",
        name="Sales Rep",
        groups=["Sales"],
    )
    session.add(owner)
    await session.commit()

    overdue_date = _prev_business_day(FIXED_NOW.date(), 4)
    opp = await _seed_opportunity(session, owner=owner, next_client_date=overdue_date)

    result = await run_tick(session)
    assert result.tasks_created == 1

    task = (
        await session.execute(
            select(Task).where(Task.category == "opportunity.overdue_checkin")
        )
    ).scalar_one()
    assert task.owner_id == owner.id

    # Sales leader (function head) received an escalation notification.
    escalations = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.category == "escalation",
                    Notification.user_id == sales_leader.id,
                    Notification.related_entity_id == str(opp.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(escalations) == 4  # one per channel
    assert await verify_chain(session) is True


async def test_opportunity_future_date_creates_nothing(session, sales_leader):
    owner = User(
        id=_uid("rep2@smartek21.com"),
        email="rep2@smartek21.com",
        name="Rep2",
        groups=["Sales"],
    )
    session.add(owner)
    await session.commit()

    await _seed_opportunity(
        session, owner=owner, next_client_date=FIXED_NOW.date() + timedelta(days=1)
    )
    result = await run_tick(session)
    assert result.tasks_created == 0


async def test_opportunity_recent_next_action_update_suppresses_alert(
    session, sales_leader
):
    owner = User(
        id=_uid("rep3@smartek21.com"),
        email="rep3@smartek21.com",
        name="Rep3",
        groups=["Sales"],
    )
    session.add(owner)
    await session.commit()

    overdue_date = _prev_business_day(FIXED_NOW.date(), 5)
    opp = await _seed_opportunity(
        session, owner=owner, next_client_date=overdue_date
    )
    # Sales updated the next action AFTER the next_client_date passed.
    await append_audit(
        session,
        actor_id=owner.id,
        action="opportunity.next_action_updated",
        entity="opportunity",
        entity_id=str(opp.id),
        before={"next_client_action": None},
        after={"next_client_action": "call scheduled"},
    )
    await session.commit()

    result = await run_tick(session)
    assert result.tasks_created == 0


# ---- task escalation ---------------------------------------------------


async def test_overdue_task_escalation_level_bumps_once_per_tick(
    session, sales_leader
):
    owner = User(
        id=_uid("owner-x@smartek21.com"),
        email="owner-x@smartek21.com",
        name="OwnerX",
        groups=["Sales"],
    )
    session.add(owner)
    await session.commit()

    task = Task(
        id=uuid.uuid4(),
        owner_id=owner.id,
        subject="Chase the client",
        due_date=FIXED_NOW.date() - timedelta(days=2),
        status="assigned",
        category="coverage",
        escalation_level=0,
    )
    session.add(task)
    await session.commit()

    first = await run_tick(session)
    await session.refresh(task)
    assert task.escalation_level == 1
    assert first.notifications_queued > 0

    # A second tick without any level change must NOT re-bump nor re-notify.
    second = await run_tick(session)
    await session.refresh(task)
    assert task.escalation_level == 1
    assert second.triggers_skipped >= 1

    # An escalated audit row was written.
    audits = list(
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "task.escalated")
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert await verify_chain(session) is True


async def test_task_escalation_stops_at_max_level(session, sales_leader):
    owner = User(
        id=_uid("owner-y@smartek21.com"),
        email="owner-y@smartek21.com",
        name="OwnerY",
        groups=["Sales"],
    )
    session.add(owner)
    await session.commit()

    task = Task(
        id=uuid.uuid4(),
        owner_id=owner.id,
        subject="Already max escalated",
        due_date=FIXED_NOW.date() - timedelta(days=10),
        status="assigned",
        escalation_level=3,
    )
    session.add(task)
    await session.commit()

    result = await run_tick(session)
    await session.refresh(task)
    assert task.escalation_level == 3
    assert result.tasks_created == 0


# ---- time-travel via DEALGATE_NOW --------------------------------------


async def test_dealgate_now_env_controls_the_tick_clock(
    session, legal_user, monkeypatch
):
    # Move the clock 30 days forward — an agreement expiring in 80 days is
    # then inside the 60-day window and must fire.
    monkeypatch.setenv("DEALGATE_NOW", (FIXED_NOW + timedelta(days=30)).isoformat())
    await _seed_agreement(
        session,
        expiry=FIXED_NOW.date() + timedelta(days=80),
        owner_email=LEGAL_LEADER,
    )
    result = await run_tick(session)
    assert result.tasks_created == 1
