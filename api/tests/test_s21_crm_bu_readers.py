"""Observed BU membership must reconcile across every pipeline projection."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_properties import HubspotPropertyMapping
from app.services.hubspot_pipeline import (
    PipelineFilters, _base_opportunity_filter, get_opportunity_row,
    list_clients, list_opportunities, list_pipeline_facets, summary,
)


NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


async def seed(session, object_type="deal"):
    mapping = HubspotPropertyMapping(key="business_unit", internal_name="selected_bu",
        object_type=object_type, label="Business Unit", field_type="enumeration",
        availability_state="configured", mapping_version=7,
        options=[{"value": "consulting", "label": "Consulting"},
                 {"value": "delivery", "label": "Delivery"},
                 {"value": "orphan", "label": "Orphan"}])
    owners = [User(email=f"bu-owner-{i}@example.test", name=f"Owner {i}", groups=[])
              for i in range(2)]
    session.add_all([mapping, *owners])
    await session.flush()
    deals, clients = [], []
    for index in range(24):
        kind = index % 8
        value = ["consulting", "delivery", None, "consulting", "consulting", "unknown", "", "consulting"][kind]
        company = Client(name=f"BU client {index:02}", hubspot_company_id=f"bu-company-{index}",
            business_unit_value="delivery", business_unit_mapping_version=7, business_unit_observed_at=NOW)
        session.add(company)
        await session.flush()
        deal = Opportunity(name=f"BU deal {index:02}", source="hubspot", hubspot_deal_id=f"bu-deal-{index}",
            client_id=company.id, owner_id=owners[index % 2].id, amount=Decimal(index + 1), currency="USD",
            hubspot_pipeline_id="main", hubspot_stage_id=f"stage-{index % 2}", stage_label="Open",
            is_closed_won=kind == 7, is_closed_lost=False,
            business_unit_value="delivery", business_unit_mapping_version=7, business_unit_observed_at=NOW)
        target = deal if object_type == "deal" else company
        target.business_unit_value = value
        target.business_unit_mapping_version = 6 if kind == 3 else 7
        target.business_unit_observed_at = None if kind == 4 else NOW
        session.add(deal)
        deals.append(deal)
        clients.append(company)
    session.add(Client(name="No matching deal", hubspot_company_id="orphan-company",
        business_unit_value="orphan", business_unit_mapping_version=7, business_unit_observed_at=NOW))
    await session.flush()
    return mapping, owners, clients, deals


@pytest.mark.parametrize("object_type", ["deal", "company"])
async def test_rows_filters_facets_and_three_pages_share_observed_population(session, object_type):
    _, _, clients, deals = await seed(session, object_type)
    filters = PipelineFilters(business_unit=("consulting",))
    pages = [await list_opportunities(session, filters=filters, page=p, page_size=1) for p in (1, 2, 3)]
    expected = [0, 8, 16]
    assert {row.opportunity_id for page in pages for row in page.items} == {deals[i].id for i in expected}
    assert all(page.total == 3 for page in pages)
    assert all(row.business_unit == "consulting" for page in pages for row in page.items)
    assert sum(row.count for row in pages[0].stage_counts) + pages[0].unknown_bucket == 3
    client_page = await list_clients(session, filters=filters)
    assert {row.client_id for row in client_page.items} == {clients[i].id for i in expected}
    assert client_page.total == 3
    aggregate = await summary(session, filters=filters)
    assert aggregate.open_count == 3 and aggregate.open_value_by_currency == {"USD": Decimal("27")}
    facets = await list_pipeline_facets(session, filters=PipelineFilters())
    assert facets.business_units == ("consulting", "delivery")
    for index, expected_bu in [(0, "consulting"), (1, "delivery"), (2, None), (3, None), (4, None), (5, None)]:
        row = await get_opportunity_row(session, opportunity_id=deals[index].id)
        assert row.business_unit == expected_bu


@pytest.mark.parametrize("object_type", ["deal", "company"])
async def test_missing_means_observed_empty_not_stale_unknown_or_unfetched(session, object_type):
    _, _, clients, deals = await seed(session, object_type)
    filters = PipelineFilters(missing=("business_unit",))
    expected = [2, 6, 10, 14, 18, 22]
    page = await list_opportunities(session, filters=filters)
    assert {row.opportunity_id for row in page.items} == {deals[i].id for i in expected}
    assert (await summary(session, filters=filters)).open_count == 6
    assert {row.client_id for row in (await list_clients(session, filters=filters)).items} == {clients[i].id for i in expected}
    assert (await list_pipeline_facets(session, filters=filters)).business_units == ()


@pytest.mark.parametrize("state", ["unknown", "absent", "ambiguous", "unavailable"])
async def test_unavailable_mapping_never_displays_or_classifies_old_values(session, state):
    mapping, _, _, deals = await seed(session)
    mapping.availability_state = state
    await session.flush()
    assert (await get_opportunity_row(session, opportunity_id=deals[0].id)).business_unit is None
    assert (await list_pipeline_facets(session)).business_units == ()
    for filters in [PipelineFilters(business_unit=("consulting",)), PipelineFilters(missing=("business_unit",))]:
        assert (await list_opportunities(session, filters=filters)).total == 0
        assert (await list_clients(session, filters=filters)).total == 0
        assert (await summary(session, filters=filters)).open_count == 0


@pytest.mark.parametrize("object_type", ["deal", "company"])
async def test_facets_do_not_leak_nonmatching_or_unauthorized_companies(session, object_type):
    _, owners, clients, deals = await seed(session, object_type)
    filters = PipelineFilters(owner=(owners[1].id,), authorized_client_ids=(clients[1].id,))
    assert (await list_pipeline_facets(session, filters=filters)).business_units == ("delivery",)
    assert (await list_opportunities(session, filters=filters)).items[0].opportunity_id == deals[1].id
    zero = PipelineFilters(opportunity_id=())
    assert (await list_pipeline_facets(session, filters=zero)).business_units == ()
    assert (await summary(session, filters=zero)).open_count == 0


async def test_unknown_raw_value_is_retained_but_not_a_named_bu_bucket(session):
    _, _, _, deals = await seed(session)
    filters = PipelineFilters(business_unit=("unknown", "wrong-source"))
    assert (await list_opportunities(session, filters=filters)).total == 0
    assert (await summary(session, filters=filters)).open_count == 0
    assert deals[5].business_unit_value == "unknown"


@pytest.mark.parametrize("dialect,function", [(postgresql.dialect(), "jsonb_array_elements"),
                                             (sqlite.dialect(), "json_each")])
def test_option_membership_compiles_for_both_supported_databases(dialect, function):
    query = select(Opportunity.id).join(Client, Client.id == Opportunity.client_id).where(
        *_base_opportunity_filter(PipelineFilters(business_unit=("consulting",))))
    sql = str(query.compile(dialect=dialect))
    assert function in sql
    assert "business_unit_observed_at" in sql and "business_unit_mapping_version" in sql
    assert "availability_state" in sql
