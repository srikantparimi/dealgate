"""S7 wave 2 — WBS phases story A.

Given/When/Then per acceptance criterion in
``docs/backlog/s7-wbs-and-templates.md``.

Every case round-trips through the ratified HTTP path so the router's
permission gate, the service's write path, and the audit emission all
line up. Cost/revenue math stays inside ``app.gm`` (CLAUDE.md rule 2).
"""

from __future__ import annotations

import uuid
from datetime import date

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.models.gm_model_phase import GmModelPhase
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
        hubspot_deal_id="H-WBS-001",
        owner_id=None,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return opp


def _payload_with_phases() -> dict:
    """Fixed-price case with 2 phases and 3 resource_lines linked by name.

    Discovery: 1 line (US Sr Engineer).
    Build:     2 lines (US + India Engineers).
    """

    start = date(2026, 3, 1)
    end = date(2026, 8, 31)
    return {
        "engagement_type": "fixed_price",
        "delivery_pattern": "hybrid",
        "phases": [
            {"name": "Discovery", "order": 0, "sow_deliverable_ref": "D1"},
            {"name": "Build", "order": 1, "description": "Core build phase"},
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
                "location": "US",
                "person_name": "Bob",
                "allocation_pct": "1",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "hours_billable": "400",
                "hourly_bill_rate": "150",
                "hourly_cost": "80",
                "validated_by": str(uuid.uuid4()),
                "phase_name": "Build",
            },
            {
                "role": "Engineer",
                "seniority": "Sr",
                "location": "India",
                "person_name": "Carol",
                "allocation_pct": "1",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "hours_billable": "300",
                "hourly_bill_rate": "80",
                "hourly_cost": "40",
                "validated_by": str(uuid.uuid4()),
                "phase_name": "Build",
            },
        ],
        "cost_lines": [],
        "total_price": "100000",
        "revenue_us": "75000",
        "revenue_india": "25000",
    }


async def test_save_with_phases_wires_resource_lines_by_name(
    app_with_session, session, opportunity, monkeypatch
):
    """Story A: creating a model with N phases + M lines resolves phase_id
    by name on every line that names a phase."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/delivery-model/{opportunity.id}/versions",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json=_payload_with_phases(),
        )
    assert r.status_code == 201, r.text
    body = r.json()

    # Response echoes the phases + phase_summary widget.
    phases = body["gm_model"]["phases"]
    assert [p["name"] for p in phases] == ["Discovery", "Build"]
    assert [p["order"] for p in phases] == [0, 1]

    # phase_summary carries revenue + cost per phase.
    summary = {b["name"]: b for b in body["gm_model"]["phase_summary"]}
    assert set(summary.keys()) == {"Discovery", "Build"}
    # Discovery: 1 US line — no cost is stripped for Delivery, kept here.
    # 100h * $150 * 1.0 = $15,000 revenue.
    from decimal import Decimal

    assert Decimal(summary["Discovery"]["revenue"]) == Decimal("15000")
    # Build: (400*150) + (300*80) = 60,000 + 24,000 = 84,000.
    assert Decimal(summary["Build"]["revenue"]) == Decimal("84000")

    # DB check: every resource_line has a phase_id.
    gm_row = (await session.execute(select(GmModel))).scalar_one()
    rows = (
        await session.execute(
            select(ResourceLine).where(ResourceLine.gm_model_id == gm_row.id)
        )
    ).scalars().all()
    assert len(rows) == 3
    assert all(r.phase_id is not None for r in rows)

    phase_by_id = {
        p.id: p
        for p in (
            await session.execute(
                select(GmModelPhase).where(GmModelPhase.gm_model_id == gm_row.id)
            )
        ).scalars().all()
    }
    discovery_rows = [r for r in rows if phase_by_id[r.phase_id].name == "Discovery"]
    build_rows = [r for r in rows if phase_by_id[r.phase_id].name == "Build"]
    assert len(discovery_rows) == 1
    assert len(build_rows) == 2


async def test_reorder_phases_updates_order_and_audits(
    app_with_session, session, opportunity, monkeypatch
):
    """Story A: PATCH .../phases/reorder rewrites ``order`` + emits an
    audit row keyed off ``gm_model.phases_reordered``."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    # Seed.
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/delivery-model/{opportunity.id}/versions",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json=_payload_with_phases(),
        )
    assert r.status_code == 201
    phases = r.json()["gm_model"]["phases"]
    discovery_id = next(p["id"] for p in phases if p["name"] == "Discovery")
    build_id = next(p["id"] for p in phases if p["name"] == "Build")

    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/delivery-model/{opportunity.id}/phases/reorder",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"ordered_phase_ids": [build_id, discovery_id]},
        )
    assert r.status_code == 200, r.text
    new = {p["name"]: p["order"] for p in r.json()["phases"]}
    assert new["Build"] == 0
    assert new["Discovery"] == 1

    # DB round-trip.
    session.expire_all()
    rows = (
        await session.execute(
            select(GmModelPhase).order_by(GmModelPhase.order)
        )
    ).scalars().all()
    assert [r.name for r in rows] == ["Build", "Discovery"]

    # Audit event landed.
    audit_rows = (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "gm_model.phases_reordered"
            )
        )
    ).scalars().all()
    assert len(audit_rows) == 1
    assert audit_rows[0].after["phases"][0]["id"] == build_id


async def test_reorder_rejects_bad_id_set(
    app_with_session, session, opportunity, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as c:
        await c.post(
            f"/delivery-model/{opportunity.id}/versions",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json=_payload_with_phases(),
        )
        # Pass a random id that does not belong to this model.
        r = await c.patch(
            f"/delivery-model/{opportunity.id}/phases/reorder",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json={"ordered_phase_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
        )
    assert r.status_code == 422


async def test_reorder_forbidden_for_sales(
    app_with_session, opportunity, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/delivery-model/{opportunity.id}/phases/reorder",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"ordered_phase_ids": []},
        )
    assert r.status_code == 403


async def test_legacy_lines_without_phase_land_in_ungrouped(
    app_with_session, session, opportunity, monkeypatch
):
    """Story A: rows saved without a ``phase_name`` are still readable and
    surface in a synthetic "Ungrouped" bucket in the phase summary."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")

    payload = _payload_with_phases()
    # Drop phases and phase_name from every line — simulates the legacy
    # save path (or a pre-S7 imported gm_model).
    payload["phases"] = []
    for r in payload["resource_lines"]:
        r.pop("phase_name", None)

    async with _client(app_with_session) as c:
        r = await c.post(
            f"/delivery-model/{opportunity.id}/versions",
            headers={"X-Test-User": "delivery@smartek21.com"},
            json=payload,
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["gm_model"]["phases"] == []
    summary = body["gm_model"]["phase_summary"]
    assert len(summary) == 1
    assert summary[0]["name"] == "Ungrouped"
    assert summary[0]["phase_id"] is None

    # DB rows have NULL phase_id.
    rows = (await session.execute(select(ResourceLine))).scalars().all()
    assert all(r.phase_id is None for r in rows)
