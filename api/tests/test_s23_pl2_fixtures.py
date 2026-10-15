"""S23-PL2 T12 · run-tagged fixture deals carry the fields of a real HubSpot deal.

The e2e bot sees only its own fixtures, and until now a fixture deal had no
stage, amount, close date, region or owner, so the Pipeline specs could not
exercise a populated row. A fixture issued with ``pipeline_deal`` gets them,
still keeps its test grant, and never gets an approval package.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.user import User
from app.services.hubspot_owners import HubspotOwner
from app.services.hubspot_properties import HubspotPropertyMapping
from app.services.test_fixtures import account_scope, create_fixture, user_allowed

STAGES = [
    ("s1", "1-Initial Contact/Prospecting", "0.10", False),
    ("s2", "2-Qualification", "0.20", False),
    ("s3", "3-Requirement/Fit Gap Analysis", "0.30", False),
    ("s4", "4-Proposal", "0.50", False),
    ("s5", "5-Negotiation", "0.70", False),
    ("s6", "6-Contracting/Drive Commitment", "0.90", False),
    ("s7", "7-Closed Won", "1.00", True),
    ("s8", "8-Closed Lost", "0.00", True),
    ("s9", "Hold", "0.10", False),
]


@pytest.fixture
def fixture_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "pl2-fixtures")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")


async def _bot(session) -> User:
    bot = User(email="bot@example.test", name="E2E bot", groups=["officeapp-e2e", "SystemAdmin"])
    session.add(bot)
    await session.flush()
    return bot


async def _mirror(session) -> None:
    session.add(HubspotPipeline(id="p1", label="Global sales pipeline", display_order=0, archived=False))
    await session.flush()
    for order, (sid, label, prob, closed) in enumerate(STAGES):
        session.add(HubspotStage(id=sid, pipeline_id="p1", label=label, display_order=order,
                                 is_closed=closed, probability=Decimal(prob), archived=False))
    session.add_all([
        HubspotOwner(id="o-active", email="rep@example.test", first_name="Rita", last_name="Rep", archived=False),
        HubspotOwner(id="o-gone", email="gone@example.test", first_name="Gus", last_name="Gone", archived=True),
        HubspotPropertyMapping(key="business_unit", internal_name="region", object_type="deal", label="Region",
                               field_type="enumeration", options=[{"value": "US"}, {"value": "South Africa"}],
                               availability_state="configured", mapping_version=3),
    ])
    await session.flush()


@pytest.mark.asyncio
async def test_populated_fixture_deal_has_hubspot_fields_and_keeps_its_grant(session, fixture_env):
    bot = await _bot(session)
    await _mirror(session)
    result = await create_fixture(
        session, actor_id=bot.id, label="Populated", reviewer_ids=[],
        pipeline_deal={"stage": 4, "amount": Decimal("125000.00"), "region": "US", "owner": "active",
                       "close_in_days": 20, "created_days_ago": 12, "activity_days_ago": 3, "draft_sow": True},
    )
    deal = await session.get(Opportunity, result["opportunity_id"])
    assert (deal.hubspot_pipeline_id, deal.hubspot_stage_id, deal.stage_label) == ("p1", "s4", "4-Proposal")
    assert deal.is_closed_won is False and deal.is_closed_lost is False
    assert deal.amount == Decimal("125000.00") and deal.currency == "USD"
    assert deal.close_date is not None and deal.hubspot_created_at is not None
    assert deal.hubspot_last_activity_at is not None
    assert (deal.business_unit_value, deal.business_unit_mapping_version) == ("US", 3)
    assert deal.business_unit_observed_at is not None
    assert deal.hubspot_owner_id == "o-active"
    # Still a fixture: no CRM identity, owned by the bot, visible only to it.
    assert deal.hubspot_deal_id is None and deal.source == "sow_upload" and deal.owner_id == bot.id
    assert user_allowed(bot, await account_scope(session, result["client_id"], opportunity_id=deal.id))
    sows = (await session.scalars(select(Sow).where(Sow.opportunity_id == deal.id))).all()
    assert len(sows) == 1
    assert (await session.scalars(select(ApprovalPackage))).all() == []


@pytest.mark.asyncio
async def test_closed_stages_and_owner_states(session, fixture_env):
    bot = await _bot(session)
    await _mirror(session)
    won = await create_fixture(session, actor_id=bot.id, label="Won", reviewer_ids=[],
                               pipeline_deal={"stage": 7, "owner": "former"})
    lost = await create_fixture(session, actor_id=bot.id, label="Lost", reviewer_ids=[],
                                pipeline_deal={"stage": 8, "owner": "none"})
    won_deal = await session.get(Opportunity, won["opportunity_id"])
    lost_deal = await session.get(Opportunity, lost["opportunity_id"])
    assert won_deal.is_closed_won is True and won_deal.is_closed_lost is False
    assert lost_deal.is_closed_lost is True and lost_deal.is_closed_won is False
    # "former": an owner id no mirror row holds, which the Pipeline shows as a former HubSpot user.
    assert won_deal.hubspot_owner_id.startswith("e2e-former-")
    assert await session.get(HubspotOwner, won_deal.hubspot_owner_id) is None
    assert lost_deal.hubspot_owner_id is None


@pytest.mark.asyncio
async def test_out_of_range_stage_and_missing_mirror_are_refused(session, fixture_env):
    bot = await _bot(session)
    with pytest.raises(HTTPException) as no_mirror:
        await create_fixture(session, actor_id=bot.id, label="No mirror", reviewer_ids=[],
                             pipeline_deal={"stage": 1})
    assert no_mirror.value.status_code == 409
    await _mirror(session)
    with pytest.raises(HTTPException) as bad_stage:
        await create_fixture(session, actor_id=bot.id, label="Bad stage", reviewer_ids=[],
                             pipeline_deal={"stage": 10})
    assert bad_stage.value.status_code == 422
