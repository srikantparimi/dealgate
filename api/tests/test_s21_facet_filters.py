"""Real facet HTTP handler must use the same filtered DB population as rows."""

from datetime import UTC, date, datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.models.watchlist import WatchedItem
from app.routers.pipeline import router
from app.services.hubspot_properties import HubspotPropertyMapping


@pytest_asyncio.fixture
async def wired(session):
    owners = [User(email=f"facet-{i}@example.test", name=f"Facet owner {i}", groups=["SystemAdmin"])
              for i in range(2)]
    clients = [Client(name=f"Facet client {i}", hubspot_company_id=f"facet-company-{i}",
                      hubspot_owner_id=f"account-{i}") for i in range(2)]
    session.add_all([*owners, *clients, HubspotPropertyMapping(key="business_unit",
        internal_name="bu", object_type="deal", field_type="enumeration", label="BU",
        availability_state="configured", mapping_version=1,
        options=[{"value": "east", "label": "East"}, {"value": "west", "label": "West"}])])
    await session.flush()
    deals = [Opportunity(name=f"Facet deal {i}", hubspot_deal_id=f"facet-deal-{i}",
        source="hubspot", owner_id=owners[i].id, client_id=clients[i].id,
        hubspot_pipeline_id=f"pipeline-{i}", hubspot_stage_id=f"stage-{i}", stage_label=f"Stage {i}",
        amount=100, currency="USD", close_date=date(2026, 10, 10 + i),
        is_closed_won=False, is_closed_lost=False,
        business_unit_value=["east", "west"][i], business_unit_mapping_version=1,
        business_unit_observed_at=datetime.now(UTC)) for i in range(2)]
    session.add_all(deals)
    await session.flush()
    app = FastAPI()
    app.include_router(router)
    actor = AuthUser(owners[0].id, owners[0].email, owners[0].name, ("SystemAdmin",))
    app.dependency_overrides[current_user] = lambda: actor

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, owners, clients, deals, app


@pytest.mark.parametrize("axis", ["pipeline", "stage", "owner", "account_owner", "business_unit",
                                 "client", "search", "date", "missing", "closed"])
async def test_facet_filter_axes_match_rows_and_summary(wired, axis):
    client, owners, clients, _, _ = wired
    query = {
        "pipeline": [("pipeline", "pipeline-0")], "stage": [("stage", "stage-0")],
        "owner": [("owner", str(owners[0].id))], "account_owner": [("account_owner", "account-0")],
        "business_unit": [("business_unit", "east")], "client": [("client", str(clients[0].id))],
        "search": [("search", "Facet deal 0")],
        "date": [("date_field", "close"), ("date_from", "2026-10-10"), ("date_to", "2026-10-10")],
        "missing": [("missing", "business_unit")], "closed": [("open_closed", "closed_lost")],
    }[axis]
    facets = await client.get("/pipeline/facets", params=query)
    rows = await client.get("/pipeline/opportunities", params=query)
    aggregate = await client.get("/pipeline/summary", params=query)
    assert facets.status_code == rows.status_code == aggregate.status_code == 200
    expected = [] if axis in ("missing", "closed") else ["east"]
    assert facets.json()["business_units"] == expected
    assert {o["id"] for o in facets.json()["owners"]} == {r["owner_id"] for r in rows.json()["items"]}
    assert rows.json()["total"] == aggregate.json()["open_count"] == len(expected)


async def test_group_and_watch_intersect_to_empty_without_facets_leak(session, wired):
    client, owners, _, deals, _ = wired
    group = TrackingGroup(name="Only east", owner_id=owners[0].id, member_kind="opportunity", visibility="private")
    session.add(group)
    await session.flush()
    session.add_all([TrackingGroupMember(group_id=group.id, member_id=deals[0].id),
        WatchedItem(user_id=owners[0].id, kind="opportunity", item_id=deals[1].id)])
    await session.flush()
    response = await client.get("/pipeline/facets", params={"group": str(group.id), "watching": "true"})
    assert response.status_code == 200 and response.json() == {"owners": [], "business_units": []}


@pytest.mark.parametrize("params", [{"date_field": "invalid"}, {"missing": "invalid"},
                                   {"open_closed": "invalid"}, {"owner": "not-a-uuid"}])
async def test_facet_rejects_invalid_filters_like_rows(wired, params):
    client, *_ = wired
    facets = await client.get("/pipeline/facets", params=params)
    rows = await client.get("/pipeline/opportunities", params=params)
    assert facets.status_code == rows.status_code
    assert facets.status_code in (400, 422)


async def test_facet_enforces_reader_permission(wired):
    client, owners, _, _, app = wired
    app.dependency_overrides[current_user] = lambda: AuthUser(owners[0].id, owners[0].email, "Denied", ())
    assert (await client.get("/pipeline/facets")).status_code == 403
