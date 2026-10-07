"""S22 · AI/SOW-proposed commercial model draft (owner directive 2026-10-05).

"Human intervention only where needed": the commercial editor opens
pre-filled from what the system already knows — the SOW extraction
(term, currency, price, engagement) and the deterministic auto-staffing
grid the upload pipeline persisted (roles, locations, allocation
fractions, rates from rate cards / past SOWs). Every proposed value
carries provenance; costs are never confirmed by the machine
(costs_confirmed=False) so the GM stays honestly incomplete until a
human reviews. Rule 2: no LLM writes a number here — extraction values
were human-confirmable fields, rates are looked up, math is Decimal in
the gm engine at save time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.gm.commercial import PricingComponent
from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.gm_model import GmModel, ResourceLine
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.commercial_models import COMPONENT
from app.services.commercial_proposal import ProposalError, propose_component

TERM_START, TERM_END = "2026-10-01", "2027-03-31"


def _fields(**overrides):
    base = {
        "price": {"value": "250000.00", "status": "confirmed"},
        "currency": {"value": "USD", "status": "confirmed"},
        "term_start": {"value": TERM_START, "status": "confirmed"},
        "term_end": {"value": TERM_END, "status": "confirmed"},
        "engagement_type_suggested": {"value": "fixed_price", "status": "confirmed"},
        "scope_summary": {"value": "Modernise the platform", "status": "confirmed"},
    }
    base.update(overrides)
    return base


async def _seed(session, *, fields=None, with_lines=True):
    owner = User(id=uuid.uuid4(), email=f"prop-{uuid.uuid4().hex[:6]}@smartek21.com",
                 name="Proposer", groups=["Delivery"])
    client = Client(id=uuid.uuid4(), name="Proposal Client")
    session.add_all([owner, client])
    await session.flush()
    opp = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner.id,
                      governance_status="Intake")
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner.id,
        file_s3_key="prop/v1.pdf", file_hash=uuid.uuid4().hex * 2,
        extract_status="complete", extracted_fields=fields or _fields(),
        confirmed_by=owner.id, confirmed_at=datetime.now(UTC),
        engagement_type_confirmed="fixed_price",
    )
    session.add(version)
    gm = GmModel(id=uuid.uuid4(), opportunity_id=opp.id, sow_id=sow.id,
                 sow_version_id=version.id, engagement_type="fixed_price",
                 created_by=owner.id, version=1)
    session.add(gm)
    await session.flush()
    if with_lines:
        session.add_all([
            ResourceLine(id=uuid.uuid4(), gm_model_id=gm.id, role="Engineer",
                         seniority="Senior", location="US",
                         start_date=date(2026, 10, 1), end_date=date(2027, 3, 31),
                         allocation_pct=Decimal("0.5"),
                         billable_hours=Decimal("480"),
                         hourly_bill_rate=Decimal("150"),
                         hourly_loaded_cost=Decimal("95")),
            ResourceLine(id=uuid.uuid4(), gm_model_id=gm.id, role="Analyst",
                         seniority="Mid", location="India",
                         start_date=date(2026, 10, 1), end_date=date(2027, 3, 31),
                         allocation_pct=Decimal("1"),
                         billable_hours=Decimal("960"),
                         hourly_bill_rate=Decimal("55"),
                         hourly_loaded_cost=Decimal("30")),
        ])
    await session.commit()
    return owner, opp, sow, version


@pytest.mark.asyncio
async def test_proposal_prefills_from_extraction_and_staffing_lines(session):
    owner, opp, sow, version = await _seed(session)
    proposal = await propose_component(session, opportunity_id=opp.id)

    component = COMPONENT.validate_python(proposal["component"])
    assert isinstance(component, PricingComponent)
    assert component.profile == "fixed_assignment"
    assert component.service_start == date(2026, 10, 1)
    assert component.service_end == date(2027, 3, 31)
    assert component.currency == "USD"
    assert component.costs_confirmed is False  # the machine never confirms
    assert component.pricing.total_fee == Decimal("250000.00")
    # Even allocation over the six service months, summing to exactly 1.
    assert len(component.pricing.allocations) == 6
    assert sum(a.weight for a in component.pricing.allocations) == Decimal("1")
    # Staffing carried over with utilization intact.
    assert len(component.staffing) == 2
    by_role = {a.role: a for a in component.staffing}
    assert by_role["Engineer"].seniority == "Senior"
    assert by_role["Engineer"].allocation == Decimal("0.5")
    assert by_role["Engineer"].hours_billable == Decimal("480")
    assert by_role["Analyst"].seniority == "Mid"
    assert by_role["Analyst"].allocation == Decimal("1")
    assert by_role["Analyst"].hours_billable == Decimal("960")
    assert by_role["Engineer"].cost_rate == Decimal("95")
    assert by_role["Engineer"].bill_rate == Decimal("150")

    prov = proposal["provenance"]
    assert prov["service_start"] == "extracted"
    assert prov["currency"] == "extracted"
    assert prov["pricing.amount"] == "extracted"
    assert prov["pricing.allocations"] == "calculated"
    assert prov["staffing"] == "looked_up"
    assert proposal["saved_version_exists"] is False


@pytest.mark.asyncio
async def test_missing_dates_default_with_explicit_warning(session):
    fields = _fields(term_start={"value": None, "status": "unconfirmed"},
                     term_end={"value": None, "status": "unconfirmed"})
    owner, opp, sow, version = await _seed(session, fields=fields)
    proposal = await propose_component(session, opportunity_id=opp.id)
    component = COMPONENT.validate_python(proposal["component"])
    assert component.service_start is not None and component.service_end is not None
    assert proposal["provenance"]["service_start"] == "defaulted"
    assert any("term" in w.lower() for w in proposal["warnings"])


@pytest.mark.asyncio
async def test_staff_aug_suggests_calendar_profile(session):
    fields = _fields(engagement_type_suggested={"value": "staff_aug", "status": "confirmed"})
    owner, opp, sow, version = await _seed(session, fields=fields)
    version.engagement_type_confirmed = "staff_aug"
    await session.commit()
    proposal = await propose_component(session, opportunity_id=opp.id)
    assert proposal["suggested_profile"] == "calendar_staff_aug"
    component = COMPONENT.validate_python(proposal["component"])
    assert component.profile == "calendar_staff_aug"
    assert len(component.staffing) == 2
    assert {r.basis for r in component.pricing.rates} == {"hourly"}


@pytest.mark.asyncio
async def test_signed_basis_refuses_proposal(session):
    owner, opp, sow, version = await _seed(session)
    gm_for_pkg = await session.scalar(
        __import__("sqlalchemy").select(GmModel.id).where(GmModel.sow_version_id == version.id))
    session.add(ApprovalPackage(id=uuid.uuid4(), opportunity_id=opp.id,
                                sow_version_id=version.id, gm_model_id=gm_for_pkg,
                                package_hash="a" * 64,
                                status="released", submitted_by=owner.id))
    await session.commit()
    with pytest.raises(ProposalError) as error:
        await propose_component(session, opportunity_id=opp.id)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_no_staffing_lines_still_proposes_fee_shell(session):
    owner, opp, sow, version = await _seed(session, with_lines=False)
    proposal = await propose_component(session, opportunity_id=opp.id)
    component = COMPONENT.validate_python(proposal["component"])
    assert component.pricing.total_fee == Decimal("250000.00")
    assert component.staffing == ()
    assert any("staffing" in w.lower() for w in proposal["warnings"])


@pytest.mark.asyncio
async def test_proposal_round_trips_through_save_commercial_model(session):
    from app.services.commercial_models import save_commercial_model

    owner, opp, sow, version = await _seed(session)
    proposal = await propose_component(session, opportunity_id=opp.id)
    from sqlalchemy import select as _select
    current_gm = await session.scalar(
        _select(GmModel.id).where(GmModel.sow_version_id == version.id))
    saved = await save_commercial_model(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        sow_version_id=version.id,
        expected_gm_model_id=current_gm,
        inputs=proposal["component"],
        change_reason="Confirmed the proposed commercial draft",
    )
    assert saved is not None


@pytest.mark.asyncio
async def test_proposal_endpoint_gates_roles_and_returns_draft(
    session, monkeypatch
):
    import httpx

    from app.db import get_session
    from app.main import app as main_app

    monkeypatch.setenv("DEALGATE_ENV", "local")
    owner, opp, sow, version = await _seed(session)

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
            denied = await c.get(
                f"/delivery-model/{opp.id}/commercial/proposal",
                headers={"X-Test-User": owner.email},
            )
            assert denied.status_code == 403
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
            ok = await c.get(
                f"/delivery-model/{opp.id}/commercial/proposal",
                headers={"X-Test-User": owner.email},
            )
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert body["component"]["profile"] == "fixed_assignment"
            assert body["provenance"]["currency"] == "extracted"
    finally:
        main_app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_price_with_currency_symbol_and_commas_parses(session):
    fields = _fields(price={"value": "$75,400", "status": "confirmed"})
    owner, opp, sow, version = await _seed(session, fields=fields)
    proposal = await propose_component(session, opportunity_id=opp.id)
    component = COMPONENT.validate_python(proposal["component"])
    assert component.pricing.total_fee == Decimal("75400")
    assert proposal["provenance"]["pricing.amount"] == "extracted"
    assert not any("price" in w.lower() for w in proposal["warnings"])
