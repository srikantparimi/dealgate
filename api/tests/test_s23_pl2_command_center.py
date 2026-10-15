"""S23-PL2 B2 — one definition of "open": the Command Center shows the Pipeline's open number.

``metrics.open_opportunity_value`` / ``open_opportunity_count`` are the
Pipeline's open count and USD value for the Command Center's scope, from the
workspace's own filter function. An open deal linked to an engagement and one
with a SOW are in that number; neither is in the stricter number (USD,
weighted, no SOW and no engagement link), which keeps its value and is
labelled "Not yet in the SOW flow". Command Center links to the Pipeline use
the workspace's parameters.

Pre-merge review (R2/R3/R4): the open number is counted over exactly the list
its link opens. The Command Center's raw HubSpot region becomes its business
unit (or "unmapped"), as the Pipeline filters; an owner becomes their HubSpot
owner. An owner the Pipeline cannot filter on (no HubSpot link, or the
Unassigned placeholder) gets no link at all. The stricter tile links to the
closest Pipeline list (no SOW). The Revenue outlook's unscheduled pipeline
still counts open deals that have a SOW.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.auth import AuthUser
from app.models.client import Client
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.user import User
from app.models.watchlist import WatchedItem
from app.routers.command_center import router as command_router
from app.routers.pipeline import router as pipeline_router
from app.services.command_center import build_command_overview
from app.services.hubspot_pipeline import PipelineFilters
from app.services.hubspot_properties import HubspotPropertyMapping
from app.services.pipeline_workspace import WorkspaceFilters, build_workspace, open_totals
from tests.test_command_center_accounts import _deal, _fixed_fee_engagement, _pipeline
from tests import test_s23_pl2_workspace as shared
from tests.test_s23_pl2_workspace import client_for

# Shared fixtures, bound as module globals so pytest finds them here.
engine, frozen_clock = shared.engine, shared.frozen_clock

STRICTER = "Not yet in the SOW flow"
NOW = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)
SCOPE = dict(include_closed=True, open_closed="any")


async def _population(session):
    owner = User(email="cc-owner@example.test", name="Casey Owner", groups=["SalesLeader"],
                 hubspot_owner_id="777", hubspot_owner_link="admin")
    client = Client(name="Lumen Health", hubspot_company_id="c-lumen")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "cc")  # stages 6 and 7 are closed
    deals = {
        "plain": await _deal(session, client=client, owner=owner, pipeline="cc", stage=stages[1], name="Plain open"),
        "linked": await _deal(session, client=client, owner=owner, pipeline="cc", stage=stages[2],
                              name="Linked to an engagement"),
        "with_sow": await _deal(session, client=client, owner=owner, pipeline="cc", stage=stages[3], name="Has a SOW"),
        "won": await _deal(session, client=client, owner=owner, pipeline="cc", stage=stages[5], name="Won", won=True),
        "lost": await _deal(session, client=client, owner=owner, pipeline="cc", stage=stages[6], name="Lost",
                            lost=True),
    }
    for deal in deals.values():
        deal.hubspot_owner_id = "777"
    await _fixed_fee_engagement(session, client=client, owner=owner, opportunity=deals["linked"],
                                cost_per_hour=Decimal("50"))
    session.add(Sow(opportunity_id=deals["with_sow"].id))
    await session.commit()
    return owner, client, deals


async def test_the_open_number_is_the_pipelines_and_the_stricter_one_is_labelled(session, frozen_clock):
    owner, _, deals = await _population(session)
    overview = await build_command_overview(session, scope=PipelineFilters(include_closed=True, open_closed="any"))

    # The Pipeline's number: every open deal, the linked one and the one with a SOW included.
    assert overview["metrics"]["open_opportunity_count"] == 3
    assert Decimal(overview["metrics"]["open_opportunity_value"]) == Decimal("375000")
    assert overview["metrics"]["open_opportunity_href"] == "/pipeline?status=open"
    workspace = await build_workspace(session, actor=AuthUser(uuid.uuid4(), "reader@example.test", "Reader",
                                                              ("SalesLeader",)), filters=WorkspaceFilters())
    assert workspace["metrics"]["open_deals"]["value"] == overview["metrics"]["open_opportunity_count"]
    assert workspace["metrics"]["open_value_usd"]["value"] == overview["metrics"]["open_opportunity_value"]

    # The stricter number keeps its own value and label: neither the linked deal nor the SOW deal.
    pipeline = overview["tiles"]["pipeline"]
    assert pipeline["label"] == STRICTER
    assert Decimal(pipeline["gross"]) == Decimal("125000") and pipeline["eligible_deals"] == 1
    assert overview["lifecycle"]["pipeline"] == 1
    item = next(row for row in overview["lifecycle_items"] if row["key"] == "pipeline")
    assert (item["label"], item["count"], item["entity"]) == (STRICTER, 1, "open deals")
    # Links into the Pipeline speak the workspace's language. The stricter number opens the
    # closest Pipeline list: open deals with no SOW.
    assert overview["metrics"]["open_opportunity_business_units"] == []
    assert pipeline["href"] == "/pipeline?status=open&sow=none"
    assert item["href"] == "/pipeline?status=open&sow=none"
    assert next(row for row in overview["brief"] if row["kind"] == "opportunity")["href"] == \
        "/pipeline?status=open&sow=none"


async def test_open_totals_is_the_workspace_filter_for_any_scope(session, frozen_clock):
    owner, _, deals = await _population(session)
    totals = await open_totals(session, PipelineFilters(owner=(owner.id,), include_closed=True, open_closed="any"))
    assert (totals.count, totals.value_usd) == (3, Decimal("375000.00"))
    assert totals.pipeline_query == {"owner": ["777"]}
    # An unknown owner has no Pipeline equivalent: no link, and nothing counted.
    nobody = await open_totals(session, PipelineFilters(owner=(uuid.uuid4(),), include_closed=True, open_closed="any"))
    assert (nobody.count, nobody.value_usd, nobody.pipeline_query) == (0, Decimal(0), None)


async def test_scoped_links_translate_region_and_owner(session, frozen_clock):
    owner, client, deals = await _population(session)
    session.add(HubspotPropertyMapping(
        key="business_unit", internal_name="region", object_type="deal", label="Region", field_type="enumeration",
        availability_state="configured", mapping_version=1,
        options=[{"value": v} for v in ("US", "South Africa")]))
    from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap

    session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    for key in ("plain", "with_sow", "won"):
        deals[key].business_unit_value, deals[key].business_unit_mapping_version = "US", 1
        deals[key].business_unit_observed_at = NOW
    await session.commit()
    user = AuthUser(owner.id, owner.email, owner.name, ("SalesLeader",))
    async with client_for(session, user, command_router, pipeline_router) as api:
        response = await api.get("/command-center/overview", params={"business_unit": "US", "owner_id": str(owner.id)})
        assert response.status_code == 200, response.text
        overview = response.json()
        href = overview["metrics"]["open_opportunity_href"]
        assert href == "/pipeline?status=open&bu=ST21&owner=777"
        assert overview["metrics"]["open_opportunity_count"] == 2
        assert overview["metrics"]["open_opportunity_business_units"] == ["ST21"]
        assert overview["tiles"]["pipeline"]["href"] == f"{href}&sow=none"
        assert next(row for row in overview["lifecycle_items"] if row["key"] == "pipeline")["href"] == \
            f"{href}&sow=none"
        # The link opens exactly the counted list.
        listed = (await api.get(href.removeprefix("/pipeline").replace("?", "/pipeline/workspace?", 1))).json()
    assert listed["page"]["total_rows"] == overview["metrics"]["open_opportunity_count"]
    assert listed["page"]["total_value_usd"] == overview["metrics"]["open_opportunity_value"]


async def test_a_region_without_a_business_unit_links_to_unmapped(session, frozen_clock):
    totals = await open_totals(session, PipelineFilters(business_unit=("Brazil",), include_closed=True,
                                                        open_closed="any"))
    assert totals.pipeline_query == {"bu": ["unmapped"]}


@pytest.mark.parametrize("path", ["/command-center/accounts", "/command-center/accounts.csv"])
async def test_watching_uses_the_dealgate_user_id(session, frozen_clock, path):
    # A HubSpot-created user: the DealGate id differs from the login id.
    owner, client, deals = await _population(session)
    stages = await _pipeline(session, "late")
    watched = await _deal(session, client=client, owner=owner, pipeline="late", stage=stages[4], name="Late stage")
    other = await _deal(session, client=client, owner=owner, pipeline="late", stage=stages[4], name="Not watched")
    session.add(WatchedItem(user_id=owner.id, kind="opportunity", item_id=watched.id))
    await session.commit()
    login = AuthUser(uuid.uuid4(), owner.email, owner.name, ("SalesLeader",))
    async with client_for(session, login, command_router) as api:
        response = await api.get(path, params={"health": "watching"})
    assert response.status_code == 200, response.text
    text = response.text
    assert "Late stage" in text and "Not watched" not in text
    assert isinstance(other, Opportunity)


# --- pre-merge review: the tile and its link describe the same list ------------------------------------------

REGION_OPTIONS = ("US", "US - IT Avalon", "US - IT Avalon (Staffing)", "Brazil", "Peru")


async def _regional_population(session):
    """The CC population plus deals in every kind of HubSpot region, tagged as the sync tags them."""
    owner, client, deals = await _population(session)
    stages = await _pipeline(session, "rg")
    for key in ("staffing", "brazil", "peru", "no_region"):
        deals[key] = await _deal(session, client=client, owner=owner, pipeline="rg", stage=stages[0], name=key)
        deals[key].hubspot_owner_id = "777"
    session.add(HubspotPropertyMapping(
        key="business_unit", internal_name="region", object_type="deal", label="Region", field_type="enumeration",
        availability_state="configured", mapping_version=1, options=[{"value": v} for v in REGION_OPTIONS]))
    session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    regions = {
        "plain": "US - IT Avalon", "won": "US - IT Avalon", "with_sow": "US - IT Avalon (Staffing)",
        "staffing": "US - IT Avalon (Staffing)", "linked": "US", "brazil": "Brazil", "peru": "Peru",
    }  # "lost" and "no_region" carry no region
    for key, value in regions.items():
        deals[key].business_unit_value, deals[key].business_unit_mapping_version = value, 1
        deals[key].business_unit_observed_at = NOW
    await session.commit()
    return owner, client, deals


async def _listed(api, href: str) -> dict:
    """The Pipeline list a Command Center link opens (the workspace answer for its query)."""
    # (httpx's ``params`` would replace the link's own query, so page_size is appended.)
    response = await api.get(f'{href.replace("/pipeline?", "/pipeline/workspace?", 1)}&page_size=100')
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(("region", "business_unit", "expected"), [
    # Both IT Avalon regions open the whole business unit, so both count it.
    ("US - IT Avalon", "IT Avalon", {"plain", "with_sow", "staffing"}),
    ("US - IT Avalon (Staffing)", "IT Avalon", {"plain", "with_sow", "staffing"}),
    # A value the map does not know opens every unmapped deal, those with no region included.
    ("Brazil", "unmapped", {"brazil", "peru", "no_region"}),
])
async def test_the_open_number_counts_the_list_its_link_opens(session, frozen_clock, region, business_unit,
                                                              expected):
    owner, _, deals = await _regional_population(session)
    user = AuthUser(owner.id, owner.email, owner.name, ("SalesLeader",))
    async with client_for(session, user, command_router, pipeline_router) as api:
        response = await api.get("/command-center/overview", params={"business_unit": region})
        assert response.status_code == 200, response.text
        metrics = response.json()["metrics"]
        assert metrics["open_opportunity_href"] == f"/pipeline?status=open&bu={business_unit.replace(' ', '+')}"
        listed = await _listed(api, metrics["open_opportunity_href"])
    assert {row["id"] for row in listed["rows"]} == {str(deals[key].id) for key in expected}
    assert (metrics["open_opportunity_count"], metrics["open_opportunity_value"]) == \
        (listed["page"]["total_rows"], listed["page"]["total_value_usd"]) == (len(expected), f"{125000 * len(expected)}.00")
    # The page names the business unit the number covers.
    assert metrics["open_opportunity_business_units"] == [business_unit]


async def test_an_owner_without_a_hubspot_link_gets_the_number_but_no_pipeline_link(session, frozen_clock):
    owner, client, _ = await _regional_population(session)
    stages = await _pipeline(session, "un")
    unlinked = User(email="uma.unlinked@example.test", name="Uma Unlinked", groups=["Sales"])
    session.add(unlinked)
    await session.flush()
    for name in ("Uma open one", "Uma open two"):
        deal = await _deal(session, client=client, owner=unlinked, pipeline="un", stage=stages[1], name=name)
        deal.hubspot_owner_id = "888"  # a HubSpot owner nobody in DealGate is linked to
    await session.commit()
    user = AuthUser(owner.id, owner.email, owner.name, ("SalesLeader",))
    async with client_for(session, user, command_router) as api:
        response = await api.get("/command-center/overview", params={"owner_id": str(unlinked.id)})
    assert response.status_code == 200, response.text
    overview = response.json()
    # The figure is the Command Center's own scope; no link claims the Pipeline shows it.
    assert overview["metrics"]["open_opportunity_count"] == 2
    assert overview["metrics"]["open_opportunity_value"] == "250000.00"
    assert overview["metrics"]["open_opportunity_href"] is None
    assert overview["metrics"]["open_opportunity_business_units"] == []
    assert overview["tiles"]["pipeline"]["href"] is None
    assert next(row for row in overview["lifecycle_items"] if row["key"] == "pipeline")["href"] is None
    assert next(row for row in overview["brief"] if row["kind"] == "opportunity")["href"] is None


async def test_the_unassigned_placeholder_owner_gets_no_pipeline_link(session, frozen_clock):
    owner, client, _ = await _regional_population(session)
    stages = await _pipeline(session, "ua")
    # HubSpot intake gives a deal whose owner it cannot resolve to this placeholder user.
    placeholder = User(email="unassigned@dealgate.local", name="Unassigned", groups=[])
    session.add(placeholder)
    await session.flush()
    await _deal(session, client=client, owner=placeholder, pipeline="ua", stage=stages[1], name="Ownerless")
    await session.commit()
    totals = await open_totals(session, PipelineFilters(owner=(placeholder.id,), **SCOPE))
    assert (totals.count, totals.value_usd, totals.pipeline_query) == (1, Decimal("125000.00"), None)


async def test_the_stricter_tile_opens_the_closest_pipeline_list(session, frozen_clock):
    owner, _, deals = await _population(session)
    user = AuthUser(owner.id, owner.email, owner.name, ("SalesLeader",))
    async with client_for(session, user, command_router, pipeline_router) as api:
        response = await api.get("/command-center/overview")
        assert response.status_code == 200, response.text
        overview = response.json()
        listed = await _listed(api, overview["tiles"]["pipeline"]["href"])
    # Open deals with no SOW: the tile's deal, plus the one linked to an engagement, which the
    # tile leaves out and the Pipeline cannot filter on (the page says so).
    assert overview["tiles"]["pipeline"]["eligible_deals"] == 1
    assert {row["id"] for row in listed["rows"]} == {str(deals["plain"].id), str(deals["linked"].id)}


async def test_the_revenue_outlook_still_counts_unscheduled_deals_that_have_a_sow(session, frozen_clock):
    # Open USD deals with no forecast schedule, each weighted 0.5 x 125,000: "plain" (no SOW) and
    # "with_sow" (a live Draft SOW); "linked" belongs to an engagement and is in neither number.
    await _population(session)
    overview = await build_command_overview(session, scope=PipelineFilters(**SCOPE))
    assert overview["revenue"]["unscheduled_weighted_pipeline"] == "125000.00"  # both, as before S23-PL2
    assert sum(Decimal(month["pipeline_upside"]) for month in overview["revenue"]["months"]) == 0
    # The stricter tile and the brief describe the deals with no SOW only.
    assert overview["tiles"]["pipeline"]["weighted"] == "62500.00"
    assert overview["tiles"]["pipeline"]["unscheduled_weighted"] == "62500.00"
    brief = next(row for row in overview["brief"] if row["kind"] == "opportunity")
    assert brief["detail"].startswith("62500.00 is unscheduled")
