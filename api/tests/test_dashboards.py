"""S5 E10 — role dashboards + client SOW/GM aggregation.

Every Given/When/Then from ``docs/backlog/s5-role-dashboards.md``, one
test per case. Tests round-trip through the FastAPI router so role
gates run for real.

No math in this file (CLAUDE.md rule 2): the aggregation is asserted by
constructing gm_model rows with known Decimal inputs and reading the
service output.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.main import app as main_app
from app.models.client import Client
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.dashboards import (
    ceo_view,
    client_sow_gm_view,
    finance_view,
)


# ---- fixtures / helpers --------------------------------------------------


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest_asyncio.fixture
async def app_with_session(session) -> AsyncIterator:
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


async def _seed_client(session, name: str) -> Client:
    c = Client(id=uuid.uuid4(), name=name, hubspot_company_id=f"COMP-{name}")
    session.add(c)
    await session.commit()
    return c


async def _seed_opportunity(
    session,
    owner: User,
    *,
    client_id: uuid.UUID | None = None,
    governance_status: str = "SOWDraft",
) -> Opportunity:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-DB-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        client_id=client_id,
        governance_status=governance_status,
    )
    session.add(opp)
    await session.commit()
    return opp


async def _seed_gm_model(
    session,
    *,
    opportunity: Opportunity,
    revenue_us: Decimal,
    revenue_india: Decimal,
    cost_us: Decimal,
    cost_india: Decimal,
    engagement_type: str = "tm",
) -> GmModel:
    """Persist a gm_model + 2 resource lines that sum to the target totals.

    The Builder computes revenue/cost from hours * rate * allocation. To make
    the totals deterministic across templates and locations we pin
    ``hours_billable=1``, ``allocation_pct=1``, then set ``hourly_bill_rate``
    to the target revenue and ``hourly_cost`` to the target cost. Any resource
    line where the revenue is zero is skipped.
    """

    model = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        engagement_type=engagement_type,
        revenue_us=revenue_us,
        revenue_india=revenue_india,
    )
    session.add(model)
    await session.flush()
    start = date(2026, 3, 1)
    end = date(2026, 8, 31)
    if revenue_us > 0 or cost_us > 0:
        session.add(
            ResourceLine(
                id=uuid.uuid4(),
                gm_model_id=model.id,
                role="Engineer",
                seniority="senior",
                location="US",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                billable_hours=Decimal("1"),
                hourly_bill_rate=revenue_us,
                hourly_loaded_cost=cost_us,
                hourly_cost=cost_us,
                person_name="Alice",
                validated_by=uuid.uuid4(),
            )
        )
    if revenue_india > 0 or cost_india > 0:
        session.add(
            ResourceLine(
                id=uuid.uuid4(),
                gm_model_id=model.id,
                role="Engineer",
                seniority="senior",
                location="India",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                billable_hours=Decimal("1"),
                hourly_bill_rate=revenue_india,
                hourly_loaded_cost=cost_india,
                hourly_cost=cost_india,
                person_name="Bob",
                validated_by=uuid.uuid4(),
            )
        )
    await session.commit()
    return model


# ---- role gates ---------------------------------------------------------


async def test_sales_cannot_read_ceo_view(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/dashboards/ceo", headers={"X-Test-User": "sales@smartek21.com"}
        )
    assert r.status_code == 403


async def test_ceo_can_read_ceo_view(app_with_session, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    await _seed_user(session, "ceo@smartek21.com", ["CEO"])
    async with _client(app_with_session) as c:
        r = await c.get(
            "/dashboards/ceo", headers={"X-Test-User": "ceo@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    # All five widgets present, empty lists not None so the browser can
    # render an EmptyState without special-casing null.
    for key in (
        "pipeline_value",
        "approved_vs_forecast_gp",
        "below_floor_deals",
        "ceo_exceptions_pending",
        "revenue_expiring_in_90_days",
    ):
        assert key in body
    assert isinstance(body["below_floor_deals"], list)
    assert isinstance(body["ceo_exceptions_pending"], list)
    assert isinstance(body["revenue_expiring_in_90_days"], list)


async def test_finance_role_gate(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/dashboards/finance", headers={"X-Test-User": "sales@smartek21.com"}
        )
    assert r.status_code == 403


async def test_hr_role_gate(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/dashboards/hr", headers={"X-Test-User": "hr@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["demand_by_skill"] == []


async def test_system_admin_sees_every_view(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        for path in (
            "/dashboards/ceo",
            "/dashboards/finance",
            "/dashboards/delivery",
            "/dashboards/sales",
            "/dashboards/hr",
            "/dashboards/legal",
        ):
            r = await c.get(path, headers={"X-Test-User": "admin@smartek21.com"})
            assert r.status_code == 200, path


# ---- CEO empty-widget contract ------------------------------------------


async def test_ceo_view_returns_empty_lists_not_nulls_on_empty_db(session):
    body = await ceo_view(session)
    assert body["below_floor_deals"] == []
    assert body["ceo_exceptions_pending"] == []
    assert body["revenue_expiring_in_90_days"] == []
    # Aggregations degrade to zero, stringified.
    assert body["pipeline_value"] == "0"
    assert body["approved_vs_forecast_gp"]["approved_gp"] == "0"
    assert body["approved_vs_forecast_gp"]["forecast_gp"] == "0"


# ---- Client SOW/GM aggregation (THE test) -------------------------------


async def test_client_sow_gm_uses_sum_of_gp_over_sum_of_revenue(session):
    """Given 2 SOWs:

    * SOW A: revenue $100k US / $60k India; cost $65k US / $30k India.
    * SOW B: revenue $50k US; cost $20k US.

    Client GM must equal:

        (100-65 + 60-30 + 50-20) / (100+60+50)
            = (35 + 30 + 30) / 210
            = 95 / 210

    And it must NOT equal mean of percentages:

        (0.35 + 0.5 + 0.6) / 3 ≈ 0.4833...

    Assert both — a broken aggregation would trip the second check.
    """

    owner = await _seed_user(session, "sales@smartek21.com", ["Sales"])
    client = await _seed_client(session, "Acme")
    opp_a = await _seed_opportunity(session, owner, client_id=client.id)
    opp_b = await _seed_opportunity(session, owner, client_id=client.id)

    await _seed_gm_model(
        session,
        opportunity=opp_a,
        revenue_us=Decimal("100000"),
        revenue_india=Decimal("60000"),
        cost_us=Decimal("65000"),
        cost_india=Decimal("30000"),
    )
    await _seed_gm_model(
        session,
        opportunity=opp_b,
        revenue_us=Decimal("50000"),
        revenue_india=Decimal("0"),
        cost_us=Decimal("20000"),
        cost_india=Decimal("0"),
    )

    body = await client_sow_gm_view(session, client.id)

    assert body["client_name"] == "Acme"
    assert len(body["rows"]) == 2

    expected_gm = Decimal("95") / Decimal("210")
    got_gm = Decimal(body["totals"]["client_gm"])
    # Precise Decimal equality — no round-trip through float.
    assert got_gm == expected_gm

    # Sanity: mean-of-percentages would land elsewhere.
    mean_of_pct = (
        Decimal("0.35") + Decimal("0.5") + Decimal("0.6")
    ) / Decimal("3")
    assert got_gm != mean_of_pct

    # Totals row echoes the aggregation inputs (Decimal roundtrip through
    # NUMERIC(14,2) preserves the 2dp scale on stringification).
    assert Decimal(body["totals"]["revenue"]) == Decimal("210000")
    assert Decimal(body["totals"]["gross_profit"]) == Decimal("95000")
    assert "SUM(gross_profit_us + gross_profit_india)" in body["totals"]["formula"]


async def test_client_sow_gm_row_exposes_per_sow_fields(session):
    owner = await _seed_user(session, "s@smartek21.com", ["Sales"])
    client = await _seed_client(session, "Beta")
    opp = await _seed_opportunity(session, owner, client_id=client.id)
    await _seed_gm_model(
        session,
        opportunity=opp,
        revenue_us=Decimal("100000"),
        revenue_india=Decimal("0"),
        cost_us=Decimal("60000"),
        cost_india=Decimal("0"),
    )
    body = await client_sow_gm_view(session, client.id)
    (row,) = body["rows"]
    # dates + value + US/India cost + approved/forecast/actual GM + exception flag
    for key in (
        "start_date",
        "end_date",
        "revenue_us",
        "revenue_india",
        "cost_us",
        "cost_india",
        "approved_gm",
        "forecast_gm",
        "actual_gm",
        "exception_flag",
    ):
        assert key in row
    # No package released -> approved_gm is null; forecast_gm is 0.4.
    assert row["approved_gm"] is None
    assert Decimal(row["forecast_gm"]) == Decimal("0.4")
    assert row["actual_gm"] == "0"


async def test_client_sow_gm_endpoint_requires_governance_role(
    app_with_session, session, monkeypatch
):
    client = await _seed_client(session, "Gamma")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/dashboards/client/{client.id}",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 403


async def test_client_sow_gm_endpoint_ok_for_finance(
    app_with_session, session, monkeypatch
):
    owner = await _seed_user(session, "sales2@smartek21.com", ["Sales"])
    client = await _seed_client(session, "Delta")
    opp = await _seed_opportunity(session, owner, client_id=client.id)
    await _seed_gm_model(
        session,
        opportunity=opp,
        revenue_us=Decimal("100000"),
        revenue_india=Decimal("0"),
        cost_us=Decimal("65000"),
        cost_india=Decimal("0"),
    )
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/dashboards/client/{client.id}",
            headers={"X-Test-User": "fin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["client_gm"] is not None


# ---- Finance widgets ----------------------------------------------------


async def test_finance_view_missing_cost_inputs_flags_gm_models_with_null_cost(
    session,
):
    owner = await _seed_user(session, "salesf@smartek21.com", ["Sales"])
    opp = await _seed_opportunity(session, owner)
    # Build a gm_model but null out the hourly_cost on the sole resource line.
    model = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        engagement_type="tm",
        revenue_us=Decimal("100"),
        revenue_india=Decimal("0"),
    )
    session.add(model)
    await session.flush()
    session.add(
        ResourceLine(
            id=uuid.uuid4(),
            gm_model_id=model.id,
            role="Engineer",
            seniority="senior",
            location="US",
            allocation_pct=Decimal("1"),
            start_date=date(2026, 3, 1),
            end_date=date(2026, 8, 31),
            billable_hours=Decimal("1"),
            hourly_bill_rate=Decimal("100"),
            hourly_loaded_cost=Decimal("0"),
            hourly_cost=None,
            person_name="Alice",
            validated_by=uuid.uuid4(),
        )
    )
    await session.commit()

    body = await finance_view(session)
    assert any(
        row["gm_model_id"] == str(model.id) for row in body["missing_cost_inputs"]
    )


async def test_finance_view_gm_by_geography_uses_server_totals(session):
    owner = await _seed_user(session, "salesg@smartek21.com", ["Sales"])
    opp = await _seed_opportunity(session, owner)
    await _seed_gm_model(
        session,
        opportunity=opp,
        revenue_us=Decimal("100"),
        revenue_india=Decimal("100"),
        cost_us=Decimal("50"),
        cost_india=Decimal("40"),
    )
    body = await finance_view(session)
    assert Decimal(body["gm_by_geography"]["US"]["gm"]) == Decimal("0.5")
    assert Decimal(body["gm_by_geography"]["India"]["gm"]) == Decimal("0.6")


# ---- Sales view ---------------------------------------------------------


async def test_sales_view_scopes_to_owner(app_with_session, session, monkeypatch):
    me = await _seed_user(session, "me@smartek21.com", ["Sales"])
    other = await _seed_user(session, "other@smartek21.com", ["Sales"])
    mine = await _seed_opportunity(session, me)
    theirs = await _seed_opportunity(session, other)
    _ = theirs

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/dashboards/sales", headers={"X-Test-User": "me@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    ids = {row["id"] for row in body["my_deals"]}
    assert str(mine.id) in ids
    assert str(theirs.id) not in ids


# ---- Delivery / Legal / HR smoke ----------------------------------------


async def test_delivery_view_returns_expected_keys(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/dashboards/delivery", headers={"X-Test-User": "d@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    for key in (
        "estimates_awaiting_review",
        "staffing_gaps",
        "upcoming_starts",
        "effort_variance",
    ):
        assert key in body
        assert isinstance(body[key], list)


async def test_legal_view_returns_expected_keys(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/dashboards/legal", headers={"X-Test-User": "l@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert "nda_msa_coverage_summary" in body
    assert isinstance(body["packages_awaiting_legal"], list)
    assert isinstance(body["notice_dates_approaching"], list)


# Silence unused-import guard: kept to make the imports greppable.
_ = datetime
_ = timedelta
_ = UTC
_ = CostLine
_ = Any
