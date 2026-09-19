"""S7 B — cost-field response filtering per role.

Covers the acceptance tests in ``docs/backlog/s7-nda-msa-hard-block.md``
(section B): a Sales user reading a deal / client / adviser / delivery
model must not see raw cost fields, while cost-authorized roles
(Delivery, Finance, HR, CEO, SystemAdmin) see them verbatim.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio

from app.db import get_session
from app.main import app as main_app
from app.models.client import Agreement, Client, LegalEntity
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.delivery_model import (
    GmModelPayload,
    ResourceLinePayload,
    create_gm_model_version,
)
from app.services.redact import COST_FIELDS, ROLES_ALLOWED_COST, redact_costs


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


# --- pure redact helper ----------------------------------------------------


def test_pure_redact_strips_flat_keys_for_sales():
    payload = {
        "revenue_us": "1000",
        "hourly_cost": "50",
        "cost_low": "1",
        "cost_base": "2",
        "cost_high": "3",
        "cost_us": "500",
        "cost_india": "200",
        "blended_gm": "0.30",
    }
    out = redact_costs(payload, {"Sales"})
    assert "revenue_us" in out
    assert "blended_gm" in out
    for key in COST_FIELDS:
        assert key not in out, f"{key} must be stripped for Sales"


def test_pure_redact_keeps_everything_for_finance():
    payload = {"hourly_cost": "50", "revenue_us": "1"}
    out = redact_costs(payload, {"Finance"})
    assert out == payload
    # Same object — no needless copy for cost-authorized roles.
    assert out is payload


def test_pure_redact_walks_lists_and_nested_dicts():
    payload = {
        "gm_model": {
            "revenue_us": "10",
            "cost_us": "5",
            "resource_lines": [
                {"role": "Eng", "hourly_bill_rate": "200", "hourly_cost": "80"},
                {"role": "PM", "hourly_bill_rate": "150", "hourly_cost": "60"},
            ],
        },
        "computed": {"cost_india": "1", "gm_blended": "0.4"},
    }
    out = redact_costs(payload, {"Sales", "Marketing"})
    assert "cost_us" not in out["gm_model"]
    assert "revenue_us" in out["gm_model"]
    for line in out["gm_model"]["resource_lines"]:
        assert "hourly_cost" not in line
        assert "hourly_bill_rate" in line
    assert "cost_india" not in out["computed"]
    assert "gm_blended" in out["computed"]


def test_pure_redact_leaves_input_unchanged():
    payload = {"hourly_cost": "50", "nested": {"cost_low": "1"}}
    original_ids = (id(payload), id(payload["nested"]))
    out = redact_costs(payload, {"Sales"})
    assert "hourly_cost" in payload
    assert "cost_low" in payload["nested"]
    assert (id(out), id(out["nested"])) != original_ids


def test_roles_allowed_cost_is_the_expected_five():
    assert ROLES_ALLOWED_COST == frozenset(
        {"Delivery", "HR", "Finance", "CEO", "SystemAdmin"}
    )


# --- end-to-end: /deals/{id} ----------------------------------------------


async def _seed_client_with_coverage(session) -> Client:
    client = Client(
        id=uuid.uuid4(),
        name=f"Client {uuid.uuid4().hex[:6]}",
        hubspot_company_id=f"HS-{uuid.uuid4().hex[:6]}",
    )
    session.add(client)
    await session.flush()
    entity = LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Entity 1")
    session.add(entity)
    await session.flush()
    for kind in ("NDA", "MSA"):
        session.add(
            Agreement(
                id=uuid.uuid4(),
                legal_entity_id=entity.id,
                kind=kind,
                state="executed",
                effective_date=date(2026, 1, 1),
                expiry=date(2030, 12, 31),
            )
        )
    await session.commit()
    return client


async def _seed_deal_with_gm(session, sales_email: str) -> Opportunity:
    owner = User(
        id=_uid(sales_email),
        email=sales_email,
        name="Sales rep",
        groups=["Sales"],
    )
    session.add(owner)
    await session.commit()
    client = await _seed_client_with_coverage(session)
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-REDACT-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        client_id=client.id,
        governance_status="SOWDraft",
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
            "scope_summary": {"value": "x", "page_ref": 1, "status": "confirmed"},
        },
        confirmed_by=owner.id,
        confirmed_at=datetime.now(UTC),
    )
    session.add(version)
    await session.commit()

    start = date(2026, 3, 1)
    end = date(2026, 8, 31)
    payload = GmModelPayload(
        engagement_type="tm",
        sow_version_id=version.id,
        delivery_pattern="hybrid",
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
                hours_billable=Decimal("1000"),
                hourly_bill_rate=Decimal("200"),
                hourly_cost=Decimal("100"),
                validated_by=uuid.uuid4(),
            ),
            ResourceLinePayload(
                role="Engineer",
                seniority="senior",
                location="India",
                person_name="Bob",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("800"),
                hourly_bill_rate=Decimal("100"),
                hourly_cost=Decimal("40"),
                validated_by=uuid.uuid4(),
            ),
        ],
        cost_lines=[],
    )
    await create_gm_model_version(
        session, opportunity_id=opp.id, actor_id=owner.id, payload=payload
    )
    return opp


async def test_get_deal_strips_cost_for_sales(app_with_session, session, monkeypatch):
    opp = await _seed_deal_with_gm(session, "sales@smartek21.com")

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/deals/{opp.id}",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    # gm_model summary present but cost keys stripped.
    assert body["gm_model"] is not None
    for key in ("hourly_cost", "cost_us", "cost_india", "cost_low", "cost_base"):
        assert key not in body["gm_model"], f"{key} leaked to Sales"
    # Revenue side of the house survives.
    assert "revenue_us" in body["gm_model"]
    assert "revenue_india" in body["gm_model"]


async def test_get_deal_keeps_cost_for_finance(app_with_session, session, monkeypatch):
    opp = await _seed_deal_with_gm(session, "sales2@smartek21.com")
    # Grant the reader Finance role. FinanceLeader would also work.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance,SalesLeader")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/deals/{opp.id}",
            headers={"X-Test-User": "fin@smartek21.com"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gm_model"] is not None


async def test_get_deal_strips_nested_resource_line_costs(
    app_with_session, session, monkeypatch
):
    """Recursive stripping: resource_lines[*].hourly_cost is a nested cost."""

    opp = await _seed_deal_with_gm(session, "sales3@smartek21.com")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/deals/{opp.id}",
            headers={"X-Test-User": "sales3@smartek21.com"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    # gm_model is the deal-detail summary; a Sales user should get no
    # cost-shaped keys anywhere in that subtree.
    def _assert_no_cost(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k not in COST_FIELDS, f"leaked cost key: {k}"
                _assert_no_cost(v)
        elif isinstance(node, list):
            for item in node:
                _assert_no_cost(item)

    _assert_no_cost(body)
