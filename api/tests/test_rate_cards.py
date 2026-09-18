"""S2 E4 — rate card publish/list/read + permissions + immutability.

Verifies:
- Finance can publish; new immutable version + row_count in the audit row.
- Non-Finance readers (Delivery, HR) can list/read; Sales gets 403.
- PATCH always returns 409.
- lookup_cost picks the right band from a version.
- Sanity warnings surface for cost bands below the sanity floor.
"""

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
from app.models.rate_card import RateCardRow, RateCardVersion
from app.services.rate_cards import (
    RateCardRowInput,
    active_rate_card,
    lookup_cost,
    publish_rate_card,
)


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


def _sample_row(**overrides) -> dict:
    row = {
        "role": "Engineer",
        "seniority": "Mid",
        "location": "US",
        "cost_low": "55.00",
        "cost_base": "70.00",
        "cost_high": "85.00",
    }
    row.update(overrides)
    return row


# --- permissions -----------------------------------------------------------


async def test_list_requires_auth(app_with_session):
    async with _client(app_with_session) as c:
        r = await c.get("/admin/rate-cards")
    assert r.status_code == 401


async def test_list_forbidden_for_sales(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/admin/rate-cards", headers={"X-Test-User": "s@smartek21.com"}
        )
    assert r.status_code == 403


async def test_list_forbidden_for_marketing(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/admin/rate-cards", headers={"X-Test-User": "m@smartek21.com"}
        )
    assert r.status_code == 403


async def test_list_allowed_for_delivery(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/admin/rate-cards", headers={"X-Test-User": "d@smartek21.com"}
        )
    assert r.status_code == 200
    assert r.json() == {"items": [], "active_id": None}


async def test_publish_forbidden_for_delivery(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/rate-cards",
            headers={"X-Test-User": "d@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "notes": None,
                "rows": [_sample_row()],
            },
        )
    assert r.status_code == 403


# --- publish + audit -------------------------------------------------------


async def test_publish_creates_version_rows_and_audit(app_with_session, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/rate-cards",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "notes": "Q4 refresh",
                "rows": [
                    _sample_row(),
                    _sample_row(
                        role="Engineer",
                        seniority="Senior",
                        cost_low="80.00",
                        cost_base="100.00",
                        cost_high="120.00",
                    ),
                    _sample_row(
                        role="Engineer",
                        seniority="Mid",
                        location="India",
                        cost_low="20.00",
                        cost_base="28.00",
                        cost_high="36.00",
                    ),
                ],
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"]["row_count"] == 3
    assert body["version"]["notes"] == "Q4 refresh"
    assert body["version"]["is_active"] is True
    assert body["warnings"] == []

    # DB round-trip: rows persisted; audit row includes row_count.
    versions = (await session.execute(select(RateCardVersion))).scalars().all()
    assert len(versions) == 1
    rows = (await session.execute(select(RateCardRow))).scalars().all()
    assert len(rows) == 3

    audit = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "rate_card.published")
        )
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].after == {
        "effective_from": "2026-09-01",
        "row_count": 3,
        "notes": "Q4 refresh",
    }
    assert audit[0].actor_id == _fake_user_id("fin@smartek21.com")


async def test_publish_rejects_non_positive_cost(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/rate-cards",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "rows": [_sample_row(cost_low="-1.00")],
            },
        )
    assert r.status_code == 422
    assert "must be > 0" in r.json()["detail"]


async def test_publish_rejects_ordering(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/rate-cards",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "rows": [_sample_row(cost_base="40.00")],  # base < low
            },
        )
    assert r.status_code == 422
    assert "cost_low <= cost_base <= cost_high" in r.json()["detail"]


async def test_publish_rejects_empty_rows(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/rate-cards",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={"effective_from": "2026-09-01", "rows": []},
        )
    # Pydantic min_length=1 → 422.
    assert r.status_code == 422


async def test_publish_sanity_warning_requires_confirm(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/rate-cards",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "rows": [_sample_row(cost_low="1.00", cost_base="2.00", cost_high="3.00")],
            },
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["warnings"], "expected sanity warnings"

    # Retry with confirm=true → succeeds.
    async with _client(app_with_session) as c:
        r2 = await c.post(
            "/admin/rate-cards",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "confirm": True,
                "rows": [_sample_row(cost_low="1.00", cost_base="2.00", cost_high="3.00")],
            },
        )
    assert r2.status_code == 201
    assert r2.json()["warnings"], "warnings still returned when confirmed"


# --- immutability ----------------------------------------------------------


async def test_patch_returns_409(app_with_session, session, monkeypatch):
    """Once published, a rate card version cannot be edited in place."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    version = await publish_rate_card(
        session,
        actor_id=_fake_user_id("fin@smartek21.com"),
        rows=[
            RateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                cost_low=Decimal("55.00"),
                cost_base=Decimal("70.00"),
                cost_high=Decimal("85.00"),
            )
        ],
        effective_from=date(2026, 9, 1),
    )

    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/rate-cards/{version.id}",
            headers={"X-Test-User": "fin@smartek21.com"},
            json={"rows": []},
        )
    assert r.status_code == 409
    assert "immutable" in r.json()["detail"]


# --- get / active / lookup -------------------------------------------------


async def test_get_returns_rows_and_active_flag(app_with_session, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    version = await publish_rate_card(
        session,
        actor_id=_fake_user_id("fin@smartek21.com"),
        rows=[
            RateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                cost_low=Decimal("55.00"),
                cost_base=Decimal("70.00"),
                cost_high=Decimal("85.00"),
            )
        ],
        effective_from=date(2026, 9, 1),
    )

    async with _client(app_with_session) as c:
        r = await c.get(
            f"/admin/rate-cards/{version.id}",
            headers={"X-Test-User": "fin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["is_active"] is True
    assert len(body["rows"]) == 1
    assert body["rows"][0]["role"] == "Engineer"


async def test_active_rate_card_picks_latest_before_date(session):
    old = await publish_rate_card(
        session,
        actor_id=None,
        rows=[
            RateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                cost_low=Decimal("50.00"),
                cost_base=Decimal("60.00"),
                cost_high=Decimal("70.00"),
            )
        ],
        effective_from=date(2026, 1, 1),
    )
    new = await publish_rate_card(
        session,
        actor_id=None,
        rows=[
            RateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                cost_low=Decimal("60.00"),
                cost_base=Decimal("75.00"),
                cost_high=Decimal("90.00"),
            )
        ],
        effective_from=date(2026, 6, 1),
    )

    # At day zero, only the older card is active.
    active_at_march = await active_rate_card(session, date(2026, 3, 1))
    assert active_at_march is not None and active_at_march.id == old.id

    # After June 1, the newer card takes over.
    active_at_aug = await active_rate_card(session, date(2026, 8, 1))
    assert active_at_aug is not None and active_at_aug.id == new.id


async def test_lookup_cost_picks_right_band(session):
    version = await publish_rate_card(
        session,
        actor_id=None,
        rows=[
            RateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                cost_low=Decimal("55.00"),
                cost_base=Decimal("70.00"),
                cost_high=Decimal("85.00"),
            ),
            RateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="India",
                cost_low=Decimal("20.00"),
                cost_base=Decimal("28.00"),
                cost_high=Decimal("36.00"),
            ),
        ],
        effective_from=date(2026, 9, 1),
    )
    us = lookup_cost("engineer", "MID", "US", version)
    assert us is not None
    assert (us.low, us.base, us.high) == (
        Decimal("55.00"),
        Decimal("70.00"),
        Decimal("85.00"),
    )

    india = lookup_cost("Engineer", "Mid", "India", version)
    assert india is not None
    assert india.base == Decimal("28.00")

    assert lookup_cost("Engineer", "Principal", "US", version) is None
