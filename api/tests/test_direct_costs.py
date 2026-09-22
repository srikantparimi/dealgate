"""S13b: direct costs use the same GM preview, saved versions and export."""

from decimal import Decimal
from dataclasses import replace
from io import BytesIO
import uuid

import openpyxl
import httpx
import pytest

from app.models.opportunity import Opportunity
from app.services.delivery_model import (
    _extra_inputs_for_model, _model_to_payload, build_compute_response,
    build_xlsx, compute_live, create_gm_model_version, parse_gm_model_payload,
    serialize_gm_model,
)
from app.db import get_session
from app.main import app


def fixture_payload(costs=None):
    return {
        "engagement_type": "fixed_price", "total_price": "50000",
        "resource_lines": [{
            "role": "Engineer", "seniority": "Senior", "location": "US",
            "person_name": "Fixture engineer", "allocation_pct": "1",
            "start_date": "2026-10-01", "end_date": "2026-10-31",
            "hours_billable": "240", "hourly_bill_rate": "0", "hourly_cost": "120",
        }],
        "cost_lines": costs or [],
    }


def cost(**changes):
    return {"category": "software", "note": "Project licenses", "amount": "1000",
            "basis": "amount", "basis_value": "1000", "location": "proportional",
            "reimbursable": False, "provenance": "manual", **changes}


def test_direct_cost_and_pass_through_finance_summary():
    payload = parse_gm_model_payload(fixture_payload([
        cost(), cost(category="travel", amount="2300", basis_value="2300", reimbursable=True),
    ]))
    response = build_compute_response(compute_live(payload))
    assert Decimal(response["gm_us"]) == Decimal("0.404")
    summary = response["finance_summary"]
    for key, expected in {
        "revenue": "50000", "labor_cost": "28800", "direct_cost": "1000",
        "total_delivery_cost": "29800", "gross_profit": "20200",
        "labor_pct": "0.576", "direct_pct": "0.02", "total_cost_pct": "0.596",
        "pass_through": "2300",
    }.items():
        assert Decimal(summary[key]) == Decimal(expected), key
    assert response["policy"]["us_applicable"] is True
    assert response["policy"]["india_applicable"] is False


def test_percentage_computed_server_side_and_proportional_split():
    raw = fixture_payload([cost(basis="percent_revenue", basis_value="2", amount="999999")])
    raw["resource_lines"].append({**raw["resource_lines"][0], "location": "India", "hourly_cost": "40"})
    response = build_compute_response(compute_live(parse_gm_model_payload(raw)))
    assert Decimal(response["finance_summary"]["direct_cost"]) == Decimal("1000")
    assert Decimal(response["cost_us"]) == Decimal("29550")
    assert Decimal(response["cost_india"]) == Decimal("9850")
    assert response["policy"]["india_applicable"] is True


@pytest.mark.parametrize("changes", [
    {"basis_value": "NaN"}, {"basis_value": "Infinity"}, {"basis_value": "-1"},
    {"location": "elsewhere"}, {"basis": "made_up"}, {"reimbursable": "false"},
])
def test_invalid_direct_cost_rejected(changes):
    with pytest.raises(ValueError):
        parse_gm_model_payload(fixture_payload([cost(**changes)]))


def test_missing_labor_cost_cannot_be_presented_as_final_or_proportionally_allocated():
    raw = fixture_payload([cost(location="US")])
    raw["resource_lines"][0]["hourly_cost"] = None
    response = build_compute_response(compute_live(parse_gm_model_payload(raw)))
    assert response["complete"] is False
    for key in ("labor_cost", "total_delivery_cost", "gross_profit", "labor_pct", "total_cost_pct"):
        assert response["finance_summary"][key] is None
    raw["cost_lines"][0]["location"] = "proportional"
    with pytest.raises(ValueError, match="complete, positive labor costs"):
        compute_live(parse_gm_model_payload(raw))


def test_raw_extracted_direct_costs_are_redacted_for_sales():
    from app.services.redact import redact_costs
    payload = {"sow_version": {"extracted_fields": {"direct_costs": [cost()]}}}
    assert "direct_costs" not in redact_costs(payload, {"Sales"})["sow_version"]["extracted_fields"]


def test_legacy_cost_snapshot_hash_shape_survives_added_columns():
    from types import SimpleNamespace
    from app.services.approvals import _cost_line_snapshot
    migrated = SimpleNamespace(category="travel", amount=Decimal("2300.000000000000"),
        location="US", note="Client visit", basis="amount", basis_value=None,
        reimbursable=False, provenance="manual", source_ref=None)
    assert _cost_line_snapshot(migrated) == {
        "category": "travel", "amount": "2300.00", "location": "US", "note": "Client visit",
    }


async def test_saved_cost_basis_is_immutable_and_exported(session):
    opp = Opportunity(id=uuid.uuid4(), hubspot_deal_id="S13B-DIRECT", governance_status="Intake")
    session.add(opp)
    await session.commit()
    first = await create_gm_model_version(session, opportunity_id=opp.id, actor_id=None,
        payload=parse_gm_model_payload(fixture_payload([
            cost(basis="percent_revenue", basis_value="2", amount="999999"),
            cost(category="=1+1", note="=SUM(A1:A2)", basis_value="2300", reimbursable=True, provenance="extracted", source_ref="=1+1"),
        ])))
    second = await create_gm_model_version(session, opportunity_id=opp.id, actor_id=None,
        payload=parse_gm_model_payload(fixture_payload()))
    assert first.id != second.id
    assert second.version == first.version + 1
    serialized = serialize_gm_model(first)
    software = next(c for c in serialized["cost_lines"] if c["category"] == "software")
    assert Decimal(software["amount"]) == Decimal("1000")
    assert Decimal(software["basis_value"]) == Decimal("2")
    result = compute_live(_model_to_payload(first), extra_inputs=_extra_inputs_for_model(first))
    response = build_compute_response(result)
    assert Decimal(response["gm_us"]) == Decimal("0.404")
    workbook = openpyxl.load_workbook(BytesIO(build_xlsx(first, result, response)))
    costs = list(workbook["Costs"].values)
    assert "reimbursable" in costs[0]
    assert "basis_value" in costs[0]
    assert "provenance" in costs[0]
    assert all(cell.data_type != "f" for row in workbook["Costs"] for cell in row)
    assert any(row[0] == "=1+1" for row in costs[1:])
    exported = dict(workbook["Result"].values)
    assert Decimal(exported["pass_through"]) == Decimal("2300")


async def test_live_api_and_cost_permissions(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async def override():
        yield session
    app.dependency_overrides[get_session] = override
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            raw = fixture_payload([cost()])
            preview = await client.post("/delivery-model/preview", headers={"X-Test-User": "delivery@smartek21.com"},
                json={"engagement_type": "fixed_price", "inputs": raw})
            assert preview.status_code == 200, preview.text
            assert Decimal(preview.json()["computed"]["finance_summary"]["gross_profit"]) == Decimal("20200")
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
            denied = await client.post("/delivery-model/preview", headers={"X-Test-User": "sales@smartek21.com"},
                json={"engagement_type": "fixed_price", "inputs": raw})
            assert denied.status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)


async def test_staffing_omitting_costs_preserves_saved_direct_costs(session):
    from app.services.sow_resources import current_resources, update_resources
    opp = Opportunity(id=uuid.uuid4(), hubspot_deal_id="S13B-PRESERVE", governance_status="Intake")
    session.add(opp)
    await session.commit()
    await create_gm_model_version(session, opportunity_id=opp.id, actor_id=None,
        payload=parse_gm_model_payload(fixture_payload([cost()])))
    edited = fixture_payload()
    edited.pop("cost_lines")
    await update_resources(session, opportunity_id=opp.id, actor_id=None, payload=edited)
    saved = await current_resources(session, opp.id)
    assert len(saved["cost_lines"]) == 1
    assert Decimal(saved["margin"]["finance_summary"]["direct_cost"]) == Decimal("1000")
    assert saved["margin"]["gm_version"] == 2


@pytest.mark.parametrize("with_missing_cost", [False, True])
async def test_cost_only_save_preserves_named_validated_staffing_and_phases(session, monkeypatch, with_missing_cost):
    from app.services.sow_resources import current_resources, update_resources
    from app.services.delivery_model import load_gm_model
    opp = Opportunity(id=uuid.uuid4(), hubspot_deal_id="S13B-COST-ONLY", governance_status="Intake")
    session.add(opp)
    await session.commit()
    raw = fixture_payload()
    validator = uuid.uuid4()
    raw["resource_lines"][0].update(validated_by=str(validator), phase_name="Build")
    if with_missing_cost:
        raw["resource_lines"].append({**raw["resource_lines"][0], "role": "Architect", "hourly_cost": None,
                                      "validated_by": None, "hours_billable": "40"})
    raw["phases"] = [{"name": "Build", "order": 0}]
    first = await create_gm_model_version(session, opportunity_id=opp.id, actor_id=None,
        payload=parse_gm_model_payload(raw))
    from types import SimpleNamespace
    async def changed_cost_band(*args):
        return SimpleNamespace(base=Decimal("999"))
    monkeypatch.setattr("app.services.delivery_model._cost_band_for", changed_cost_band)
    changed = await update_resources(session, opportunity_id=opp.id, actor_id=None,
        payload={"engagement_type": "fixed_price", "cost_lines": [cost(location="US")]})
    second = await load_gm_model(session, changed.gm_model_id)
    assert second.resource_lines[0].person_name == first.resource_lines[0].person_name
    assert second.resource_lines[0].validated_by == validator
    assert second.resource_lines[0].hourly_bill_rate == first.resource_lines[0].hourly_bill_rate
    assert second.resource_lines[0].phase_id == second.phases[0].id
    assert second.phases[0].name == "Build"
    state = await current_resources(session, opp.id)
    assert state["resource_lines"][0]["validated_by"] == str(validator)
    if with_missing_cost:
        assert len(second.resource_lines) == 2
        assert second.resource_lines[1].hourly_cost is None
        assert state["margin"]["complete"] is False
        assert state["margin"]["finance_summary"]["gross_profit"] is None
    else:
        assert Decimal(state["margin"]["gm_us"]) == Decimal("0.404")


async def test_sales_staffing_save_preserves_hidden_costs_and_rejects_cost_writes(session, monkeypatch):
    from app.services.sow_resources import current_resources
    opp = Opportunity(id=uuid.uuid4(), hubspot_deal_id="S13B-SALES", governance_status="Intake")
    session.add(opp)
    await session.commit()
    model = await create_gm_model_version(session, opportunity_id=opp.id, actor_id=None,
        payload=parse_gm_model_payload(fixture_payload([cost()])))
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async def override():
        yield session
    app.dependency_overrides[get_session] = override
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            headers = {"X-Test-User": "sales@smartek21.com"}
            response = await client.get(f"/sows/{opp.id}/staffing", headers=headers)
            assert response.status_code == 200, response.text
            assert "cost_lines" not in response.json()
            assert "hourly_cost" not in response.json()["resource_lines"][0]
            row = {**fixture_payload()["resource_lines"][0], "id": str(model.resource_lines[0].id), "hours_billable": "200"}
            row.pop("hourly_cost")
            raw = {"engagement_type": "fixed_price", "resource_lines": [row], "total_price": "50000"}
            saved = await client.put(f"/sows/{opp.id}/staffing", headers=headers, json=raw)
            assert saved.status_code == 200, saved.text
            state = await current_resources(session, opp.id)
            assert Decimal(state["resource_lines"][0]["hourly_cost"]) == Decimal("120")
            assert Decimal(state["cost_lines"][0]["amount"]) == Decimal("1000")
            assert "finance_summary" not in saved.json()["margin_after"]
            denied_costs = await client.put(f"/sows/{opp.id}/staffing", headers=headers, json={**raw, "cost_lines": []})
            assert denied_costs.status_code == 403
            denied_rate = await client.put(f"/sows/{opp.id}/staffing", headers=headers,
                json={**raw, "resource_lines": [{**row, "hourly_cost": None}]})
            assert denied_rate.status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)


async def test_extracted_proposal_is_not_costed_until_review_and_removal_stays_removed(session, monkeypatch):
    from app.models.sow import Sow, SowVersion
    from app.services.sow_resources import current_resources, update_resources
    opp = Opportunity(id=uuid.uuid4(), hubspot_deal_id="S13B-PROPOSAL", governance_status="Intake")
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, file_s3_key="fixture.pdf",
        file_hash="s13b-proposal", extract_status="complete", extracted_fields={
            "direct_costs": {"value": [{
                "category": "Travel", "note": "Reimbursed expenses", "basis": "amount",
                "basis_value": None, "location": "proportional", "reimbursable": True, "page_ref": 3,
            }]},
        })
    session.add(version)
    await session.commit()
    raw = {**fixture_payload(), "sow_version_id": str(version.id)}
    await create_gm_model_version(session, opportunity_id=opp.id, actor_id=None,
        payload=replace(parse_gm_model_payload(raw), direct_costs_reviewed=False))
    initial = await current_resources(session, opp.id)
    assert initial["direct_cost_proposals"][0]["basis_value"] is None
    assert initial["cost_lines"] == []
    assert Decimal(initial["margin"]["gm_us"]) == Decimal("0.424")
    await update_resources(session, opportunity_id=opp.id, actor_id=None, payload=raw)
    reviewed = await current_resources(session, opp.id)
    assert reviewed["direct_costs_reviewed"] is True
    assert reviewed["direct_cost_proposals"] == []
    assert reviewed["cost_lines"] == []
    monkeypatch.setenv("DEALGATE_ENV", "local")
    async def override():
        yield session
    app.dependency_overrides[get_session] = override
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for role, expected in (("Sales", False), ("Finance", True)):
                monkeypatch.setenv("DEALGATE_TEST_GROUPS", role)
                response = await client.get(f"/sow/versions/{version.id}", headers={"X-Test-User": "reader@smartek21.com"})
                assert response.status_code == 200, response.text
                assert ("direct_costs" in response.json()["extracted_fields"]) is expected
    finally:
        app.dependency_overrides.pop(get_session, None)
