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
from app.models.client import Client, LegalEntity
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.models.user import User

# Importing the scheduler package registers `scheduler_fired` on Base.metadata
# so `create_all` in the shared conftest picks the table up.
from app.scheduler.ledger import SchedulerFired  # noqa: F401 — register mapper

from worker.alert_scheduler import (
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


# ---- agreement expiry warning (S17: gone) -----------------------------
#
# Agreements are a flat NDA/MSA doc store in S17: no expiry column, no
# state machine, no owner_email. The five agreement-scheduler tests that
# used to live here (expiry-within-window, idempotence, outside-window,
# expired, non-executed) went with them.


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


# ---- time-travel via DEALGATE_NOW (S17: agreement clock removed) ------
#
# The former test used a synthetic agreement expiry to prove the clock
# override. S17 removes agreement expiry entirely; the DEALGATE_NOW override
# is exercised by every other tick test through the FIXED_NOW fixture.
