"""Deals API — row-level access, sort, mutation authz, audit emission.

Covers the S1-E2 acceptance tests. Uses `httpx.AsyncClient` against the real
FastAPI app with the in-memory SQLite fixture from `conftest.py`.
"""

from __future__ import annotations

import uuid
from datetime import date

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.opportunity import Opportunity
from app.models.user import User


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _fake_user_id(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest_asyncio.fixture
async def app_with_session(session):
    """Override the `get_session` dep so the app hits the test DB."""

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def seeded(session):
    """Seed two Sales users and four opportunities with distinct dates + statuses."""

    sales = User(email="sales@smartek21.com", name="Sales One", groups=["Sales"])
    sales.id = _fake_user_id("sales@smartek21.com")
    other = User(email="rep2@smartek21.com", name="Sales Two", groups=["Sales"])
    other.id = _fake_user_id("rep2@smartek21.com")
    ceo = User(email="ceo@smartek21.com", name="CEO One", groups=["CEO"])
    ceo.id = _fake_user_id("ceo@smartek21.com")
    session.add_all([sales, other, ceo])
    await session.flush()

    opps = [
        Opportunity(
            hubspot_deal_id="H-100",
            owner_id=sales.id,
            engagement_type="Fixed",
            sales_stage="Qualified",
            governance_status="Intake",
            next_client_action="Send NDA",
            next_client_date=date(2026, 3, 1),
        ),
        Opportunity(
            hubspot_deal_id="H-101",
            owner_id=sales.id,
            engagement_type=None,
            sales_stage="Discovery",
            governance_status="Intake",
            next_client_action="Discovery call",
            next_client_date=date(2026, 1, 15),
        ),
        Opportunity(
            hubspot_deal_id="H-102",
            owner_id=other.id,
            engagement_type="T&M",
            sales_stage="Qualified",
            governance_status="Coverage",
            next_client_action="Follow up",
            next_client_date=None,
        ),
        Opportunity(
            hubspot_deal_id="H-103",
            owner_id=other.id,
            engagement_type=None,
            sales_stage="Prospecting",
            governance_status="Intake",
            next_client_action=None,
            next_client_date=date(2026, 2, 10),
        ),
    ]
    session.add_all(opps)
    await session.commit()
    return {
        "sales": sales,
        "other": other,
        "ceo": ceo,
        "opps": {o.hubspot_deal_id: o for o in opps},
    }


# --- GET /deals: row-level access ------------------------------------------


async def test_list_requires_auth(app_with_session):
    async with _client(app_with_session) as c:
        r = await c.get("/deals")
    assert r.status_code == 401


async def test_list_as_sales_returns_only_own_deals(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get("/deals", headers={"X-Test-User": "sales@smartek21.com"})
    assert r.status_code == 200
    body = r.json()
    hubspot_ids = {row["hubspot_deal_id"] for row in body["items"]}
    assert hubspot_ids == {"H-100", "H-101"}
    assert body["total"] == 2


async def test_list_as_ceo_returns_all_deals(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get("/deals", headers={"X-Test-User": "ceo@smartek21.com"})
    assert r.status_code == 200
    body = r.json()
    hubspot_ids = {row["hubspot_deal_id"] for row in body["items"]}
    assert hubspot_ids == {"H-100", "H-101", "H-102", "H-103"}
    assert body["total"] == 4


# --- GET /deals: default sort ----------------------------------------------


async def test_default_sort_is_next_client_date_asc_nulls_last(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get("/deals", headers={"X-Test-User": "ceo@smartek21.com"})
    assert r.status_code == 200
    dates_and_ids = [(row["next_client_date"], row["hubspot_deal_id"]) for row in r.json()["items"]]
    # 2026-01-15, 2026-02-10, 2026-03-01, then None last.
    assert [d for d, _ in dates_and_ids] == [
        "2026-01-15",
        "2026-02-10",
        "2026-03-01",
        None,
    ]


# --- GET /deals: owner=me filter ------------------------------------------


async def test_owner_me_filter_narrows_to_caller(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        # CEO can see all, but owner=me still narrows to their own (zero deals).
        r = await c.get("/deals?owner=me", headers={"X-Test-User": "ceo@smartek21.com"})
    assert r.status_code == 200
    assert r.json()["items"] == []


# --- GET /deals/{id} --------------------------------------------------------


async def test_get_detail_unauthenticated_401(app_with_session, seeded):
    deal_id = seeded["opps"]["H-100"].id
    async with _client(app_with_session) as c:
        r = await c.get(f"/deals/{deal_id}")
    assert r.status_code == 401


async def test_get_detail_forbidden_for_non_owner_non_leader(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    deal_id = seeded["opps"]["H-102"].id  # owned by "other"
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/deals/{deal_id}", headers={"X-Test-User": "sales@smartek21.com"}
        )
    assert r.status_code == 403


async def test_get_detail_owner_can_read(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    deal_id = seeded["opps"]["H-100"].id
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/deals/{deal_id}", headers={"X-Test-User": "sales@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["hubspot_deal_id"] == "H-100"
    assert body["coverage_state"] == "No client linked"
    assert body["tasks"] == []
    assert body["audit"] == []


# --- PATCH /deals/{id} -----------------------------------------------------


async def test_patch_forbidden_for_non_owner_non_leader(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    deal_id = seeded["opps"]["H-102"].id  # owned by "other"
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/deals/{deal_id}",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"next_client_action": "Try to sneak in"},
        )
    assert r.status_code == 403


async def test_patch_by_owner_emits_owner_changed_audit(
    app_with_session, seeded, monkeypatch, session
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    deal = seeded["opps"]["H-100"]
    new_owner_id = seeded["other"].id
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/deals/{deal.id}",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"owner_id": str(new_owner_id)},
        )
    assert r.status_code == 200
    assert r.json()["owner_id"] == str(new_owner_id)

    rows = (
        await session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity == "opportunity",
                AuditEvent.entity_id == str(deal.id),
                AuditEvent.action == "opportunity.owner_changed",
            )
            .order_by(AuditEvent.ts.asc())
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].after == {"owner_id": str(new_owner_id)}
    assert await verify_chain(session) is True


async def test_patch_next_action_emits_next_action_updated_audit(
    app_with_session, seeded, monkeypatch, session
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    deal = seeded["opps"]["H-100"]
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/deals/{deal.id}",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"next_client_action": "Send SOW draft"},
        )
    assert r.status_code == 200

    rows = (
        await session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity == "opportunity",
                AuditEvent.action == "opportunity.next_action_updated",
            )
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_patch_by_sales_leader_on_others_deal_succeeds(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SalesLeader")
    deal = seeded["opps"]["H-102"]  # owned by "other"
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/deals/{deal.id}",
            headers={"X-Test-User": "salesleader@smartek21.com"},
            json={"engagement_type": "Managed Service"},
        )
    assert r.status_code == 200
    assert r.json()["engagement_type"] == "Managed Service"


# --- governance status stays Intake when engagement_type is null -----------


async def test_governance_status_stays_intake_when_engagement_type_null(
    app_with_session, seeded, monkeypatch, session
):
    """Setting fields other than engagement_type must NOT promote governance
    status; only the S2 workflow module may transition it.
    """

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    deal = seeded["opps"]["H-101"]  # engagement_type IS None
    assert deal.engagement_type is None
    assert deal.governance_status == "Intake"
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/deals/{deal.id}",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"next_client_action": "Book discovery call"},
        )
    assert r.status_code == 200
    assert r.json()["governance_status"] == "Intake"
    # Re-fetch from the DB — no auto-advance.
    fresh = (
        await session.execute(select(Opportunity).where(Opportunity.id == deal.id))
    ).scalar_one()
    assert fresh.governance_status == "Intake"
    assert fresh.engagement_type is None
