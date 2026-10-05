"""Independent Pipeline population and trust oracles; isolated SQLite only."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.models.user import User
from app.models.watchlist import WatchedItem
from app.routers.pipeline import _resolve_scope
from app.services import test_fixtures
from app.services.hubspot_pipeline import (
    PipelineFilters, list_clients, list_opportunities, scope_pipeline_filters, summary,
)

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "independent-pipeline")
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")


async def owner(session, *, fixture=False):
    row = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@independent.test", name="QA Owner",
               groups=["Sales", "SystemAdmin"] + (["officeapp-e2e"] if fixture else []))
    session.add(row)
    await session.flush()
    return row


async def population(session, count=1):
    user = await owner(session)
    clients = [Client(id=uuid.uuid4(), name=f"QA Account {i:03}") for i in range(count)]
    session.add_all(clients)
    await session.flush()
    deals = [Opportunity(id=uuid.uuid4(), source="hubspot", name=f"QA Deal {i:03}",
        client_id=client.id, owner_id=user.id, governance_status="Intake",
        hubspot_pipeline_id="primary", hubspot_stage_id="qualified", stage_label="Qualified",
        is_closed_won=False, is_closed_lost=False, amount=Decimal(i + 1), currency="USD")
        for i, client in enumerate(clients)]
    session.add_all(deals)
    await session.flush()
    return user, clients, deals


async def sow(session, user, deal, *, status=None, archived=False, submitted_at=NOW):
    source = Sow(id=uuid.uuid4(), opportunity_id=deal.id, archived_at=NOW if archived else None)
    session.add(source)
    await session.flush()
    version = SowVersion(id=uuid.uuid4(), sow_id=source.id, uploaded_by=user.id,
        file_s3_key=f"qa/{source.id}.pdf", file_hash="a" * 64, extract_status="complete")
    session.add(version)
    await session.flush()
    if status:
        gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_id=source.id,
                     sow_version_id=version.id, engagement_type="tm", created_by=user.id)
        session.add(gm)
        await session.flush()
        session.add(ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
            gm_model_id=gm.id, package_hash="b" * 64, status=status,
            submitted_by=user.id, submitted_at=submitted_at))
        await session.flush()
    return source


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["readiness", "attention"])
async def test_filtered_membership_values_and_totals_reconcile_across_three_pages(session, axis):
    user, clients, deals = await population(session, 84)
    selected = [i for i in range(84) if i % 3 != 0]
    for i in selected:
        if axis == "readiness":
            await sow(session, user, deals[i])
        else:
            deals[i].owner_id = None
    await session.flush()
    filters = PipelineFilters(**{axis: ("draft" if axis == "readiness" else "no_owner",)})
    opp_pages = [await list_opportunities(session, filters=filters, page=p, page_size=25, now=NOW) for p in range(1, 5)]
    client_pages = [await list_clients(session, filters=filters, page=p, page_size=25, now=NOW) for p in range(1, 5)]
    assert {row.opportunity_id for page in opp_pages for row in page.items} == {deals[i].id for i in selected}
    assert {row.client_id for page in client_pages for row in page.items} == {clients[i].id for i in selected}
    assert [len(page.items) for page in opp_pages] == [25, 25, 6, 0]
    assert all(page.total == 56 for page in opp_pages + client_pages)
    assert all(sum(stage.count for stage in page.stage_counts) + page.unknown_bucket == 56 for page in opp_pages)
    assert all(row.matching_deal_count == 1 for page in client_pages for row in page.items)
    result = await summary(session, filters=filters, now=NOW)
    assert result.open_count == 56 and result.open_value_by_currency == {"USD": Decimal("2408")}


@pytest.mark.asyncio
async def test_zero_population_and_explicit_no_match_client_toggle(session):
    user, clients, _ = await population(session, 3)
    filters = PipelineFilters(owner=(uuid.uuid4(),))
    for page in (1, 99):
        opportunities = await list_opportunities(session, filters=filters, page=page, now=NOW)
        accounts = await list_clients(session, filters=filters, page=page, now=NOW)
        assert opportunities.items == accounts.items == ()
        assert opportunities.total == accounts.total == 0
    restored = await list_clients(session, filters=replace(filters, show_clients_without_matches=True), now=NOW)
    assert {row.client_id for row in restored.items} == {client.id for client in clients}
    assert all(row.matching_deal_count == 0 and not row.open_value_by_currency for row in restored.items)
    assert (await summary(session, filters=filters, now=NOW)).open_count == 0


@pytest.mark.asyncio
async def test_group_union_watch_intersection_and_dynamic_population_beyond_200(session):
    user, clients, deals = await population(session, 231)
    dynamic = TrackingGroup(id=uuid.uuid4(), owner_id=user.id, name="All owned", member_kind="opportunity",
        visibility="private", filter_json={"owner": [str(user.id)]})
    manual = TrackingGroup(id=uuid.uuid4(), owner_id=user.id, name="Subset", member_kind="opportunity", visibility="private")
    session.add_all([dynamic, manual])
    await session.flush()
    session.add_all([TrackingGroupMember(group_id=manual.id, member_id=deals[i].id) for i in (1, 230)])
    session.add_all([WatchedItem(user_id=user.id, kind="opportunity", item_id=deals[1].id),
        WatchedItem(user_id=user.id, kind="client", item_id=clients[230].id)])
    await session.flush()
    full = await _resolve_scope(session, user=user, group_ids=[dynamic.id], watching=False)
    assert set(full["opportunity_id"]) == {deal.id for deal in deals}
    selected = await _resolve_scope(session, user=user, group_ids=[dynamic.id, manual.id], watching=True)
    assert set(selected["opportunity_id"]) == {deals[1].id, deals[230].id}
    filters = await scope_pipeline_filters(session, user, PipelineFilters(opportunity_id=selected["opportunity_id"]))
    assert (await list_opportunities(session, filters=filters, now=NOW)).total == 2
    assert (await list_clients(session, filters=filters, now=NOW)).total == 2
    assert (await summary(session, filters=filters, now=NOW)).open_value_by_currency == {"USD": Decimal("233")}


@pytest.mark.asyncio
async def test_dynamic_group_preserves_pipeline_qualified_stage_identity(session):
    user, _, deals = await population(session, 2)
    deals[1].hubspot_pipeline_id = "other-pipeline"
    group = TrackingGroup(owner_id=user.id, name="Primary qualified", member_kind="opportunity", visibility="private",
        filter_json={"pipeline": "primary", "stage": ["qualified"]})
    session.add(group)
    await session.flush()
    selected = await _resolve_scope(session, user=user, group_ids=[group.id], watching=False)
    assert set(selected["opportunity_id"]) == {deals[0].id}


@pytest.mark.asyncio
async def test_later_released_sibling_cannot_hide_pending_sow_attention(session):
    user, _, deals = await population(session)
    await sow(session, user, deals[0], status="pending_delivery_hr", submitted_at=NOW - timedelta(days=2))
    await sow(session, user, deals[0], status="released", submitted_at=NOW - timedelta(days=1))
    filters = PipelineFilters(attention=("pending_approval",))
    rows = await list_opportunities(session, filters=filters, now=NOW)
    assert [row.opportunity_id for row in rows.items] == [deals[0].id]
    assert (await list_clients(session, filters=filters, now=NOW)).total == 1
    assert (await summary(session, filters=filters, now=NOW)).pending_approvals == 1


@pytest.mark.asyncio
async def test_archived_sow_cannot_supply_current_readiness_or_pending_counts(session):
    user, _, deals = await population(session)
    await sow(session, user, deals[0])
    await sow(session, user, deals[0], status="pending_finance_legal", archived=True)
    rows = await list_opportunities(session, filters=PipelineFilters(readiness=("draft",)), now=NOW)
    assert [row.opportunity_id for row in rows.items] == [deals[0].id]
    assert rows.items[0].sow_count == 1
    assert (await summary(session, now=NOW)).pending_approvals == 0


@pytest.mark.asyncio
async def test_client_readiness_agrees_with_its_single_matching_uploaded_draft(session):
    user, _, deals = await population(session)
    await sow(session, user, deals[0])
    filters = PipelineFilters(readiness=("draft",))
    rows = await list_opportunities(session, filters=filters, now=NOW)
    clients = await list_clients(session, filters=filters, now=NOW)
    assert rows.items[0].sow_approval_state == "draft"
    assert clients.items[0].worst_sow_approval_state == "draft"


@pytest.mark.asyncio
async def test_client_attention_excludes_closed_won_deal_outside_selected_owner(session):
    user, clients, deals = await population(session, 2)
    other = await owner(session)
    deals[1].client_id, deals[1].owner_id, deals[1].is_closed_won = clients[0].id, other.id, True
    await session.flush()
    filters = PipelineFilters(owner=(user.id,))
    rows = await list_opportunities(session, filters=filters, now=NOW)
    accounts = await list_clients(session, filters=filters, now=NOW)
    assert [row.opportunity_id for row in rows.items] == [deals[0].id]
    assert accounts.items[0].matching_deal_count == 1
    assert "closed_won_not_released" not in accounts.items[0].attention_flags


@pytest.mark.asyncio
async def test_unknown_currency_is_not_relabelled_usd_in_stage_chip(session):
    _, _, deals = await population(session)
    deals[0].currency = None
    await session.flush()
    rows = await list_opportunities(session, now=NOW)
    accounts = await list_clients(session, now=NOW)
    aggregate = await summary(session, now=NOW)
    assert aggregate.open_value_by_currency == accounts.items[0].open_value_by_currency == {"UNK": Decimal("1")}
    assert rows.stage_counts[0].open_value_by_currency == {"UNK": Decimal("1")}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ["valid", "foreign_tenant", "foreign_environment", "expired", "mirrored", "wrong_owner"])
async def test_fixture_scope_applies_before_deal_client_and_summary_counts(session, monkeypatch, invalidity):
    ordinary, business_clients, business_deals = await population(session)
    tester = await owner(session, fixture=True)
    issued = await test_fixtures.create_fixture(session, actor_id=tester.id, label="Pipeline QA", reviewer_ids=[], hours=1)
    fixture_deal = await session.get(Opportunity, issued["opportunity_id"])
    fixture_deal.source = "hubspot"
    if invalidity == "foreign_tenant":
        monkeypatch.setenv("DEALGATE_TENANT_ID", "other")
    elif invalidity == "foreign_environment":
        monkeypatch.setenv("DEALGATE_ENV", "staging")
    elif invalidity == "mirrored":
        fixture_deal.hubspot_deal_id = "real-crm-reference"
    elif invalidity == "wrong_owner":
        fixture_deal.owner_id = ordinary.id
    elif invalidity == "expired":
        later = datetime.now(UTC) + timedelta(hours=2)
        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return later.astimezone(tz) if tz else later.replace(tzinfo=None)
        monkeypatch.setattr(test_fixtures, "datetime", ExpiredClock)
    await session.flush()
    for reader, expected_deals, expected_clients in (
        (ordinary, {business_deals[0].id}, {business_clients[0].id}),
        (tester, {fixture_deal.id} if invalidity == "valid" else set(),
         {issued["client_id"]} if invalidity == "valid" else set()),
    ):
        filters = await scope_pipeline_filters(session, reader, PipelineFilters())
        deals = await list_opportunities(session, filters=filters, now=NOW)
        clients = await list_clients(session, filters=filters, now=NOW)
        assert {row.opportunity_id for row in deals.items} == expected_deals
        assert {row.client_id for row in clients.items} == expected_clients
        assert deals.total == clients.total == (await summary(session, filters=filters, now=NOW)).open_count == len(expected_deals)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["opportunities", "clients"])
async def test_http_rejects_page_zero_and_preserves_total_on_out_of_range_page(session, path):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.auth import current_user
    from app.db import get_session
    from app.routers.pipeline import router

    user, _, _ = await population(session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        invalid = await client.get(f"/pipeline/{path}", params={"page": 0})
        empty = await client.get(f"/pipeline/{path}", params={"page": 99})
    assert invalid.status_code == 422
    assert empty.status_code == 200, empty.text
    assert empty.json()["items"] == [] and empty.json()["total"] == 1
