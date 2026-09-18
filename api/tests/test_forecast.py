"""S6 E9 — weekly forecast update service + router.

Every Given/When/Then from ``docs/backlog/s6-weekly-forecast.md``, driven
by ``DEALGATE_NOW`` so week-ending is deterministic. Round-trips through
the FastAPI router where possible so role gates + audit + notification
wiring are exercised end-to-end.

CLAUDE.md rule 2: no math in this file — the pass/fail case leans on the
pure GM library exactly like the delivery-model tests do.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.main import app as main_app
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.forecast import ForecastPeriod
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.delivery_model import (
    GmModelPayload,
    ResourceLinePayload,
    create_gm_model_version,
)


FIXED_NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)  # a Thursday


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_NOW", FIXED_NOW.isoformat())


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


async def _seed_user(session, email: str, groups: list[str]) -> User:
    u = User(id=_uid(email), email=email, name=email.split("@")[0], groups=groups)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _seed_opp_with_sow(session, owner: User) -> tuple[Opportunity, SowVersion]:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-FC-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        governance_status="Signed",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/{uuid.uuid4()}.pdf",
        file_hash="deadbeef" * 8,
        extract_status="complete",
        extracted_fields={
            "scope_summary": {"value": "Build", "page_ref": 1, "status": "confirmed"},
        },
        confirmed_by=owner.id,
        confirmed_at=FIXED_NOW,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return opp, version


def _passing_payload(sow_version_id: uuid.UUID, *, lines: int = 5) -> GmModelPayload:
    """5 lines: 3 US + 2 India, priced with room above the 35% / 50% floors."""

    start = date(2026, 3, 1)
    end = date(2026, 12, 31)
    resources: list[ResourceLinePayload] = []
    for i in range(lines):
        loc = "US" if i < 3 else "India"
        # US rates: $200 bill / $100 cost → 50% GM if hours_billable == remaining.
        # India rates: $100 bill / $40 cost → 60% GM.
        bill = Decimal("200") if loc == "US" else Decimal("100")
        cost = Decimal("100") if loc == "US" else Decimal("40")
        resources.append(
            ResourceLinePayload(
                role=f"Engineer{i}",
                seniority="senior",
                location=loc,
                person_name=f"Person{i}",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("1000"),
                hourly_bill_rate=bill,
                hourly_cost=cost,
                validated_by=uuid.uuid4(),
            )
        )
    return GmModelPayload(
        engagement_type="tm",
        sow_version_id=sow_version_id,
        delivery_pattern="hybrid",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        resource_lines=resources,
        cost_lines=[],
    )


def _thin_us_payload(sow_version_id: uuid.UUID) -> GmModelPayload:
    """1 US line where a bigger remaining-hours plan pushes GM under the floor."""

    start = date(2026, 3, 1)
    end = date(2026, 12, 31)
    return GmModelPayload(
        engagement_type="tm",
        sow_version_id=sow_version_id,
        delivery_pattern="us_only",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        resource_lines=[
            ResourceLinePayload(
                role="Engineer",
                seniority="senior",
                location="US",
                person_name="Alice",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("1000"),  # revenue = 1000 * 100 = $100k
                hourly_bill_rate=Decimal("100"),
                hourly_cost=Decimal("90"),  # planned GM = 10%
                validated_by=uuid.uuid4(),
            ),
        ],
        cost_lines=[],
    )


async def _seed_released_package(
    session, *, passing: bool = True, owner_email: str = "owner@smartek21.com"
) -> tuple[Opportunity, User, uuid.UUID]:
    """Seed opp+sow+gm_model and a ``released`` approval_package pointing at
    the gm_model. Returns (opp, owner, gm_model_id)."""

    owner = await _seed_user(session, owner_email, ["Sales"])
    opp, version = await _seed_opp_with_sow(session, owner)
    payload = (
        _passing_payload(version.id)
        if passing
        else _thin_us_payload(version.id)
    )
    gm_model = await create_gm_model_version(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        payload=payload,
    )
    # Manually seed a released approval package so we don't drag the whole
    # approval state machine through every forecast test.
    pkg = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        gm_model_id=gm_model.id,
        package_hash="a" * 64,
        status="released",
        submitted_by=owner.id,
        released_at=FIXED_NOW,
    )
    session.add(pkg)
    await session.commit()
    return opp, owner, gm_model.id


async def _seed_delivery_lead(session) -> User:
    return await _seed_user(
        session, "delivery@smartek21.com", ["Delivery"]
    )


# ---- AC 1: happy path ---------------------------------------------------


async def test_happy_path_creates_forecast_row_with_computed_gm(
    app_with_session, session, monkeypatch
):
    opp, owner, gm_model_id = await _seed_released_package(session)
    delivery = await _seed_delivery_lead(session)

    # Load the resource line IDs for the payload.
    from app.models.gm_model import ResourceLine as RL

    rls = list(
        (
            await session.execute(select(RL).where(RL.gm_model_id == gm_model_id))
        ).scalars().all()
    )
    assert len(rls) == 5

    # Post 500 remaining hours per line (half of planned 1000).
    lines = [
        {"resource_line_id": str(r.id), "remaining_hours": "500"} for r in rls
    ]

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as client:
        r = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": lines},
            headers={"X-Test-User": delivery.email},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    # Week ending Sunday for 2026-09-17 (Thursday) is 2026-09-20.
    assert body["week_ending"] == "2026-09-20"
    # Revenue is the pinned contract revenue: 3 * 1000 * 200 + 2 * 1000 * 100 = 800k.
    assert Decimal(body["forecast_revenue"]) == Decimal("800000.00")
    # Cost: US = 3 * 500 * 100 = 150k. India = 2 * 500 * 40 = 40k.
    assert Decimal(body["forecast_cost_us"]) == Decimal("150000.00")
    assert Decimal(body["forecast_cost_india"]) == Decimal("40000.00")
    # GM US = (600k - 150k) / 600k = 0.75. India = (200k - 40k) / 200k = 0.80.
    assert Decimal(body["forecast_gm_us"]) == Decimal("0.7500")
    assert Decimal(body["forecast_gm_india"]) == Decimal("0.8000")

    # Audit chain intact.
    assert await verify_chain(session) is True

    # forecast.updated audit landed.
    audit_rows = list(
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "forecast.updated")
            )
        ).scalars().all()
    )
    assert len(audit_rows) == 1


# ---- AC 2: recovery task when below floor ------------------------------


async def test_recovery_task_filed_when_gm_below_floor(
    app_with_session, session, monkeypatch
):
    opp, owner, gm_model_id = await _seed_released_package(session, passing=False)
    delivery = await _seed_delivery_lead(session)

    from app.models.gm_model import ResourceLine as RL

    rls = list(
        (
            await session.execute(select(RL).where(RL.gm_model_id == gm_model_id))
        ).scalars().all()
    )
    assert len(rls) == 1
    # remaining_hours == billable_hours → GM matches planned 10% (below 35%).
    lines = [{"resource_line_id": str(rls[0].id), "remaining_hours": "1000"}]

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as client:
        r = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": lines},
            headers={"X-Test-User": delivery.email},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["forecast_gm_us"]) == Decimal("0.1000")

    # A recovery task landed for the gm_model's created_by (the owner in seed).
    tasks = list(
        (
            await session.execute(
                select(Task).where(Task.category == "forecast.recovery")
            )
        ).scalars().all()
    )
    assert len(tasks) == 1
    assert tasks[0].owner_id == owner.id

    # Notification fanned out on the escalation category.
    notifs = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.category == "escalation",
                    Notification.related_entity == "forecast_period",
                )
            )
        ).scalars().all()
    )
    # One per channel (email + teams + slack + inapp).
    assert len(notifs) >= 4
    assert await verify_chain(session) is True


# ---- AC 3: partial update — missing lines retain last known ------------


async def test_partial_update_retains_last_known_hours(
    app_with_session, session, monkeypatch
):
    opp, owner, gm_model_id = await _seed_released_package(session)
    delivery = await _seed_delivery_lead(session)

    from app.models.gm_model import ResourceLine as RL

    rls = list(
        (
            await session.execute(select(RL).where(RL.gm_model_id == gm_model_id))
        ).scalars().all()
    )
    assert len(rls) == 5

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")

    # Week 1: all 5 lines at 800 hours.
    week1_lines = [
        {"resource_line_id": str(r.id), "remaining_hours": "800"} for r in rls
    ]
    async with _client(app_with_session) as client:
        r = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": week1_lines},
            headers={"X-Test-User": delivery.email},
        )
    assert r.status_code == 200

    # Fast-forward one week (2026-09-24 Thursday → week ending 2026-09-27).
    later = FIXED_NOW + timedelta(days=7)
    monkeypatch.setenv("DEALGATE_NOW", later.isoformat())

    # Week 2: only 2 lines updated to 500; the other 3 should retain 800.
    partial = [
        {"resource_line_id": str(rls[0].id), "remaining_hours": "500"},
        {"resource_line_id": str(rls[1].id), "remaining_hours": "500"},
    ]
    async with _client(app_with_session) as client:
        r = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": partial},
            headers={"X-Test-User": delivery.email},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    # US cost: 2 * 500 * 100 + 1 * 800 * 100 = 100k + 80k = 180k.
    assert Decimal(body["forecast_cost_us"]) == Decimal("180000.00")
    # India cost stays: 2 * 800 * 40 = 64k.
    assert Decimal(body["forecast_cost_india"]) == Decimal("64000.00")
    # Snapshot carries all 5 lines.
    assert len(body["forecast_lines_json"]) == 5


# ---- AC 4: not-released package → 409 ----------------------------------


async def test_not_released_package_returns_409(
    app_with_session, session, monkeypatch
):
    owner = await _seed_user(session, "owner@smartek21.com", ["Sales"])
    opp, version = await _seed_opp_with_sow(session, owner)
    payload = _passing_payload(version.id)
    gm_model = await create_gm_model_version(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        payload=payload,
    )
    # No approval package at all → not released.
    delivery = await _seed_delivery_lead(session)

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as client:
        r = await client.post(
            f"/forecast/{gm_model.id}",
            json={"lines": []},
            headers={"X-Test-User": delivery.email},
        )
    assert r.status_code == 409, r.text
    assert "released" in r.json()["detail"].lower()


# ---- AC 5: non-Delivery/SystemAdmin → 403 -------------------------------


async def test_non_delivery_role_returns_403(
    app_with_session, session, monkeypatch
):
    opp, owner, gm_model_id = await _seed_released_package(session)
    hr = await _seed_user(session, "hr@smartek21.com", ["HR"])

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
    async with _client(app_with_session) as client:
        r = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": []},
            headers={"X-Test-User": hr.email},
        )
    assert r.status_code == 403


# ---- AC 6: same-week second POST → 409 (UNIQUE) ------------------------


async def test_same_week_second_post_returns_409(
    app_with_session, session, monkeypatch
):
    opp, owner, gm_model_id = await _seed_released_package(session)
    delivery = await _seed_delivery_lead(session)

    from app.models.gm_model import ResourceLine as RL

    rls = list(
        (
            await session.execute(select(RL).where(RL.gm_model_id == gm_model_id))
        ).scalars().all()
    )
    lines = [{"resource_line_id": str(rls[0].id), "remaining_hours": "500"}]

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as client:
        r1 = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": lines},
            headers={"X-Test-User": delivery.email},
        )
    assert r1.status_code == 200, r1.text

    async with _client(app_with_session) as client:
        r2 = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": lines},
            headers={"X-Test-User": delivery.email},
        )
    assert r2.status_code == 409, r2.text


# ---- Read endpoints -----------------------------------------------------


async def test_latest_and_history_endpoints(
    app_with_session, session, monkeypatch
):
    opp, owner, gm_model_id = await _seed_released_package(session)
    delivery = await _seed_delivery_lead(session)

    from app.models.gm_model import ResourceLine as RL

    rls = list(
        (
            await session.execute(select(RL).where(RL.gm_model_id == gm_model_id))
        ).scalars().all()
    )
    lines = [
        {"resource_line_id": str(r.id), "remaining_hours": "500"} for r in rls
    ]

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as client:
        r = await client.post(
            f"/forecast/{gm_model_id}",
            json={"lines": lines},
            headers={"X-Test-User": delivery.email},
        )
    assert r.status_code == 200

    # Finance can read.
    finance = await _seed_user(session, "finance@smartek21.com", ["Finance"])
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as client:
        r = await client.get(
            f"/forecast/{gm_model_id}/latest",
            headers={"X-Test-User": finance.email},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body is not None
        assert body["gm_model_id"] == str(gm_model_id)

        r = await client.get(
            f"/forecast/{gm_model_id}/history",
            headers={"X-Test-User": finance.email},
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    # A user with no governance role is 403 on reads.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "")
    async with _client(app_with_session) as client:
        r = await client.get(
            f"/forecast/{gm_model_id}/latest",
            headers={"X-Test-User": "randomer@smartek21.com"},
        )
        assert r.status_code == 403
