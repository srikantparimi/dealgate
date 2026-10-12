"""S22 P3-4 / P3-5 — the nightly portfolio scheduler.

MSP and staff-aug engagements ending within two calendar months raise the
renewal item (a ``renewal`` row when a deal is behind the engagement, the
owner task + notification otherwise); roll-offs within 60 days and
below-floor engagements reach the account owner through the notification
outbox, once per day. Idempotent: a second tick writes nothing new.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

import app.scheduler.ledger  # noqa: F401 — registers scheduler_fired for create_all
from app.auth import AuthUser
from app.models.client import Client
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.task import Task
from app.models.user import User
from app.services import engagement_forecast as svc
from tests.test_s22_portfolio_forecast import seed_calendar
from worker.portfolio_scheduler import run_tick

TODAY = "2027-03-01T06:00:00Z"


async def owner_and_client(session) -> tuple[AuthUser, User, Client]:
    owner = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Account Owner", groups=["Sales"])
    session.add(owner)
    client = Client(id=uuid.uuid4(), name="Client A", hubspot_company_id=None)
    session.add(client)
    await session.commit()
    return AuthUser(owner.id, owner.email, owner.name, ("Sales",)), owner, client


async def engagement(session, actor, client, **overrides):
    body = {
        "client_id": client.id, "name": "Managed services", "type": "msp", "start": date(2026, 11, 1), "end": date(2027, 4, 30),
        "monthly_fee": "42000", "additional_costs_flag": False, "same_dates_for_all": True, "owner_user_id": actor.id,
    }
    body.update(overrides)
    row = await svc.create_engagement(session, actor=actor, body=body)
    await session.commit()
    return row


async def staffed(session, actor, client, *, bill, cost, end=date(2027, 4, 30), name="Staffing"):
    eng = await engagement(session, actor, client, name=name, type="staff_augmentation", monthly_fee=None, same_dates_for_all=False, end=end)
    res = await svc.create_resource(session, actor=actor, body={"name": f"Dev {uuid.uuid4().hex[:4]}", "location": "US", "employment_type": "w2_employee", "seniority": "Mid"})
    await svc.add_allocation(session, actor=actor, eng=eng, body={"resource_id": res.id, "role": "Developer", "utilization": 1, "bill_rate": bill, "cost_per_hour": cost})
    await session.commit()
    return eng


async def test_renewals_raise_the_renewal_item_for_msp_and_staff_aug_within_two_months(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", TODAY)
    await seed_calendar(session)
    actor, owner, client = await owner_and_client(session)
    # 1) MSP without a deal: ends 2027-04-30 → alert date 2027-02-28 ≤ today → owner task + notification
    manual = await engagement(session, actor, client)
    # 2) staff-aug from a deal: renewal row via open_renewal
    opp = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner.id, hubspot_deal_id="HS-1", source="hubspot", governance_status="Intake")
    session.add(opp)
    await session.commit()
    from_deal = await engagement(session, actor, client, name="Staffing FY27", type="staff_augmentation", monthly_fee=None, opportunity_id=opp.id, end=date(2027, 4, 15))
    # 3) MSP ending far out: nothing yet
    far = await engagement(session, actor, client, name="Later MSP", end=date(2027, 12, 31))
    # 4) fixed-cost ending soon: not a renewal type
    await engagement(session, actor, client, name="Assessment", type="assessment", monthly_fee=None, total_price="50000", end=date(2027, 3, 31))

    result = await run_tick(session)
    assert result.renewals_opened == 1 and result.renewal_tasks_created == 1
    renewals = (await session.execute(select(Renewal))).scalars().all()
    assert len(renewals) == 1 and renewals[0].opportunity_id == opp.id and renewals[0].term_end == from_deal.end
    tasks = (await session.execute(select(Task).where(Task.category == "renewal.review"))).scalars().all()
    subjects = {t.subject for t in tasks}
    assert any(manual.name in s and "ends 2027-04-30" in s for s in subjects)
    assert all(far.name not in s for s in subjects)
    notes = (await session.execute(select(Notification).where(Notification.user_id == owner.id))).scalars().all()
    assert {n.category for n in notes} >= {"expiry_warning"}

    # idempotent: a second tick on the same day adds nothing
    before_tasks = await session.scalar(select(func.count()).select_from(Task))
    before_notes = await session.scalar(select(func.count()).select_from(Notification))
    again = await run_tick(session)
    assert again.renewals_opened == 0 and again.renewal_tasks_created == 0 and again.triggers_skipped >= 2
    assert await session.scalar(select(func.count()).select_from(Task)) == before_tasks
    assert await session.scalar(select(func.count()).select_from(Notification)) == before_notes


async def test_nightly_digest_reaches_the_owner_once_with_rolloffs_and_below_floor(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", TODAY)
    await seed_calendar(session)
    actor, owner, client = await owner_and_client(session)
    # below floor: bill 100 vs loaded cost 70 × 1.36 = 95.2 → GM ≈ 4.8 % < 35 %; ends far out (no renewal, no roll-off)
    weak = await staffed(session, actor, client, bill="100", cost="70", end=date(2027, 12, 31), name="Weak margin")
    # healthy but rolling off within 60 days of today (ends 2027-04-15, nothing after)
    rolling = await staffed(session, actor, client, bill="200", cost="70", end=date(2027, 4, 15), name="Rolling off")
    # healthy, long — no finding
    await staffed(session, actor, client, bill="200", cost="70", end=date(2027, 12, 31), name="Healthy")

    result = await run_tick(session)
    assert result.digests_queued == 1
    digest = (
        await session.execute(select(Notification).where(Notification.user_id == owner.id, Notification.category == "daily_digest"))
    ).scalars().all()
    assert digest, "owner gets exactly one nightly digest"
    body = digest[0].body_md
    assert "Roll-offs in the next 60 days** (1)" in body and rolling.name in body
    assert "Below the project floor** (1)" in body and weak.name in body
    assert "Healthy" not in body.split("Below the project floor")[1]
    assert digest[0].subject == "Portfolio forecast · 1 roll-off, 1 below floor"

    # once per day
    again = await run_tick(session)
    assert again.digests_queued == 0
    count = await session.scalar(select(func.count()).select_from(Notification).where(Notification.category == "daily_digest"))
    assert count == len(digest)

    # next day → a new digest
    monkeypatch.setenv("DEALGATE_NOW", "2027-03-02T06:00:00Z")
    tomorrow = await run_tick(session)
    assert tomorrow.digests_queued == 1


async def test_quiet_portfolio_sends_nothing(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", TODAY)
    await seed_calendar(session)
    actor, owner, client = await owner_and_client(session)
    await staffed(session, actor, client, bill="200", cost="70", end=date(2027, 12, 31), name="Healthy")
    result = await run_tick(session)
    assert result.digests_queued == 0 and result.owners_without_findings == 1
    assert await session.scalar(select(func.count()).select_from(Notification)) == 0


@pytest.mark.parametrize("end,fires", [(date(2027, 4, 30), True), (date(2027, 5, 1), True), (date(2027, 5, 2), False)])
async def test_two_calendar_month_rule_is_the_existing_d8_rule(session, monkeypatch, end, fires):
    monkeypatch.setenv("DEALGATE_NOW", TODAY)  # 2027-03-01 → fires for term ends up to and including 2027-05-01
    await seed_calendar(session)
    actor, owner, client = await owner_and_client(session)
    await engagement(session, actor, client, end=end)
    result = await run_tick(session)
    assert (result.renewal_tasks_created == 1) is fires
