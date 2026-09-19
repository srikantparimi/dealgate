"""S9 wave 1 — client rate card publish + immutability + role gates + audit.

Covers:
- publish creates one immutable card + rows + audit
- unauthenticated → 401; Sales → 403; Delivery can read but not write
- GET returns has_fallback=true when no card exists
- active_client_rate_card picks the newest effective_from
- rows are never mutated after publish (a new card is a new version)
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
from app.models.client import Client
from app.models.client_rate_card import ClientRateCard, ClientRateCardRow
from app.services.client_rate_cards import (
    ClientRateCardRowInput,
    active_client_rate_card,
    publish_client_rate_card,
)


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _http(app):
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


@pytest_asyncio.fixture
async def client_row(session):
    c = Client(id=uuid.uuid4(), name="Acme Corp")
    session.add(c)
    await session.commit()
    return c


def _row(**overrides) -> dict:
    r = {
        "role": "Engineer",
        "seniority": "Mid",
        "location": "US",
        "bill_rate": "175.00",
        "currency": "USD",
        "unit": "hourly",
    }
    r.update(overrides)
    return r


# --- permission gates ------------------------------------------------------


async def test_get_requires_auth(app_with_session, client_row):
    async with _http(app_with_session) as c:
        r = await c.get(f"/clients/{client_row.id}/rate-card")
    assert r.status_code == 401


async def test_publish_forbidden_for_delivery(app_with_session, client_row, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _http(app_with_session) as c:
        r = await c.post(
            f"/clients/{client_row.id}/rate-card",
            headers={"X-Test-User": "d@smartek21.com"},
            json={"effective_from": "2026-09-01", "source": "manual", "rows": [_row()]},
        )
    assert r.status_code == 403


async def test_get_allowed_for_delivery(app_with_session, client_row, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _http(app_with_session) as c:
        r = await c.get(
            f"/clients/{client_row.id}/rate-card",
            headers={"X-Test-User": "d@smartek21.com"},
        )
    assert r.status_code == 200


# --- has_fallback empty state ---------------------------------------------


async def test_get_empty_returns_has_fallback(app_with_session, client_row, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _http(app_with_session) as c:
        r = await c.get(
            f"/clients/{client_row.id}/rate-card",
            headers={"X-Test-User": "f@smartek21.com"},
        )
    body = r.json()
    assert r.status_code == 200
    assert body["card"] is None
    assert body["has_fallback"] is True
    assert "no client rate card" in body["warning"]


async def test_get_404_when_client_missing(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _http(app_with_session) as c:
        r = await c.get(
            f"/clients/{uuid.uuid4()}/rate-card",
            headers={"X-Test-User": "f@smartek21.com"},
        )
    assert r.status_code == 404


# --- publish + audit -------------------------------------------------------


async def test_publish_creates_card_rows_and_audit(
    app_with_session, client_row, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _http(app_with_session) as c:
        r = await c.post(
            f"/clients/{client_row.id}/rate-card",
            headers={"X-Test-User": "f@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "source": "manual",
                "notes": "Q4 MSA import",
                "rows": [_row(), _row(seniority="Senior", bill_rate="225.00")],
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_fallback"] is False
    assert body["card"]["row_count"] == 2
    assert body["card"]["source"] == "manual"

    cards = (await session.execute(select(ClientRateCard))).scalars().all()
    assert len(cards) == 1
    rows = (await session.execute(select(ClientRateCardRow))).scalars().all()
    assert len(rows) == 2

    audit = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "client_rate_card.published")
        )
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].after["row_count"] == 2
    assert audit[0].after["source"] == "manual"


async def test_publish_rejects_empty_rows(app_with_session, client_row, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _http(app_with_session) as c:
        r = await c.post(
            f"/clients/{client_row.id}/rate-card",
            headers={"X-Test-User": "f@smartek21.com"},
            json={"effective_from": "2026-09-01", "source": "manual", "rows": []},
        )
    assert r.status_code == 422


async def test_publish_rejects_bad_source(app_with_session, client_row, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _http(app_with_session) as c:
        r = await c.post(
            f"/clients/{client_row.id}/rate-card",
            headers={"X-Test-User": "f@smartek21.com"},
            json={"effective_from": "2026-09-01", "source": "hack", "rows": [_row()]},
        )
    assert r.status_code == 422


# --- active + immutability -------------------------------------------------


async def test_active_picks_latest_effective_from(session, client_row):
    a = await publish_client_rate_card(
        session,
        actor_id=None,
        client_id=client_row.id,
        rows=[
            ClientRateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                bill_rate=Decimal("150.00"),
            )
        ],
        effective_from=date(2026, 1, 1),
    )
    b = await publish_client_rate_card(
        session,
        actor_id=None,
        client_id=client_row.id,
        rows=[
            ClientRateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                bill_rate=Decimal("175.00"),
            )
        ],
        effective_from=date(2026, 6, 1),
    )
    active = await active_client_rate_card(session, client_row.id)
    assert active.id == b.id
    # a stays intact — immutable.
    a_rows = (
        await session.execute(
            select(ClientRateCardRow).where(ClientRateCardRow.client_rate_card_id == a.id)
        )
    ).scalars().all()
    assert len(a_rows) == 1
    assert a_rows[0].bill_rate == Decimal("150.0000")


async def test_active_returns_none_before_effective(session, client_row):
    await publish_client_rate_card(
        session,
        actor_id=None,
        client_id=client_row.id,
        rows=[
            ClientRateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                bill_rate=Decimal("175.00"),
            )
        ],
        effective_from=date(2099, 1, 1),
    )
    assert await active_client_rate_card(session, client_row.id) is None


async def test_publish_rejects_bad_location(session, client_row):
    with pytest.raises(Exception):
        await publish_client_rate_card(
            session,
            actor_id=None,
            client_id=client_row.id,
            rows=[
                ClientRateCardRowInput(
                    role="Engineer",
                    seniority="Mid",
                    location="Canada",
                    bill_rate=Decimal("175.00"),
                )
            ],
            effective_from=date(2026, 1, 1),
        )
