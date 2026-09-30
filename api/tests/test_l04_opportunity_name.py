"""S20 W2 L04 · verify Opportunity.name is populated from HubSpot dealname
and used as the display/search key.

Ensures:
- Fresh backfill writes `opportunity.name = props.dealname`.
- The query service search matches on `name` (in addition to stage_label,
  hubspot_deal_id, and client name).
- The Pipeline list surface returns the real dealname on the `name`
  column instead of the S19 fallback (stage_label).
- Update path picks up a `dealname` change on the next event.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.integrations.hubspot import StubHubSpotClient
from app.models.opportunity import Opportunity
from app.services.hubspot_backfill import run_backfill
from app.services.hubspot_intake import handle_event
from app.services.hubspot_pipeline import PipelineFilters, list_opportunities


def _sample_deal(deal_id: str, dealname: str, stage: str = "1038193692") -> dict:
    return {
        "id": deal_id,
        "properties": {
            "dealname": dealname,
            "dealstage": stage,
            "pipeline": "710688094",
            "hubspot_owner_id": "77",
        },
    }


@pytest.mark.asyncio
async def test_backfill_writes_dealname_to_name(session):
    stub = StubHubSpotClient(
        deals={
            "500": _sample_deal("500", "BSC Staffing - UX/UI Designer"),
            "501": _sample_deal("501", "Momentum - Extension - GIAP (1 Month)"),
        },
        owners={"77": {"id": "77", "email": "rep@smartek21.com", "firstName": "Sam", "lastName": "Rep"}},
    )
    await run_backfill(stub, session_factory=lambda: session)
    await session.commit()

    rows = list((await session.execute(
        select(Opportunity).order_by(Opportunity.hubspot_deal_id)
    )).scalars())
    assert len(rows) == 2
    by_id = {r.hubspot_deal_id: r for r in rows}
    assert by_id["500"].name == "BSC Staffing - UX/UI Designer"
    assert by_id["501"].name == "Momentum - Extension - GIAP (1 Month)"


@pytest.mark.asyncio
async def test_intake_writes_dealname_on_create(session):
    stub = StubHubSpotClient(
        deals={"800": _sample_deal("800", "Blue Shield of California - Pilot")},
        owners={"77": {"id": "77", "email": "rep@smartek21.com", "firstName": "Sam", "lastName": "Rep"}},
    )
    await handle_event(
        session,
        {"eventId": 1, "subscriptionType": "deal.creation", "objectId": 800},
        stub,
    )
    await session.commit()

    opp = (await session.execute(
        select(Opportunity).where(Opportunity.hubspot_deal_id == "800")
    )).scalar_one()
    assert opp.name == "Blue Shield of California - Pilot"


@pytest.mark.asyncio
async def test_intake_updates_dealname_on_change(session):
    stub = StubHubSpotClient(
        deals={"801": _sample_deal("801", "Old dealname")},
        owners={"77": {"id": "77", "email": "rep@smartek21.com", "firstName": "Sam", "lastName": "Rep"}},
    )
    await handle_event(
        session,
        {"eventId": 10, "subscriptionType": "deal.creation", "objectId": 801},
        stub,
    )
    await session.commit()

    stub.deals["801"]["properties"]["dealname"] = "Renamed dealname"
    await handle_event(
        session,
        {"eventId": 11, "subscriptionType": "deal.propertyChange", "objectId": 801},
        stub,
    )
    await session.commit()

    opp = (await session.execute(
        select(Opportunity).where(Opportunity.hubspot_deal_id == "801")
    )).scalar_one()
    assert opp.name == "Renamed dealname"


@pytest.mark.asyncio
async def test_search_matches_dealname(session):
    stub = StubHubSpotClient(
        deals={
            "900": _sample_deal("900", "BSC Staffing - UX/UI Designer"),
            "901": _sample_deal("901", "Momentum - GIAP Extension"),
        },
        owners={"77": {"id": "77", "email": "rep@smartek21.com", "firstName": "Sam", "lastName": "Rep"}},
    )
    for did in ("900", "901"):
        await handle_event(
            session,
            {"eventId": int(did), "subscriptionType": "deal.creation", "objectId": int(did)},
            stub,
        )
    await session.commit()

    page = await list_opportunities(session, filters=PipelineFilters(search="BSC"))
    assert page.total == 1
    assert page.items[0].hubspot_deal_id == "900"
    assert page.items[0].name == "BSC Staffing - UX/UI Designer"


@pytest.mark.asyncio
async def test_list_returns_dealname_not_stage_fallback(session):
    stub = StubHubSpotClient(
        deals={"902": _sample_deal("902", "Venetian - Direct Placement/System Engineer")},
        owners={"77": {"id": "77", "email": "rep@smartek21.com", "firstName": "Sam", "lastName": "Rep"}},
    )
    await handle_event(
        session,
        {"eventId": 20, "subscriptionType": "deal.creation", "objectId": 902},
        stub,
    )
    await session.commit()

    page = await list_opportunities(session, filters=PipelineFilters())
    assert page.total == 1
    row = page.items[0]
    assert row.name == "Venetian - Direct Placement/System Engineer"
    # Sanity: the row was not defaulted to the stage_label (S19 fallback).
    assert row.name != row.stage_label
