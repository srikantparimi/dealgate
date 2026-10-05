"""Independent FC-05/12 service-boundary checks; not signed-journey acceptance."""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.auth import AuthUser
from app.gm.commercial import FeeAllocation, FixedFee, PeriodCost, PricingComponent
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.forecast import ForecastConversion, ForecastJob, ForecastPlanVersion, ForecastSchedule
from app.models.opportunity import Opportunity
from app.routers.forecast import _planning_response
from app.services.commercial_models import COMPONENT, save_commercial_model
from app.services.forecast_plans import PlanInput, link_conversion, list_plans, outlook, process_plan_jobs, save_plan
from app.services.test_fixtures import create_fixture
from tests.test_approvals import _seed_opp_with_sow, _seed_user

D = Decimal
AS_OF = datetime(2026, 10, 1, 12, tzinfo=UTC)
MONTH = date(2027, 1, 1)


@pytest.fixture(autouse=True)
def isolated_scope(monkeypatch):
    for key, value in {
        "DEALGATE_ENV": "local", "DEALGATE_TENANT_ID": "independent-plan-review",
        "DEALGATE_REPORTING_TIMEZONE": "America/Los_Angeles",
        "DEALGATE_REPORTING_CURRENCY": "USD", "ALLOW_DEV_SEED_ENDPOINT": "1",
    }.items():
        monkeypatch.setenv(key, value)


def actor(user, groups=None):
    return AuthUser(id=user.id, email=user.email, name=user.name, groups=tuple(groups or user.groups))


def component(revenue="1000", cost="500", **changes):
    return PricingComponent(**(dict(
        component_id="implementation", version="1", source_id="qa-input",
        source_version="1", workstream_id="implementation", profile="fixed_assignment",
        profile_version="1", policy_version="blueprint-defaults-v1",
        source_evidence=("independent-fixture:page-1",), service_start=MONTH,
        service_end=date(2027, 1, 31), timezone="America/Los_Angeles", currency="USD",
        billing_cadence="monthly", cost_basis="Confirmed delivery estimate", costs_confirmed=True,
        costs=(PeriodCost("delivery", MONTH, "India", D(cost) if cost is not None else None),),
        pricing=FixedFee(D(revenue), (FeeAllocation(MONTH, "India", D("1")),),
                         "Confirmed single service month", D("0.01")),
    ) | changes))


def request(account_id, **changes):
    return PlanInput(**(dict(
        account_id=account_id, title="Independent January plan", idempotency_key=uuid.uuid4(),
        inputs=COMPONENT.dump_python(component(), mode="json"), probability="0.5",
        probability_source="Reviewed probability", assumptions=["One month, confirmed scope"],
        lifecycle="tentative", change_reason="Independent service boundary fixture",
    ) | changes))


async def seed(session):
    user = await _seed_user(session, "planner@independent.test", ["Delivery"])
    deal, _ = await _seed_opp_with_sow(session, user)
    return user, deal


async def signed_source(session, user, account_id, *, revenue="400", cost="200", status="released"):
    # Only the released-package state is seeded. Commercial calculation/storage is real;
    # this is not evidence for signature verification, release, or project creation.
    deal, sow = await _seed_opp_with_sow(session, user)
    deal.client_id = account_id
    await session.commit()
    inputs = component(revenue, cost, source_id=str(sow.sow_id), source_version=str(sow.id))
    gm = await save_commercial_model(session, opportunity_id=deal.id, actor_id=user.id,
        sow_version_id=sow.id, expected_gm_model_id=None,
        inputs=COMPONENT.dump_python(inputs, mode="json"), change_reason="Confirmed QA source")
    package = ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=sow.id,
        gm_model_id=gm.id, package_hash="a" * 64, status=status, submitted_by=user.id)
    session.add(package)
    await session.commit()
    return gm, package


@pytest.mark.asyncio
async def test_create_replay_and_changed_payload_preserve_one_version_job_audit(session):
    user, deal = await seed(session)
    body = request(deal.client_id)
    first = await save_plan(session, actor=actor(user), body=body)
    replay = await save_plan(session, actor=actor(user), body=body)
    assert replay.id == first.id
    with pytest.raises(HTTPException) as error:
        await save_plan(session, actor=actor(user), body=body.model_copy(update={"probability": "0.75"}))
    assert error.value.status_code == 409
    assert len((await session.scalars(select(ForecastPlanVersion))).all()) == 1
    assert len((await session.scalars(select(ForecastJob))).all()) == 1
    audits = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == "forecast.plan_version_created"))).all()
    assert len(audits) == 1 and audits[0].correlation_id == str(body.idempotency_key)


@pytest.mark.asyncio
async def test_conversion_replay_replaces_only_explicit_partial_scope(session):
    user, deal = await seed(session)
    version = await save_plan(session, actor=actor(user), body=request(deal.client_id))
    await process_plan_jobs(session)
    gm, _ = await signed_source(session, user, deal.client_id)
    args = dict(actor=actor(user), plan_id=version.plan_id, gm_model_id=gm.id,
                expected_version_id=version.id, scope_fraction="0.4", reason="Signed 40 percent")
    before = await outlook(session, actor=actor(user), as_of=AS_OF)
    conversion = await link_conversion(session, **args)
    assert (await link_conversion(session, **args)).id == conversion.id
    after = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert before["future"]["revenue"] == D("900")
    assert after["future"]["revenue"] == D("700")  # 400 signed + 1000 * .6 * .5.
    assert after["future"]["cost"] == D("350")  # 200 signed + 500 * .6 * .5.
    assert len((await session.scalars(select(ForecastConversion))).all()) == 1


@pytest.mark.asyncio
async def test_conversion_changes_the_projection_watermark(session):
    user, deal = await seed(session)
    version = await save_plan(session, actor=actor(user), body=request(deal.client_id))
    await process_plan_jobs(session)
    gm, _ = await signed_source(session, user, deal.client_id)
    before = await outlook(session, actor=actor(user), as_of=AS_OF)
    await link_conversion(session, actor=actor(user), plan_id=version.plan_id, gm_model_id=gm.id,
        expected_version_id=version.id, scope_fraction="0.4", reason="Signed 40 percent")
    after = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert before["future"]["revenue"] != after["future"]["revenue"]
    assert before["source_watermark"] != after["source_watermark"]


@pytest.mark.asyncio
async def test_overlapping_conversion_cannot_persist_an_unreadable_company_outlook(session):
    user, deal = await seed(session)
    version = await save_plan(session, actor=actor(user), body=request(deal.client_id))
    await process_plan_jobs(session)
    first, _ = await signed_source(session, user, deal.client_id)
    second, _ = await signed_source(session, user, deal.client_id)
    args = dict(actor=actor(user), plan_id=version.plan_id, expected_version_id=version.id,
                scope_fraction="0.6", reason="Confirmed contract fraction")
    await link_conversion(session, gm_model_id=first.id, **args)
    with pytest.raises(HTTPException) as error:
        await link_conversion(session, gm_model_id=second.id, **args)
    assert error.value.status_code == 409
    assert len((await session.scalars(select(ForecastConversion))).all()) == 1
    assert (await outlook(session, actor=actor(user), as_of=AS_OF))["future"]["revenue"] == D("1000")


@pytest.mark.asyncio
async def test_unsigned_source_cannot_retire_potential_and_creates_no_conversion(session):
    user, deal = await seed(session)
    version = await save_plan(session, actor=actor(user), body=request(deal.client_id))
    gm, _ = await signed_source(session, user, deal.client_id, status="ready_to_sign")
    with pytest.raises(HTTPException) as error:
        await link_conversion(session, actor=actor(user), plan_id=version.plan_id, gm_model_id=gm.id,
            expected_version_id=version.id, scope_fraction="1", reason="Not actually signed")
    assert error.value.status_code == 409
    assert not (await session.scalars(select(ForecastConversion))).all()


@pytest.mark.asyncio
async def test_signed_unknown_cost_preserves_known_revenue_and_incomplete_margin(session):
    user, deal = await seed(session)
    await signed_source(session, user, deal.client_id, cost=None)
    view = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert view["future"]["revenue"] == D("400")
    assert view["future"]["cost"] is None
    assert view["future"]["gm"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("groups", [("Sales",), ("Sales", "HR")])
async def test_portfolio_reader_without_forecast_financial_permission_has_no_raw_costs(session, groups):
    user, deal = await seed(session)
    await save_plan(session, actor=actor(user), body=request(deal.client_id))
    reader = actor(user, groups)
    rows = await list_plans(session, actor=reader)
    response = _planning_response({"items": rows}, reader)
    assert len(response["items"]) == 1
    assert "commercial_inputs" not in response["items"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ["issuer_demoted", "deal_owner_changed", "client_mirrored", "deal_mirrored"])
async def test_fixture_trust_is_revalidated_before_planning_write(session, invalidity):
    issuer = await _seed_user(session, "issuer@independent.test", ["SystemAdmin", "Delivery", "officeapp-e2e"])
    issued = await create_fixture(session, actor_id=issuer.id, label="Forecast QA", reviewer_ids=[])
    await session.commit()
    client = await session.get(Client, issued["client_id"])
    deal = await session.get(Opportunity, issued["opportunity_id"])
    if invalidity == "issuer_demoted":
        issuer.groups = ["Delivery", "officeapp-e2e"]
    elif invalidity == "deal_owner_changed":
        outsider = await _seed_user(session, "new-owner@independent.test", ["Sales"])
        deal.owner_id = outsider.id
    elif invalidity == "client_mirrored":
        client.hubspot_company_id = "business-client-id"
    else:
        deal.hubspot_deal_id = "business-deal-id"
    await session.commit()
    with pytest.raises(HTTPException) as error:
        await save_plan(session, actor=actor(issuer), body=request(client.id))
    assert error.value.status_code == 403
    assert not (await session.scalars(select(ForecastPlanVersion))).all()


@pytest.mark.asyncio
async def test_worker_repair_obsoletes_failed_old_version_without_changing_old_inputs(session):
    user, deal = await seed(session)
    invalid = COMPONENT.dump_python(replace(component(), profile="unsupported_fixture"), mode="json")
    first = await save_plan(session, actor=actor(user), body=request(deal.client_id, inputs=invalid))
    original = dict(first.component_inputs)
    # Store corruption at the queue boundary to exercise durable failure, not a mock calculator.
    first.component_inputs = {**first.component_inputs, "costs": [{"amount": "invalid"}]}
    await session.commit()
    assert await process_plan_jobs(session) == 1
    job = await session.scalar(select(ForecastJob).where(ForecastJob.plan_version_id == first.id))
    assert job.status == "failed" and job.attempts == 1 and job.next_attempt_at is not None
    old_inputs = dict(first.component_inputs)
    fixed = await save_plan(session, actor=actor(user), plan_id=first.plan_id,
        body=request(deal.client_id, expected_version_id=first.id))
    job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    assert await process_plan_jobs(session) == 2
    assert job.status == "obsolete" and job.attempts == 1
    assert first.component_inputs == old_inputs and original != old_inputs
    assert await session.get(ForecastSchedule, first.id) is None
    assert await session.get(ForecastSchedule, fixed.id) is not None
    view = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert view["future"]["revenue"] == D("500") and not view["stale"]


@pytest.mark.asyncio
async def test_worker_and_reads_cannot_consume_a_foreign_tenant_job(session, monkeypatch):
    user, deal = await seed(session)
    version = await save_plan(session, actor=actor(user), body=request(deal.client_id))
    monkeypatch.setenv("DEALGATE_TENANT_ID", "another-tenant")
    assert await process_plan_jobs(session) == 0
    assert await session.get(ForecastSchedule, version.id) is None
    assert await list_plans(session, actor=actor(user)) == []
    assert (await outlook(session, actor=actor(user), as_of=AS_OF))["accounts"] == []


@pytest.mark.asyncio
async def test_newest_pending_version_is_stale_and_does_not_reuse_old_totals(session):
    user, deal = await seed(session)
    first = await save_plan(session, actor=actor(user), body=request(deal.client_id))
    await process_plan_jobs(session)
    next_version = await save_plan(session, actor=actor(user), plan_id=first.plan_id,
        body=request(deal.client_id, expected_version_id=first.id, probability="0.75"))
    view = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert view["stale"] and view["pending_sources"] == [str(next_version.id)]
    assert view["future"]["revenue"] == D("0")
    assert await process_plan_jobs(session) == 1
    fresh = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert not fresh["stale"] and fresh["future"]["revenue"] == D("750")
