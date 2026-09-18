"""S2 E4 — policy publish, sentinel default, immutability, permissions."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.policy import PolicyVersion
from app.services.policy import active_policy, publish_policy


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
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


# --- sentinel + service ----------------------------------------------------


async def test_active_policy_returns_sentinel_when_empty(session):
    active = await active_policy(session)
    assert active.is_default is True
    assert active.id is None
    assert active.us_floor == Decimal("0.35")
    assert active.india_floor == Decimal("0.50")
    assert active.fx_convention == "fixed_at_sow_date"


async def test_publish_records_audit_and_becomes_active(session):
    actor = _fake_user_id("fin@smartek21.com")
    version = await publish_policy(
        session,
        actor_id=actor,
        us_floor=Decimal("0.40"),
        india_floor=Decimal("0.55"),
        fx_convention="monthly_average",
        effective_from=date(2026, 9, 1),
        notes="Q4 tightening",
    )
    assert version.us_floor == Decimal("0.40")

    active = await active_policy(session)
    assert active.is_default is False
    assert active.id == version.id
    assert active.us_floor == Decimal("0.40")
    assert active.fx_convention == "monthly_average"

    audit = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "policy.published")
        )
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].after["us_floor"] == "0.40"
    assert audit[0].after["india_floor"] == "0.55"
    assert audit[0].actor_id == actor


async def test_publish_rejects_us_ge_india(session):
    with pytest.raises(Exception) as exc:
        await publish_policy(
            session,
            actor_id=None,
            us_floor=Decimal("0.60"),
            india_floor=Decimal("0.50"),
            fx_convention="fixed_at_sow_date",
            effective_from=date(2026, 10, 1),
        )
    assert "strictly less than india_floor" in str(exc.value.detail)


async def test_publish_rejects_out_of_range_floors(session):
    with pytest.raises(Exception) as exc:
        await publish_policy(
            session,
            actor_id=None,
            us_floor=Decimal("0"),
            india_floor=Decimal("0.5"),
            fx_convention="fixed_at_sow_date",
            effective_from=date(2026, 10, 1),
        )
    assert "us_floor" in str(exc.value.detail)

    with pytest.raises(Exception) as exc2:
        await publish_policy(
            session,
            actor_id=None,
            us_floor=Decimal("0.35"),
            india_floor=Decimal("1.0"),
            fx_convention="fixed_at_sow_date",
            effective_from=date(2026, 10, 1),
        )
    assert "india_floor" in str(exc2.value.detail)


async def test_publish_rejects_unknown_fx_convention(session):
    with pytest.raises(Exception) as exc:
        await publish_policy(
            session,
            actor_id=None,
            us_floor=Decimal("0.35"),
            india_floor=Decimal("0.50"),
            fx_convention="daily",
            effective_from=date(2026, 10, 1),
        )
    assert "fx_convention" in str(exc.value.detail)


async def test_active_policy_picks_latest_by_effective_date(session):
    old = await publish_policy(
        session,
        actor_id=None,
        us_floor=Decimal("0.35"),
        india_floor=Decimal("0.50"),
        fx_convention="fixed_at_sow_date",
        effective_from=date(2026, 1, 1),
    )
    new = await publish_policy(
        session,
        actor_id=None,
        us_floor=Decimal("0.40"),
        india_floor=Decimal("0.55"),
        fx_convention="monthly_average",
        effective_from=date(2026, 6, 1),
    )

    at_march = await active_policy(session, date(2026, 3, 1))
    assert at_march.id == old.id
    at_july = await active_policy(session, date(2026, 7, 1))
    assert at_july.id == new.id


# --- HTTP surface ----------------------------------------------------------


async def test_list_requires_auth(app_with_session):
    async with _client(app_with_session) as c:
        r = await c.get("/admin/policy")
    assert r.status_code == 401


async def test_list_forbidden_for_sales(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get("/admin/policy", headers={"X-Test-User": "s@smartek21.com"})
    assert r.status_code == 403


async def test_list_returns_sentinel_active(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.get("/admin/policy", headers={"X-Test-User": "l@smartek21.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["active"]["is_default"] is True
    assert body["active"]["us_floor"] == "0.35"
    assert body["active"]["india_floor"] == "0.50"
    assert "monthly_average" in body["allowed_fx_conventions"]


async def test_publish_via_http_finance_ok(app_with_session, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/policy",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "us_floor": "0.40",
                "india_floor": "0.55",
                "fx_convention": "monthly_average",
                "notes": "Q4 tightening",
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_active"] is True
    versions = (await session.execute(select(PolicyVersion))).scalars().all()
    assert len(versions) == 1


async def test_publish_via_http_us_gt_india_returns_422(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/policy",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={
                "effective_from": "2026-10-01",
                "us_floor": "0.60",
                "india_floor": "0.50",
                "fx_convention": "fixed_at_sow_date",
            },
        )
    assert r.status_code == 422
    assert "strictly less than india_floor" in r.json()["detail"]


async def test_publish_forbidden_for_delivery(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/policy",
            headers={"X-Test-User": "d@smartek21.com"},
            json={
                "effective_from": "2026-10-01",
                "us_floor": "0.40",
                "india_floor": "0.55",
                "fx_convention": "monthly_average",
            },
        )
    assert r.status_code == 403


async def test_patch_returns_409(app_with_session, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    version = await publish_policy(
        session,
        actor_id=_fake_user_id("fin@smartek21.com"),
        us_floor=Decimal("0.40"),
        india_floor=Decimal("0.55"),
        fx_convention="fixed_at_sow_date",
        effective_from=date(2026, 10, 1),
    )
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/policy/{version.id}",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={"us_floor": "0.45"},
        )
    assert r.status_code == 409
    assert "immutable" in r.json()["detail"]
