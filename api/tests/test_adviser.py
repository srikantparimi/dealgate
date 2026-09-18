"""Opportunity Adviser — intake, structured pricing, permissions, immutability.

S3 E11 acceptance tests. Exercises the full vertical slice: HTTP -> service
-> pricing math -> persisted row -> audit -> read back. The Bedrock adapter
is the deterministic :class:`StubBedrock` so tests never touch the real
model service.
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
from app.models.adviser_estimate import DEFAULT_LABEL, AdviserEstimate
from app.models.audit import AuditEvent
from app.services.rate_cards import RateCardRowInput, publish_rate_card


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


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


def _rich_intake() -> dict:
    """An intake with enough signal for the stub to draft a team."""

    return {
        "client_name": "Acme Widgets",
        "problem": (
            "Replace a bespoke internal quoting tool with a modern app "
            "used by sales and delivery teams across three regions."
        ),
        "functions": ["quoting", "approvals", "reporting"],
        "users_count": 250,
        "systems": ["Salesforce", "NetSuite"],
        "geography": "Global",
        "timeline": "9 months",
    }


def _thin_intake() -> dict:
    """A near-empty intake — the stub should ask clarifying questions."""

    return {"client_name": "Mystery Co", "problem": "Help us."}


async def _seed_rate_card(session) -> None:
    """Publish rate card rows covering the roles the stub proposes."""

    await publish_rate_card(
        session,
        actor_id=None,
        rows=[
            RateCardRowInput(
                role="Solution Architect",
                seniority="Senior",
                location="US",
                cost_low=Decimal("120.00"),
                cost_base=Decimal("150.00"),
                cost_high=Decimal("180.00"),
            ),
            RateCardRowInput(
                role="Engineer",
                seniority="Senior",
                location="India",
                cost_low=Decimal("40.00"),
                cost_base=Decimal("50.00"),
                cost_high=Decimal("60.00"),
            ),
            RateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="India",
                cost_low=Decimal("25.00"),
                cost_base=Decimal("32.00"),
                cost_high=Decimal("40.00"),
            ),
            RateCardRowInput(
                role="Project Manager",
                seniority="Mid",
                location="US",
                cost_low=Decimal("90.00"),
                cost_base=Decimal("110.00"),
                cost_high=Decimal("130.00"),
            ),
        ],
        effective_from=date(2026, 1, 1),
    )


# --- permissions -----------------------------------------------------------


async def test_post_requires_auth(app_with_session):
    async with _client(app_with_session) as c:
        r = await c.post("/adviser/estimates", json=_rich_intake())
    assert r.status_code == 401


async def test_post_forbidden_for_delivery(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "d@smartek21.com"},
            json=_rich_intake(),
        )
    assert r.status_code == 403


async def test_post_forbidden_for_finance(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "fin@smartek21.com"},
            json=_rich_intake(),
        )
    assert r.status_code == 403


async def test_post_allowed_for_marketing(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "m@smartek21.com"},
            json=_rich_intake(),
        )
    assert r.status_code == 201, r.text


# --- estimate response shape + label ---------------------------------------


async def test_estimate_returns_exact_label(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "s@smartek21.com"},
            json=_rich_intake(),
        )
    assert r.status_code == 201, r.text
    body = r.json()
    # Verbatim match — this is contractual with the UI header.
    assert body["label"] == "Indicative estimate, requires Delivery and Finance validation"
    assert body["kind"] == "estimate"
    assert body["scope"]
    assert len(body["team"]) >= 3
    # Cost bands + delivery options are present and use Decimal-strings.
    assert "cost_low" in body and "cost_base" in body and "cost_high" in body
    options = {o["key"]: o for o in body["options"]}
    assert set(options.keys()) == {"us_only", "india_only", "mixed"}
    # The stub returns a Mixed team, so US-only and India-only are ineligible
    # but Mixed clears.
    assert options["mixed"]["eligible"] is True


async def test_thin_intake_returns_questions_not_estimate(
    app_with_session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "m@smartek21.com"},
            json=_thin_intake(),
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "questions"
    assert isinstance(body["questions"], list) and body["questions"]
    # Same label wording so the UI can render one banner regardless of shape.
    assert body["label"] == DEFAULT_LABEL


# --- persistence + audit ---------------------------------------------------


async def test_persisted_row_has_model_prompt_and_sources(
    app_with_session, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Presales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "p@smartek21.com"},
            json=_rich_intake(),
        )
    assert r.status_code == 201, r.text
    body = r.json()
    row_id = uuid.UUID(body["id"])

    row = (
        await session.execute(
            select(AdviserEstimate).where(AdviserEstimate.id == row_id)
        )
    ).scalar_one()
    assert row.model, "model must be persisted"
    assert row.prompt_version, "prompt_version must be persisted"
    # sources is a list (possibly empty). None is not acceptable — Presales
    # needs a stable shape to render.
    assert row.sources is not None
    assert isinstance(row.sources, list)
    # Inputs echoed verbatim.
    assert row.inputs["client_name"] == "Acme Widgets"

    audits = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "adviser.estimated")
        )
    ).scalars().all()
    assert len(audits) == 1
    assert audits[0].actor_id == _fake_user_id("p@smartek21.com")
    assert audits[0].after["model"] == row.model
    assert audits[0].after["prompt_version"] == row.prompt_version


# --- no PDF export ---------------------------------------------------------


async def test_no_pdf_export_endpoint(app_with_session, monkeypatch):
    """§15 risk mitigation: no PDF export path exists."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    # Create an estimate first so we have a real id.
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "s@smartek21.com"},
            json=_rich_intake(),
        )
        assert r.status_code == 201
        est_id = r.json()["id"]

        pdf = await c.get(
            f"/adviser/estimates/{est_id}/pdf",
            headers={"X-Test-User": "s@smartek21.com"},
        )
    assert pdf.status_code == 404


# --- rate card integration -------------------------------------------------


async def test_cost_bands_use_rate_cards_when_present(
    app_with_session, session, monkeypatch
):
    await _seed_rate_card(session)
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "s@smartek21.com"},
            json=_rich_intake(),
        )
    assert r.status_code == 201, r.text
    body = r.json()
    # Every proposed role is covered by the seeded rate card → no sentinels.
    assert body["has_sentinel_costs"] is False
    # A specific role: Engineer/Senior/India with 480 hrs @ 100% allocation
    # and cost_base $50 → 480 * 50 = 24,000.
    match = [
        m
        for m in body["team"]
        if m["role"] == "Engineer" and m["seniority"] == "Senior" and m["location"] == "India"
    ]
    assert match, "stub is expected to include a Sr India engineer"
    assert Decimal(match[0]["cost_base"]) == Decimal("24000.00")


async def test_cost_bands_fall_back_to_sentinel_when_no_rate_card(
    app_with_session, monkeypatch
):
    """No rate card published — deterministic pricing still returns numbers,
    but flags them as sentinel so the UI shows "TBD" instead of a false quote.
    """

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "s@smartek21.com"},
            json=_rich_intake(),
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_sentinel_costs"] is True
    assert all(m["is_sentinel"] for m in body["team"])


# --- read endpoints --------------------------------------------------------


async def test_get_returns_persisted_estimate(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "s@smartek21.com"},
            json=_rich_intake(),
        )
        assert r.status_code == 201
        est_id = r.json()["id"]

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/adviser/estimates/{est_id}",
            headers={"X-Test-User": "fin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == est_id
    assert body["label"] == DEFAULT_LABEL
    assert body["team"]


async def test_list_scopes_to_current_user_by_default(
    app_with_session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "alice@smartek21.com"},
            json=_rich_intake(),
        )
        await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "bob@smartek21.com"},
            json=_rich_intake(),
        )
        # Alice's default view sees only her draft.
        r = await c.get(
            "/adviser/estimates",
            headers={"X-Test-User": "alice@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["submitted_by"] == str(
        _fake_user_id("alice@smartek21.com")
    )


async def test_list_all_owners_returns_full_set(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SalesLeader")
    async with _client(app_with_session) as c:
        # SalesLeader may only READ (not write). Use Sales for the setup.
        pass
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "alice@smartek21.com"},
            json=_rich_intake(),
        )
        await c.post(
            "/adviser/estimates",
            headers={"X-Test-User": "bob@smartek21.com"},
            json=_rich_intake(),
        )

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/adviser/estimates?owner=all",
            headers={"X-Test-User": "ceo@smartek21.com"},
        )
    assert r.status_code == 200
    assert r.json()["total"] == 2
