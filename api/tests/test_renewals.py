"""S5 E9 — renewals scheduler + notice-date + escalation.

Every Given/When/Then in docs/backlog/s5-renewals-scheduler.md, driven
by ``DEALGATE_NOW`` so the tests time-travel without patching
``datetime``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User

# Registers the scheduler_fired mapper on Base.metadata for create_all.
from app.scheduler.ledger import SchedulerFired  # noqa: F401

from worker.renewals_scheduler import (
    ESCALATION_LEVEL_1_DAYS,
    ESCALATION_LEVEL_2_DAYS,
    NUDGE_STALE_DAYS,
    RENEWAL_LEAD_DAYS,
    run_tick,
)


FIXED_NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)  # a Thursday
SALES_LEADER = "sales-head@smartek21.com"
LEGAL_LEADER = "legal-head@smartek21.com"


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_NOW", FIXED_NOW.isoformat())
    monkeypatch.setenv("SALES_LEADER_EMAIL", SALES_LEADER)
    monkeypatch.setenv("LEGAL_LEADER_EMAIL", LEGAL_LEADER)


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


@pytest_asyncio.fixture
async def legal_leader(session):
    u = User(
        id=_uid(LEGAL_LEADER),
        email=LEGAL_LEADER,
        name="Legal Head",
        groups=["Legal"],
    )
    session.add(u)
    await session.commit()
    return u


async def _seed_owner(session, email: str = "owner@smartek21.com") -> User:
    u = User(
        id=_uid(email),
        email=email,
        name=email.split("@")[0],
        groups=["Sales"],
    )
    session.add(u)
    await session.commit()
    return u


async def _seed_opp_with_sow(
    session,
    *,
    owner: User,
    term_end: date,
    term_start: date | None = None,
    notice_date: date | None = None,
    confirmed_at: datetime | None = None,
) -> tuple[Opportunity, SowVersion]:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-RN-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        governance_status="Signed",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    ts = term_start or (term_end - timedelta(days=180))
    fields: dict = {
        "term_start": {
            "value": ts.isoformat(),
            "page_ref": 1,
            "status": "confirmed",
        },
        "term_end": {
            "value": term_end.isoformat(),
            "page_ref": 1,
            "status": "confirmed",
        },
    }
    if notice_date is not None:
        fields["notice_date"] = {
            "value": notice_date.isoformat(),
            "page_ref": 1,
            "status": "confirmed",
        }
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/{uuid.uuid4()}.pdf",
        file_hash="deadbeef" * 8,
        extract_status="complete",
        extracted_fields=fields,
        confirmed_by=owner.id,
        confirmed_at=confirmed_at or datetime.now(UTC),
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    await session.refresh(opp)
    return opp, version


# ---- AC 1: 60d ahead → opens renewal, idempotent -----------------------


async def test_open_at_lead_creates_renewal_task_and_notifications(
    session, sales_leader
):
    owner = await _seed_owner(session)
    term_end = FIXED_NOW.date() + timedelta(days=RENEWAL_LEAD_DAYS)
    opp, _v = await _seed_opp_with_sow(session, owner=owner, term_end=term_end)

    first = await run_tick(session)
    assert first.renewals_opened == 1
    assert first.tasks_created >= 1

    renewals = list((await session.execute(select(Renewal))).scalars().all())
    assert len(renewals) == 1
    assert renewals[0].status == "open"
    assert renewals[0].term_end == term_end
    assert renewals[0].trigger_date == term_end - timedelta(days=RENEWAL_LEAD_DAYS)

    tasks = list(
        (
            await session.execute(
                select(Task).where(Task.category == "renewal.review")
            )
        )
        .scalars()
        .all()
    )
    assert len(tasks) == 1
    assert tasks[0].owner_id == owner.id

    notifs = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.related_entity == "renewal",
                    Notification.related_entity_id == str(renewals[0].id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert {n.channel for n in notifs} == {"email", "teams", "slack", "inapp"}
    assert await verify_chain(session) is True

    # Second tick same window: idempotent.
    second = await run_tick(session)
    assert second.renewals_opened == 0
    assert second.triggers_skipped >= 1

    still_one = list((await session.execute(select(Renewal))).scalars().all())
    assert len(still_one) == 1


# ---- AC 2: stale renewal → nudge notification --------------------------


async def test_open_renewal_nudged_when_no_update_for_7d(
    session, sales_leader, monkeypatch
):
    owner = await _seed_owner(session)
    term_end = FIXED_NOW.date() + timedelta(days=30)
    opp, _v = await _seed_opp_with_sow(session, owner=owner, term_end=term_end)

    # Pretend the renewal was opened 8 days ago.
    opened_ago = FIXED_NOW - timedelta(days=8)
    monkeypatch.setenv("DEALGATE_NOW", opened_ago.isoformat())
    # Force term_end to satisfy the 60d guard on the initial open by pushing
    # the clock forward 60d. We just need a row in the DB — create manually.
    renewal = Renewal(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        term_end=term_end,
        trigger_date=term_end - timedelta(days=RENEWAL_LEAD_DAYS),
        status="open",
    )
    session.add(renewal)
    await session.commit()

    # Insert an "opened" audit row aged 8 days ago so the nudge trigger fires.
    from app.models.audit import AuditEvent as AE
    stale_ts = FIXED_NOW - timedelta(days=NUDGE_STALE_DAYS + 1)
    ae = AE(
        id=uuid.uuid4(),
        ts=stale_ts,
        actor_id=None,
        action="renewal.opened",
        entity="renewal",
        entity_id=str(renewal.id),
        before=None,
        after={"status": "open"},
        prev_hash=None,
        row_hash="a" * 64,
    )
    session.add(ae)
    await session.commit()

    monkeypatch.setenv("DEALGATE_NOW", FIXED_NOW.isoformat())
    result = await run_tick(session)

    # Nudge notifications for the owner (one per channel).
    nudges = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.related_entity == "renewal",
                    Notification.related_entity_id == str(renewal.id),
                    Notification.user_id == owner.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(nudges) >= 4
    assert result.triggers_fired


# ---- AC 3: notice_date - 60d → Legal task -----------------------------


async def test_notice_date_creates_legal_task(session, legal_leader):
    owner = await _seed_owner(session)
    term_end = FIXED_NOW.date() + timedelta(days=200)
    # Notice date earlier than term_end - 60 (i.e., outside the auto window).
    notice_date = FIXED_NOW.date() + timedelta(days=30)  # -60 = today - 30
    opp, _v = await _seed_opp_with_sow(
        session,
        owner=owner,
        term_end=term_end,
        notice_date=notice_date,
    )

    result = await run_tick(session)
    tasks = list(
        (
            await session.execute(
                select(Task).where(Task.category == "renewal.notice_review")
            )
        )
        .scalars()
        .all()
    )
    assert len(tasks) == 1
    assert tasks[0].owner_id == legal_leader.id
    assert tasks[0].due_date == notice_date
    assert result.tasks_created >= 1


# ---- AC 4/5: 30d + 14d escalations -------------------------------------


async def test_escalation_at_30_and_14_days(session, sales_leader):
    owner = await _seed_owner(session)
    term_end = FIXED_NOW.date() + timedelta(days=ESCALATION_LEVEL_1_DAYS)
    opp, _v = await _seed_opp_with_sow(session, owner=owner, term_end=term_end)

    # Seed an open renewal so the escalation trigger has a row to fire on.
    renewal = Renewal(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        term_end=term_end,
        trigger_date=term_end - timedelta(days=RENEWAL_LEAD_DAYS),
        status="open",
    )
    session.add(renewal)
    await session.commit()

    result_30 = await run_tick(session)

    esc_30 = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.category == "escalation",
                    Notification.related_entity_id == str(renewal.id),
                    Notification.user_id == sales_leader.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(esc_30) >= 4

    # Fast-forward 16d (30 - 14) — the same renewal fires the L2 escalation.
    later = FIXED_NOW + timedelta(days=ESCALATION_LEVEL_1_DAYS - ESCALATION_LEVEL_2_DAYS)
    import os as _os
    _os.environ["DEALGATE_NOW"] = later.isoformat()

    result_14 = await run_tick(session)
    total_esc = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.category == "escalation",
                    Notification.related_entity_id == str(renewal.id),
                    Notification.user_id == sales_leader.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(total_esc) >= 8  # 4 for L1 + 4 for L2 (fan-out per channel)


# ---- AC 6: expired → churn transition + submit_package blocked ---------


async def test_expired_transitions_to_churn_and_blocks_submit(
    session, sales_leader
):
    owner = await _seed_owner(session)
    term_end = FIXED_NOW.date() - timedelta(days=1)
    opp, _v = await _seed_opp_with_sow(session, owner=owner, term_end=term_end)

    renewal = Renewal(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        term_end=term_end,
        trigger_date=term_end - timedelta(days=RENEWAL_LEAD_DAYS),
        status="open",
    )
    session.add(renewal)
    await session.commit()

    result = await run_tick(session)
    assert result.renewals_churned == 1
    await session.refresh(renewal)
    assert renewal.status == "churn"

    # A submit_package call on the same opportunity must now 409.
    from app.services.approvals import ApprovalError, submit_package

    with pytest.raises(ApprovalError) as exc:
        await submit_package(
            session, actor_id=owner.id, opportunity_id=opp.id
        )
    assert exc.value.status_code == 409
    assert "churn" in str(exc.value.detail).lower()


# ---- AC 7: short assessment signed inside 60d window -------------------


async def test_short_assessment_opens_renewal_immediately(
    session, sales_leader
):
    owner = await _seed_owner(session)
    # 4 week assessment starting last week; term ends in 3 weeks.
    term_start = FIXED_NOW.date() - timedelta(days=7)
    term_end = term_start + timedelta(days=21)  # ≤ 28 days
    opp, _v = await _seed_opp_with_sow(
        session,
        owner=owner,
        term_end=term_end,
        term_start=term_start,
        confirmed_at=FIXED_NOW - timedelta(days=6),
    )

    result = await run_tick(session)
    assert result.renewals_opened == 1
    renewals = list((await session.execute(select(Renewal))).scalars().all())
    assert len(renewals) == 1
    assert renewals[0].status == "open"
    assert renewals[0].term_end == term_end


# ---- Router smoke: GET list + PATCH from account owner ----------------


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_router_list_and_patch_owner_only(
    app_with_session, session, sales_leader, monkeypatch
):
    owner = await _seed_owner(session)
    term_end = FIXED_NOW.date() + timedelta(days=45)
    opp, _v = await _seed_opp_with_sow(session, owner=owner, term_end=term_end)
    renewal = Renewal(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        term_end=term_end,
        trigger_date=term_end - timedelta(days=RENEWAL_LEAD_DAYS),
        status="open",
    )
    session.add(renewal)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")

    async with _client(app_with_session) as client:
        # Owner (Sales) can list.
        r = await client.get(
            "/renewals",
            headers={"X-Test-User": owner.email},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == str(renewal.id)

        # Owner can PATCH outcome_summary.
        r = await client.patch(
            f"/renewals/{renewal.id}",
            json={"outcome_summary": "Client agreed to extend by 12 months"},
            headers={"X-Test-User": owner.email},
        )
        assert r.status_code == 200, r.text
        assert r.json()["outcome_summary"] == "Client agreed to extend by 12 months"

    # Non-owner PATCH is 403.
    other = await _seed_owner(session, email="stranger@smartek21.com")
    async with _client(app_with_session) as client:
        r = await client.patch(
            f"/renewals/{renewal.id}",
            json={"outcome_summary": "hi"},
            headers={"X-Test-User": other.email},
        )
        assert r.status_code == 403

    # Audit chain intact.
    assert await verify_chain(session) is True


async def test_router_governance_role_can_read(
    app_with_session, session, sales_leader, monkeypatch
):
    owner = await _seed_owner(session)
    term_end = FIXED_NOW.date() + timedelta(days=45)
    opp, _v = await _seed_opp_with_sow(session, owner=owner, term_end=term_end)
    renewal = Renewal(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        term_end=term_end,
        trigger_date=term_end - timedelta(days=RENEWAL_LEAD_DAYS),
        status="open",
    )
    session.add(renewal)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as client:
        r = await client.get(
            "/renewals",
            headers={"X-Test-User": "finance@smartek21.com"},
        )
        assert r.status_code == 200
        assert r.json()["total"] == 1

    # A user without any governance role is 403.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "")
    async with _client(app_with_session) as client:
        r = await client.get(
            "/renewals",
            headers={"X-Test-User": "randomer@smartek21.com"},
        )
        assert r.status_code == 403
