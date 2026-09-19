"""S7 wave 2 — Reusable delivery-model templates (story B).

Blueprint §7 rule: templates NEVER carry cost values. The Builder
reaches for the active rate card whenever it needs a cost — the
template only carries shape (phases, role/seniority/location, relative
hours, and bill rate).
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
from app.models.gm_model import GmModel, ResourceLine
from app.models.gm_model_phase import GmModelPhase
from app.models.gm_model_template import GmModelTemplate
from app.models.opportunity import Opportunity


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


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


@pytest_asyncio.fixture
async def opportunity(session) -> Opportunity:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="H-TPL-001",
        owner_id=None,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return opp


@pytest_asyncio.fixture
async def opportunity_two(session) -> Opportunity:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="H-TPL-002",
        owner_id=None,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return opp


def _model_payload_two_phases() -> dict:
    start = date(2026, 3, 1)
    end = date(2026, 8, 31)
    return {
        "engagement_type": "fixed_price",
        "delivery_pattern": "onshore-led",
        "phases": [
            {"name": "Discovery", "order": 0, "sow_deliverable_ref": "D1"},
            {"name": "Build", "order": 1},
        ],
        "resource_lines": [
            {
                "role": "Engineer",
                "seniority": "Sr",
                "location": "US",
                "person_name": "Alice",
                "allocation_pct": "1",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "hours_billable": "100",
                "hourly_bill_rate": "150",
                "hourly_cost": "80",
                "validated_by": str(uuid.uuid4()),
                "phase_name": "Discovery",
            },
            {
                "role": "Engineer",
                "seniority": "Sr",
                "location": "India",
                "person_name": "Bob",
                "allocation_pct": "1",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "hours_billable": "200",
                "hourly_bill_rate": "80",
                "hourly_cost": "40",
                "validated_by": str(uuid.uuid4()),
                "phase_name": "Build",
            },
        ],
        "cost_lines": [
            {
                "category": "tools",
                "amount": "500",
                "location": "US",
                "phase_name": "Build",
            }
        ],
        "total_price": "38000",
        "revenue_us": "15000",
        "revenue_india": "23000",
    }


async def _seed_model(app, opportunity) -> str:
    async with _client(app) as c:
        r = await c.post(
            f"/delivery-model/{opportunity.id}/versions",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json=_model_payload_two_phases(),
        )
    assert r.status_code == 201, r.text
    return r.json()["gm_model"]["id"]


async def test_save_as_template_omits_cost_values(
    app_with_session, session, opportunity, monkeypatch
):
    """Story B: template_json carries phases + resource_lines shape but
    NEVER an ``hourly_cost`` (blueprint §7)."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    gm_id = await _seed_model(app_with_session, opportunity)

    async with _client(app_with_session) as c:
        r = await c.post(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"gm_model_id": gm_id, "name": "Standard hybrid FP"},
        )
    assert r.status_code == 201, r.text
    payload = r.json()["template"]
    assert payload["engagement_type"] == "fixed_price"
    assert payload["phase_count"] == 2
    assert payload["resource_line_count"] == 2

    tpl = (
        await session.execute(select(GmModelTemplate))
    ).scalar_one()
    tj = tpl.template_json
    assert [p["name"] for p in tj["phases"]] == ["Discovery", "Build"]
    # Cost field absent from every resource_line — blueprint §7 rule.
    for r in tj["resource_lines"]:
        assert "hourly_cost" not in r
        # Shape fields present.
        assert set(r.keys()) >= {
            "phase_name",
            "role",
            "seniority",
            "location",
            "allocation_pct",
            "hours_billable",
            "hourly_bill_rate",
        }
    # phase_name pins each line to a phase by name (join key at seed).
    names = sorted(r["phase_name"] for r in tj["resource_lines"])
    assert names == ["Build", "Discovery"]

    # cost_lines carry money (non-labor costs; NOT hourly cost) but do
    # persist their own amount — the blueprint rule bans HOURLY cost only.
    assert len(tj["cost_lines"]) == 1
    assert tj["cost_lines"][0]["phase_name"] == "Build"

    # Audit landed.
    audits = (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "gm_model_template.created"
            )
        )
    ).scalars().all()
    assert len(audits) == 1
    assert audits[0].after["name"] == "Standard hybrid FP"


async def test_save_template_rejects_duplicate_name(
    app_with_session, session, opportunity, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    gm_id = await _seed_model(app_with_session, opportunity)
    async with _client(app_with_session) as c:
        r1 = await c.post(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"gm_model_id": gm_id, "name": "Dup"},
        )
        assert r1.status_code == 201
        r2 = await c.post(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"gm_model_id": gm_id, "name": "Dup"},
        )
    assert r2.status_code == 422


async def test_list_templates_filter_by_engagement_type(
    app_with_session, opportunity, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    gm_id = await _seed_model(app_with_session, opportunity)
    async with _client(app_with_session) as c:
        await c.post(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"gm_model_id": gm_id, "name": "FP One"},
        )
        r_all = await c.get(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
        )
        r_fp = await c.get(
            "/delivery-model/templates?engagement_type=fixed_price",
            headers={"X-Test-User": "delivery@smartek21.com"},
        )
        r_sa = await c.get(
            "/delivery-model/templates?engagement_type=staff_aug",
            headers={"X-Test-User": "delivery@smartek21.com"},
        )
    assert r_all.status_code == 200
    assert r_fp.status_code == 200
    assert r_sa.status_code == 200
    assert len(r_all.json()["items"]) == 1
    assert len(r_fp.json()["items"]) == 1
    assert len(r_sa.json()["items"]) == 0


async def test_list_templates_presales_can_read(
    app_with_session, opportunity, monkeypatch
):
    """Presales can pick a template when starting a new opportunity."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    gm_id = await _seed_model(app_with_session, opportunity)
    async with _client(app_with_session) as c:
        await c.post(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"gm_model_id": gm_id, "name": "For Presales"},
        )
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Presales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/delivery-model/templates",
            headers={"X-Test-User": "presales@smartek21.com"},
        )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


async def test_seed_from_template_creates_draft_with_null_costs(
    app_with_session,
    session,
    opportunity,
    opportunity_two,
    monkeypatch,
):
    """Story B AC: seeding a template on a fresh opp creates a gm_model
    draft with phases + resource_lines whose ``hourly_cost`` is NULL.

    Cost bands are populated on Builder open via the active rate card —
    this test just verifies the null-init contract."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    src_gm_id = await _seed_model(app_with_session, opportunity)

    # Save-as-template on the source.
    async with _client(app_with_session) as c:
        r = await c.post(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"gm_model_id": src_gm_id, "name": "Seedable"},
        )
    tpl_id = r.json()["template"]["id"]

    # Seed onto a different opportunity.
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/delivery-model/{opportunity_two.id}/from-template/{tpl_id}",
            headers={"X-Test-User": "delivery@smartek21.com"},
        )
    assert r.status_code == 201, r.text
    new_gm = r.json()["gm_model"]
    assert new_gm["engagement_type"] == "fixed_price"
    assert [p["name"] for p in new_gm["phases"]] == ["Discovery", "Build"]

    # DB round-trip: new gm_model exists on opportunity_two, resource_lines
    # inherit the shape but ``hourly_cost`` is NULL (no rate card seeded in
    # the test fixture — the fallback in create_gm_model_version has
    # nothing to look up so the column stays null).
    rows = (
        await session.execute(
            select(ResourceLine).join(GmModel).where(
                GmModel.opportunity_id == opportunity_two.id
            )
        )
    ).scalars().all()
    assert len(rows) == 2
    for r in rows:
        assert r.hourly_cost is None
        assert r.phase_id is not None  # phases wired through by name

    # Every seeded line was cloned as "to hire" (person_name null).
    assert all(r.person_name is None for r in rows)

    # Bill rate carried through the template (shape, not cost).
    bills = sorted(r.hourly_bill_rate for r in rows)
    assert bills == [Decimal("80.0000"), Decimal("150.0000")]

    # Audit chain: both the create + seeded_from_template rows landed.
    seeded_audits = (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "gm_model.seeded_from_template"
            )
        )
    ).scalars().all()
    assert len(seeded_audits) == 1
    assert seeded_audits[0].after["template_id"] == tpl_id


async def test_seed_forbidden_for_sales(
    app_with_session, opportunity_two, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/delivery-model/{opportunity_two.id}/from-template/{uuid.uuid4()}",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 403


async def test_delete_template_soft_deletes_and_audits(
    app_with_session, session, opportunity, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    gm_id = await _seed_model(app_with_session, opportunity)
    async with _client(app_with_session) as c:
        r = await c.post(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"gm_model_id": gm_id, "name": "ToDelete"},
        )
        tpl_id = r.json()["template"]["id"]
        r_del = await c.delete(
            f"/delivery-model/templates/{tpl_id}",
            headers={"X-Test-User": "delivery@smartek21.com"},
        )
    assert r_del.status_code == 204

    tpl = (
        await session.execute(select(GmModelTemplate))
    ).scalar_one()
    assert tpl.active is False

    # List omits inactive.
    async with _client(app_with_session) as c:
        r_list = await c.get(
            "/delivery-model/templates",
            headers={"X-Test-User": "delivery@smartek21.com"},
        )
    assert r_list.status_code == 200
    assert len(r_list.json()["items"]) == 0

    audits = (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "gm_model_template.deleted"
            )
        )
    ).scalars().all()
    assert len(audits) == 1
