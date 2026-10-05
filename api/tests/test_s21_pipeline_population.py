"""Independent membership expectations for S21-09/11, T09 (local DB)."""
from decimal import Decimal
from datetime import date, timedelta

import pytest

from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.sow import Sow
from app.models.next_action import NextAction
from app.models.watchlist import WatchedItem
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.services.hubspot_pipeline import PipelineFilters, list_clients, list_opportunities, summary


@pytest.mark.asyncio
async def test_trusted_fixture_scope_precedes_every_population(session, population, monkeypatch):
    from app.services.hubspot_pipeline import scope_pipeline_filters
    from app.services.test_fixtures import create_fixture

    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "pipeline-lane")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    owners, _, _ = population
    test_user = User(email="scope@example.test", name="Test Reader", groups=["officeapp-e2e", "SystemAdmin"])
    session.add(test_user)
    await session.flush()
    fixture = await create_fixture(session, actor_id=test_user.id, label="Pipeline scope", reviewer_ids=[])
    deal = await session.get(Opportunity, fixture["opportunity_id"])
    deal.source = "hubspot"
    await session.flush()
    ordinary = await scope_pipeline_filters(session, owners[0], PipelineFilters())
    test_scope = await scope_pipeline_filters(session, test_user, PipelineFilters())
    assert (await list_opportunities(session, filters=ordinary)).total == 60
    assert (await list_clients(session, filters=ordinary)).total == 60
    assert (await summary(session, filters=ordinary)).open_count == 60
    assert [r.opportunity_id for r in (await list_opportunities(session, filters=test_scope)).items] == [deal.id]
    assert [r.client_id for r in (await list_clients(session, filters=test_scope)).items] == [fixture["client_id"]]
    assert (await summary(session, filters=test_scope)).open_count == 1
    # Binding a fixture to a real mirror identity invalidates the test grant.
    deal.hubspot_deal_id = "bound-to-crm"
    await session.flush()
    denied = await scope_pipeline_filters(session, test_user, PipelineFilters())
    assert (await list_opportunities(session, filters=denied)).total == 0
    assert (await list_clients(session, filters=denied)).total == 0
    assert (await summary(session, filters=denied)).open_count == 0


@pytest.fixture
async def population(session):
    owners = [User(email=f"population-{i}@example.test", name=f"Owner {i}", groups=[]) for i in range(2)]
    clients = [Client(name=f"Population client {i:02}", hubspot_company_id=f"population-{i}") for i in range(60)]
    session.add_all(owners + clients)
    await session.flush()
    deals = []
    for i, client in enumerate(clients):
        deal = Opportunity(source="hubspot", name=f"Population deal {i:02}",
            hubspot_deal_id=f"population-deal-{i}", client_id=client.id,
            owner_id=owners[i % 2].id,
            hubspot_pipeline_id="population", hubspot_stage_id=f"stage-{i % 4}",
            stage_label=f"Stage {i % 4}", amount=Decimal(i + 1), currency="USD",
            is_closed_won=False, is_closed_lost=False, governance_status="Intake")
        deals.append(deal)
    session.add_all(deals)
    await session.flush()
    return owners, clients, deals


@pytest.mark.asyncio
async def test_three_pages_share_exact_filtered_population(session, population):
    owners, clients, deals = population
    for filters, expected in [
        (PipelineFilters(owner=(owners[0].id,)), list(range(0, 60, 2))),
        (PipelineFilters(owner=(owners[0].id,), stage=("stage-0",)), list(range(0, 60, 4))),
        (PipelineFilters(owner=(owners[0].id,), stage=("stage-1",)), []),
    ]:
        rows = [await list_opportunities(session, filters=filters, page=p, page_size=25) for p in range(1, 4)]
        client_rows = [await list_clients(session, filters=filters, page=p, page_size=25) for p in range(1, 4)]
        assert {r.opportunity_id for page in rows for r in page.items} == {deals[i].id for i in expected}
        assert {r.client_id for page in client_rows for r in page.items} == {clients[i].id for i in expected}
        assert all(page.total == len(expected) for page in rows + client_rows)
        assert sum(s.count for s in rows[0].stage_counts) == len(expected)
        assert all(r.matching_deal_count == 1 for page in client_rows for r in page.items)
        aggregate = await summary(session, filters=filters)
        assert aggregate.open_count == len(expected)
        assert aggregate.open_value_by_currency.get("USD", Decimal(0)) == sum((Decimal(i + 1) for i in expected), Decimal(0))


@pytest.mark.asyncio
async def test_search_does_not_cross_join_unrelated_clients(session, population):
    _, clients, deals = population
    filters = PipelineFilters(search="Population deal 07")
    opportunity_page = await list_opportunities(session, filters=filters)
    client_page = await list_clients(session, filters=filters)
    aggregate = await summary(session, filters=filters)
    assert [r.opportunity_id for r in opportunity_page.items] == [deals[7].id]
    assert [r.client_id for r in client_page.items] == [clients[7].id]
    assert client_page.items[0].open_value_by_currency == {"USD": Decimal(8)}
    assert aggregate.open_count == 1
    assert aggregate.open_value_by_currency == {"USD": Decimal(8)}


@pytest.mark.asyncio
async def test_unavailable_bu_filter_never_silently_expands_population(session, population):
    filters = PipelineFilters(business_unit=("Not configured",))
    assert (await list_opportunities(session, filters=filters)).total == 0
    assert (await list_clients(session, filters=filters)).total == 0
    assert (await summary(session, filters=filters)).open_count == 0


@pytest.mark.asyncio
async def test_readiness_filters_before_paging_and_counts(session, population):
    _, clients, deals = population
    selected = [1, 28, 55]
    session.add_all([Sow(opportunity_id=deals[i].id) for i in selected])
    await session.flush()
    filters = PipelineFilters(readiness=("draft",))
    page = await list_opportunities(session, filters=filters, page_size=25)
    assert {r.opportunity_id for r in page.items} == {deals[i].id for i in selected}
    assert page.total == sum(s.count for s in page.stage_counts) == 3
    matching_clients = await list_clients(session, filters=filters, page_size=25)
    assert {r.client_id for r in matching_clients.items} == {clients[i].id for i in selected}
    assert (await summary(session, filters=filters)).open_count == 3


@pytest.mark.asyncio
async def test_attention_filters_before_paging_and_counts(session, population):
    _, clients, deals = population
    for i in (2, 29, 56):
        deals[i].owner_id = None
    await session.flush()
    filters = PipelineFilters(attention=("no_owner",))
    page = await list_opportunities(session, filters=filters, page_size=25)
    assert {r.opportunity_id for r in page.items} == {deals[i].id for i in (2, 29, 56)}
    assert page.total == sum(s.count for s in page.stage_counts) == 3
    assert (await list_clients(session, filters=filters)).total == 3
    assert (await summary(session, filters=filters)).open_count == 3


@pytest.mark.asyncio
async def test_summary_action_count_uses_selected_deals(session, population):
    owners, _, deals = population
    session.add_all([NextAction(opportunity_id=deal.id, description="Review",
        owner_user_id=owners[0].id, created_by=owners[0].id,
        due_date=date.today() - timedelta(days=1), status="open") for deal in deals])
    await session.flush()
    assert (await summary(session, filters=PipelineFilters(owner=(owners[0].id,)))).overdue_actions == 30
    assert (await summary(session, filters=PipelineFilters(owner=(owners[0].id,), stage=("stage-1",)))).overdue_actions == 0


@pytest.mark.asyncio
async def test_group_and_watch_axes_intersect_and_client_watches_expand(session, population):
    from app.models.tracking_group import TrackingGroup, TrackingGroupMember
    from app.models.watchlist import WatchedItem
    from app.routers.pipeline import _resolve_scope
    owners, clients, deals = population
    group = TrackingGroup(owner_id=owners[0].id, name="Selected", member_kind="opportunity", visibility="private")
    session.add(group)
    await session.flush()
    session.add_all([TrackingGroupMember(group_id=group.id, member_id=deals[i].id) for i in (0, 1)])
    session.add_all([WatchedItem(user_id=owners[0].id, kind="opportunity", item_id=deals[1].id),
                     WatchedItem(user_id=owners[0].id, kind="client", item_id=clients[2].id)])
    await session.flush()
    both = await _resolve_scope(session, user=owners[0], group_ids=[group.id], watching=True)
    assert set(both["opportunity_id"]) == {deals[1].id}
    watched = await _resolve_scope(session, user=owners[0], group_ids=None, watching=True)
    assert set(watched["opportunity_id"]) == {deals[1].id, deals[2].id}

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.auth import current_user
    from app.db import get_session
    from app.routers.pipeline import router
    app = FastAPI()
    app.include_router(router)
    owners[0].groups = ["Sales"]
    app.dependency_overrides[current_user] = lambda: owners[0]
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        query = {"group": str(group.id), "watching": "true"}
        opportunities = await http.get("/pipeline/opportunities", params=query)
        client_response = await http.get("/pipeline/clients", params=query)
        totals = await http.get("/pipeline/summary", params=query)
    assert opportunities.status_code == client_response.status_code == totals.status_code == 200
    assert [r["opportunity_id"] for r in opportunities.json()["items"]] == [str(deals[1].id)]
    assert [r["client_id"] for r in client_response.json()["items"]] == [str(clients[1].id)]
    assert opportunities.json()["total"] == client_response.json()["total"] == totals.json()["open_count"] == 1


@pytest.mark.asyncio
async def test_dynamic_group_has_no_first_200_cap(session, population):
    from app.models.tracking_group import TrackingGroup
    from app.routers.pipeline import _resolve_scope
    owners, clients, _ = population
    extras = [Opportunity(source="hubspot", name=f"Additional {i}", client_id=clients[0].id,
        owner_id=owners[0].id, governance_status="Intake") for i in range(201)]
    group = TrackingGroup(owner_id=owners[0].id, name="All owner's", member_kind="opportunity", visibility="private", filter_json={"owner": [str(owners[0].id)]})
    session.add_all(extras + [group])
    await session.flush()
    selected = await _resolve_scope(session, user=owners[0], group_ids=[group.id], watching=False)
    assert len(selected["opportunity_id"]) == 231
    assert {deal.id for deal in extras}.issubset(set(selected["opportunity_id"]))
