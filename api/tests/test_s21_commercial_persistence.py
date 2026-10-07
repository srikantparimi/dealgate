"""S21-15/17: immutable commercial truth reaches existing GM consumers."""

import copy
import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import TypeAdapter

from app.gm.commercial import PricingComponent
from app.gm.calendar import DayHours, StaffingAssignment, WorkCalendar
from app.gm.commercial import FeeAllocation, FixedFee
from app.services.commercial_models import CommercialInputError, parse_component, save_commercial_model
from app.services.delivery_model import _model_to_payload, compute_live, serialize_gm_model
from app.services.redact import redact_costs
from tests.test_approval_routing import fixture
from tests.test_approvals import (
    app_with_session,
    _client,
    _passing_payload,
    _seed_opp_with_sow,
    _seed_owner,
)  # noqa: F401
from tests.test_s21_commercial_profiles import component


def wire(sow, **changes):
    value = component(source_id=str(sow.sow_id), source_version=str(sow.id),
                      policy_version="blueprint-defaults-v1", **changes)
    return TypeAdapter(PricingComponent).dump_python(value, mode="json")


@pytest.mark.parametrize("change", ["float", "unknown", "nested_unknown"])
def test_parser_never_silently_coerces_or_discards_commercial_inputs(change):
    value = TypeAdapter(PricingComponent).dump_python(component(), mode="json")
    if change == "float":
        value["pricing"]["total_fee"] = 420000.01
    elif change == "unknown":
        value["formula"] = "ignore policy"
    else:
        value["pricing"]["hourly_cost"] = "0"
    with pytest.raises(CommercialInputError):
        parse_component(value)


@pytest.mark.asyncio
async def test_saved_component_roundtrips_exactly_and_existing_reader_uses_it(session):
    owner, opp, sow, old, _ = await fixture(session)
    inputs = wire(sow)
    model = await save_commercial_model(session, opportunity_id=opp.id, actor_id=owner.id,
                                        sow_version_id=sow.id, expected_gm_model_id=old.id,
                                        inputs=inputs, change_reason="Confirmed service month allocation")
    assert model.id != old.id and model.version == old.version + 1
    assert model.commercial_inputs == inputs
    assert model.commercial_snapshot["policy"]["version"] == "blueprint-defaults-v1"
    result = compute_live(_model_to_payload(model))
    assert result.revenue_india == Decimal("420000")
    assert result.cost_india == Decimal("210000")
    assert result.gm_blended == Decimal("0.5")
    data = serialize_gm_model(model, result=result)
    assert data["computed"]["complete"] is True
    assert len(data["commercial_snapshot"]["schedule"]["rows"]) == 6
    for group in ("Sales", "Legal", "Presales"):
        redacted = redact_costs(data, {group})
        assert "commercial_inputs" not in redacted
        assert "commercial_snapshot" not in redacted
        assert "cost_india" not in redacted["computed"]


@pytest.mark.asyncio
async def test_saved_commercial_dates_populate_unconfirmed_sow_terms(session):
    from app.models.sow import SowVersion
    from app.services.delivery_model import create_gm_model_version

    owner = await _seed_owner(session, "term-owner@smartek21.com")
    opp, sow = await _seed_opp_with_sow(session, owner, confirmed=False)
    old = await create_gm_model_version(
        session,
        actor_id=owner.id,
        opportunity_id=opp.id,
        payload=_passing_payload(sow.id),
    )
    inputs = wire(
        sow,
        service_start=date(2026, 10, 1),
        service_end=date(2026, 12, 1),
    )

    await save_commercial_model(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        sow_version_id=sow.id,
        expected_gm_model_id=old.id,
        inputs=inputs,
        change_reason="Confirmed staffing plan and contract dates",
    )

    saved_sow = await session.get(SowVersion, sow.id, populate_existing=True)
    start = saved_sow.extracted_fields["term_start"]
    end = saved_sow.extracted_fields["term_end"]
    assert (start["value"], start["provenance"], start["status"]) == (
        "2026-10-01",
        "manual",
        "confirmed",
    )
    assert (end["value"], end["provenance"], end["status"]) == (
        "2026-12-01",
        "manual",
        "confirmed",
    )


@pytest.mark.asyncio
async def test_missing_cost_stays_null_not_pass_and_immutable_old_version_survives(session):
    owner, opp, sow, old, _ = await fixture(session)
    inputs = wire(sow, costs_confirmed=False)
    model = await save_commercial_model(session, opportunity_id=opp.id, actor_id=owner.id,
                                        sow_version_id=sow.id, expected_gm_model_id=old.id,
                                        inputs=inputs, change_reason="Cost validation pending")
    result = compute_live(_model_to_payload(model))
    data = serialize_gm_model(model, result=result)
    assert data["computed"]["complete"] is False
    assert data["computed"]["cost_india"] is None
    assert data["computed"]["gm_blended"] is None
    assert data["computed"]["policy"]["india_pass"] is False
    assert model.revenue_us is None and model.revenue_india is None
    assert data["commercial_snapshot"]["outcome"]["status"] == "incomplete"
    assert old.commercial_inputs is None


@pytest.mark.asyncio
async def test_stale_write_and_foreign_source_rejected_before_persist(session):
    owner, opp, sow, old, _ = await fixture(session)
    inputs = wire(sow)
    for mutation in ("stale", "source", "policy"):
        candidate = copy.deepcopy(inputs)
        if mutation == "source":
            candidate["source_version"] = str(uuid.uuid4())
        if mutation == "policy":
            candidate["policy_version"] = "invented-policy"
        with pytest.raises(CommercialInputError):
            await save_commercial_model(
                session, opportunity_id=opp.id, actor_id=owner.id, sow_version_id=sow.id,
                expected_gm_model_id=uuid.uuid4() if mutation == "stale" else old.id,
                inputs=candidate, change_reason="Confirmed change",
            )


@pytest.mark.asyncio
async def test_approval_hash_includes_commercial_source_and_frozen_policy(session):
    from app.services.approvals import package_hash

    owner, opp, sow, old, _ = await fixture(session)
    model = await save_commercial_model(session, opportunity_id=opp.id, actor_id=owner.id,
                                        sow_version_id=sow.id, expected_gm_model_id=old.id,
                                        inputs=wire(sow), change_reason="Confirmed economics")
    first = package_hash(sow, model)
    model.commercial_inputs = {**model.commercial_inputs, "version": "changed"}
    assert package_hash(sow, model) != first
    await session.rollback()


@pytest.mark.asyncio
async def test_api_permission_save_refresh_and_stale_guard(app_with_session, session, monkeypatch):  # noqa: F811
    owner, opp, sow, old, _ = await fixture(session)
    body = {"sow_version_id": str(sow.id), "expected_gm_model_id": str(old.id),
            "inputs": wire(sow), "change_reason": "Confirmed allocation from signed scope"}
    async with _client(app_with_session) as client:
        headers = {"X-Test-User": owner.email}
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
        denied = await client.post(f"/delivery-model/{opp.id}/commercial/versions", json=body, headers=headers)
        assert denied.status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
        preview = await client.post("/delivery-model/commercial/preview", json=body["inputs"], headers=headers)
        assert preview.status_code == 200, preview.text
        assert preview.json()["computed"]["cost_india"] == "210000"
        saved = await client.post(f"/delivery-model/{opp.id}/commercial/versions", json=body, headers=headers)
        assert saved.status_code == 201, saved.text
        fetched = await client.get(f"/delivery-model/{opp.id}", headers=headers)
        assert fetched.json()["gm_model"]["commercial_inputs"] == body["inputs"]
        assert fetched.json()["gm_model"]["computed"]["gm_blended"] == "0.5"
        stale = await client.post(f"/delivery-model/{opp.id}/commercial/versions", json=body, headers=headers)
        assert stale.status_code == 409
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
        redacted = await client.get(f"/delivery-model/{opp.id}", headers=headers)
        assert redacted.status_code == 200
        assert "commercial_inputs" not in redacted.json()["gm_model"]
        assert "commercial_outcome" not in redacted.json()["gm_model"]["computed"]


@pytest.mark.asyncio
async def test_fixed_fee_partial_staffing_saves_and_reloads_exact_financials(
    app_with_session, session, monkeypatch,  # noqa: F811
):
    owner, opp, sow, old, _ = await fixture(session)
    workday = DayHours(Decimal("8"), Decimal("8"), Decimal("8"))
    weekend = DayHours(Decimal("0"), Decimal("0"), Decimal("0"))
    calendar = WorkCalendar(
        "india-standard", "2026-v1", "America/New_York",
        date(2026, 10, 1), date(2026, 12, 1),
        (workday, workday, workday, workday, workday, weekend, weekend),
    )
    binding = dict(
        source_id=str(sow.sow_id), source_version=str(sow.id),
        component_id="delivery", profile_version="1",
        policy_version="blueprint-defaults-v1", role="Consultant",
        location="India", timezone="America/New_York", currency="USD",
        calendar=calendar, bill_rate=None, cost_rate=Decimal("30"),
        rate_version=None, cost_version="loaded-cost-2026",
        start=date(2026, 10, 1), end=date(2026, 12, 1),
        cost_rate_basis="hourly",
    )
    staffing = (
        StaffingAssignment("full-a", quantity=1, allocation=Decimal("1"), **binding),
        StaffingAssignment("full-b", quantity=1, allocation=Decimal("1"), **binding),
        StaffingAssignment("half", quantity=1, allocation=Decimal("0.5"), **binding),
    )
    commercial = component(
        component_id="delivery", source_id=str(sow.sow_id), source_version=str(sow.id),
        policy_version="blueprint-defaults-v1", service_start=date(2026, 10, 1),
        service_end=date(2026, 12, 1), billing_cadence="on_completion",
        cost_basis="loaded hourly cost", costs=(), staffing=staffing,
        pricing=FixedFee(
            Decimal("75400"),
            tuple(FeeAllocation(month, "India", Decimal("1")) for month in (
                date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1),
            )),
            "confirmed service months", Decimal("0.01"),
        ),
    )
    inputs = TypeAdapter(PricingComponent).dump_python(commercial, mode="json")
    body = {
        "sow_version_id": str(sow.id),
        "expected_gm_model_id": str(old.id),
        "inputs": inputs,
        "change_reason": "Confirmed partial staffing plan",
    }
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    async with _client(app_with_session) as client:
        saved = await client.post(
            f"/delivery-model/{opp.id}/commercial/versions",
            json=body,
            headers={"X-Test-User": owner.email},
        )
        assert saved.status_code == 201, saved.text
        reloaded = await client.get(
            f"/delivery-model/{opp.id}",
            headers={"X-Test-User": owner.email},
        )
    computed = reloaded.json()["gm_model"]["computed"]
    assert computed["complete"] is True
    assert computed["finance_summary"]["revenue"] == "75400.00"
    assert computed["finance_summary"]["labor_cost"] == "26400.00"
    assert computed["finance_summary"]["gross_profit"] == "49000.00"
    assert reloaded.json()["gm_model"]["commercial_inputs"] == inputs


@pytest.mark.asyncio
async def test_persisted_policy_does_not_change_after_finance_publishes(session):
    from datetime import date
    from app.services.policy import publish_policy
    from app.services.approvals import _floor_check, submit_package
    owner, opp, sow, old, _ = await fixture(session)
    model = await save_commercial_model(session, opportunity_id=opp.id, actor_id=owner.id,
                                        sow_version_id=sow.id, expected_gm_model_id=old.id,
                                        inputs=wire(sow), change_reason="Confirmed basis")
    await publish_policy(session, actor_id=owner.id, us_floor=Decimal("0.4"),
                         india_floor=Decimal("0.6"), effective_from=date(2020, 1, 1),
                         fx_convention="fixed_at_sow_date")
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    floors = await _floor_check(session, pkg)
    assert pkg.gm_model_id == model.id
    assert pkg.policy_version_id is None
    assert floors["india_floor"] == "0.50"
    assert floors["india_pass"] is True


@pytest.mark.asyncio
async def test_weekly_forecast_cannot_turn_commercial_cost_into_zero(session):
    from app.auth import AuthUser
    from app.models.approval import ApprovalPackage
    from app.services.forecast import update_forecast
    owner, opp, sow, old, _ = await fixture(session)
    model = await save_commercial_model(session, opportunity_id=opp.id, actor_id=owner.id,
                                        sow_version_id=sow.id, expected_gm_model_id=old.id,
                                        inputs=wire(sow), change_reason="Confirmed scope")
    session.add(ApprovalPackage(id=uuid.uuid4(), opportunity_id=opp.id, sow_version_id=sow.id,
                                gm_model_id=model.id, status="released", submitted_by=owner.id,
                                package_hash="unit-boundary-only"))
    await session.commit()
    row = await update_forecast(session, actor=AuthUser(id=owner.id, email=owner.email,
                                name=owner.name, groups=("Delivery",)), gm_model_id=model.id, lines=[])
    assert row.forecast_revenue == Decimal("420000")
    assert row.forecast_cost_india == Decimal("210000")
    assert row.forecast_gm_india == Decimal("0.5")
    assert row.forecast_lines_json[0]["source_version"] == str(sow.id)


@pytest.mark.asyncio
async def test_saved_snapshot_does_not_recalculate_under_new_engine_code(session, monkeypatch):
    from app.gm.commercial import ComponentSchedule
    owner, opp, sow, old, _ = await fixture(session)
    model = await save_commercial_model(session, opportunity_id=opp.id, actor_id=owner.id,
                                        sow_version_id=sow.id, expected_gm_model_id=old.id,
                                        inputs=wire(sow), change_reason="Frozen calculation evidence")
    def forbid_recalculation(*args, **kwargs):
        raise AssertionError("Stored financial approval basis must not be recalculated on read")
    monkeypatch.setattr(ComponentSchedule, "assess", forbid_recalculation)
    data = serialize_gm_model(model, result=compute_live(_model_to_payload(model)))
    assert data["computed"]["cost_india"] == "210000"
    assert data["computed"]["policy"]["india_pass"] is True


@pytest.mark.asyncio
async def test_signed_sow_requires_a_separate_amendment_version(session):
    from app.models.approval import ApprovalPackage
    owner, opp, sow, old, _ = await fixture(session)
    session.add(ApprovalPackage(id=uuid.uuid4(), opportunity_id=opp.id, sow_version_id=sow.id,
                                gm_model_id=old.id, status="released", submitted_by=owner.id,
                                package_hash="signed-boundary-unit-fixture"))
    await session.commit()
    with pytest.raises(CommercialInputError, match="amendment"):
        await save_commercial_model(session, opportunity_id=opp.id, actor_id=owner.id,
                                     sow_version_id=sow.id, expected_gm_model_id=old.id,
                                     inputs=wire(sow), change_reason="Changed cost")
