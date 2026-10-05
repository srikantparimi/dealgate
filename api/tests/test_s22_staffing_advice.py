"""S22 · staffing advice: estimate draft + rate lookup + solver verdict."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.integrations.bedrock_team_estimate import (
    EstimateUnavailable,
    StubTeamEstimate,
    TeamEstimate,
)
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.staffing_advice import AdviceError, advise

D = Decimal


async def _seed(session, *, price="$75,400"):
    owner = User(id=uuid.uuid4(), email=f"adv-{uuid.uuid4().hex[:6]}@smartek21.com",
                 name="Adviser", groups=["Delivery"])
    client = Client(id=uuid.uuid4(), name="Advice Client")
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
        file_s3_key="adv/v1.docx", file_hash=uuid.uuid4().hex * 2,
        extract_status="complete",
        extracted_fields={
            "price": {"value": price, "status": "confirmed"},
            "scope_summary": {"value": "ServiceNow assessment, 7 workstreams",
                              "status": "confirmed"},
        },
        confirmed_by=owner.id, confirmed_at=datetime.now(UTC),
    )
    session.add(version)
    await session.commit()
    return opp


@pytest.mark.asyncio
async def test_caesars_shape_estimate_feeds_solver_and_mix_hits_target(session):
    opp = await _seed(session)
    advice = await advise(
        session,
        opportunity_id=opp.id,
        estimator=StubTeamEstimate(),  # 2.5 FTE over 7 weeks, with quotes
        target_gm=D("0.35"),
        min_onshore_fte=D("1"),
    )
    assert advice["feasible"] is True
    assert advice["estimate"]["required_fte"] == "2.5"
    assert advice["estimate"]["provenance"] == "extracted"
    assert advice["estimate"]["evidence"]
    assert advice["inputs"]["revenue"] == "75400"  # "$75,400" normalised
    assert advice["inputs"]["weeks"] == "7"  # from the estimate's duration
    assert Decimal(advice["suggested"]["onshore_fte"]) == D("1")
    assert Decimal(advice["suggested"]["gm"]) >= D("0.35")
    assert advice["caution"] is None


@pytest.mark.asyncio
async def test_overscoped_engagement_raises_the_delivery_caution(session):
    opp = await _seed(session)
    big = StubTeamEstimate(TeamEstimate(
        required_fte="6", duration_weeks="7", roles=(), rationale="big scope",
        evidence=("19.5 person-weeks across 7 workstreams",),
    ))
    advice = await advise(
        session, opportunity_id=opp.id, estimator=big, target_gm=D("0.35"),
    )
    assert advice["feasible"] is False
    assert advice["caution"] is not None and "6" in advice["caution"]
    assert Decimal(advice["max_fte_at_target"]) < D("6")
    # The best achievable team is still shown so Delivery sees the gap.
    assert advice["suggested"] is not None


@pytest.mark.asyncio
async def test_estimator_failure_falls_back_to_manual_fte(session):
    opp = await _seed(session)
    broken = StubTeamEstimate(EstimateUnavailable(reason="model down"))
    advice = await advise(
        session, opportunity_id=opp.id, estimator=broken,
        weeks=D("7"), target_gm=D("0.35"),
    )
    assert advice["estimate"] is None
    assert any("by hand" in w for w in advice["warnings"])
    assert advice["suggested"] is not None  # capacity envelope still computed


@pytest.mark.asyncio
async def test_missing_fee_is_a_422_not_a_guess(session):
    opp = await _seed(session, price="")
    with pytest.raises(AdviceError) as error:
        await advise(session, opportunity_id=opp.id, estimator=StubTeamEstimate(),
                     weeks=D("7"))
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_target_gm_defaults_to_policy_floor_with_warning(session):
    opp = await _seed(session)
    advice = await advise(
        session, opportunity_id=opp.id, estimator=StubTeamEstimate(),
    )
    assert advice["inputs"]["target_gm_provenance"] == "defaulted"
    assert any("Target GM defaulted" in w for w in advice["warnings"])


@pytest.mark.asyncio
async def test_endpoint_gates_roles_and_returns_advice(session, monkeypatch):
    import httpx

    from app.db import get_session
    from app.main import app as main_app

    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("S3_STUB", "1")  # offline stub estimator
    opp = await _seed(session)

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
            denied = await c.post(
                f"/delivery-model/{opp.id}/commercial/staffing-advice",
                headers={"X-Test-User": "adv@smartek21.com"},
                json={"target_gm": "0.35", "min_onshore_fte": "1"},
            )
            assert denied.status_code == 403
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
            ok = await c.post(
                f"/delivery-model/{opp.id}/commercial/staffing-advice",
                headers={"X-Test-User": "adv@smartek21.com"},
                json={"target_gm": "0.35", "min_onshore_fte": "1"},
            )
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert body["feasible"] is True
            assert body["estimate"]["required_fte"] == "2.5"
            assert Decimal(body["suggested"]["gm"]) >= Decimal("0.35")
    finally:
        main_app.dependency_overrides.pop(get_session, None)
