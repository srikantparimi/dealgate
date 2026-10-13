from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.models.client import Client
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.user import User
from app.auth import AuthUser, current_user
from app.db import get_session
from app.routers.command_center import router
from app.services.command_center import CommandAccountFilters, command_accounts_csv, list_command_accounts
from app.services.hubspot_pipeline import PipelineFilters


async def _pipeline(session, pipeline_id: str, count: int = 7) -> list[HubspotStage]:
    session.add(HubspotPipeline(id=pipeline_id, label=f"Pipeline {pipeline_id}", display_order=0, archived=False))
    stages = []
    for index in range(count):
        stage = HubspotStage(
            id=f"{pipeline_id}-opaque-{index}",
            pipeline_id=pipeline_id,
            label=f"Stage {index + 1}",
            display_order=(index + 1) * 10,
            is_closed=index >= 5,
            probability=Decimal("1") if index == 5 else Decimal("0") if index == 6 else Decimal("0.5"),
            archived=False,
        )
        session.add(stage)
        stages.append(stage)
    await session.flush()
    return stages


async def _deal(
    session,
    *,
    client: Client,
    owner: User,
    pipeline: str,
    stage: HubspotStage | None,
    name: str,
    source: str = "hubspot",
    won: bool = False,
    lost: bool = False,
) -> Opportunity:
    row = Opportunity(
        source=source,
        hubspot_deal_id=f"hs-{uuid.uuid4()}" if source == "hubspot" else None,
        name=name,
        client_id=client.id,
        owner_id=owner.id,
        hubspot_pipeline_id=pipeline,
        hubspot_stage_id=stage.id if stage else "missing-stage",
        stage_label=stage.label if stage else "Unknown",
        stage_order=stage.display_order if stage else None,
        is_closed_won=won,
        is_closed_lost=lost,
        amount=Decimal("125000"),
        currency="USD",
        governance_status="Signature",
        business_unit_value="ST21",
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_stage5_is_resolved_per_pipeline_and_not_from_stage_ids(session):
    owner = User(email="owner@example.test", name="Owner", groups=[])
    client = Client(name="Eligible account", hubspot_company_id="company-1")
    session.add_all([owner, client])
    await session.flush()
    a = await _pipeline(session, "alpha")
    b = await _pipeline(session, "beta")
    await _deal(session, client=client, owner=owner, pipeline="alpha", stage=a[3], name="Stage four")
    fifth = await _deal(session, client=client, owner=owner, pipeline="alpha", stage=a[4], name="Stage five")
    later = await _deal(session, client=client, owner=owner, pipeline="beta", stage=b[5], name="Later won", won=True)
    await session.commit()

    page = await list_command_accounts(session, scope=PipelineFilters(include_closed=True))

    assert {row.opportunity_id for row in page.items} == {fifth.id, later.id}
    assert page.scope_label == "HubSpot deals · Stage 5 and above"
    assert page.configuration_gaps == ()


@pytest.mark.asyncio
async def test_sow_governance_does_not_change_sales_stage_eligibility(session):
    owner = User(email="owner2@example.test", name="Owner Two", groups=[])
    client = Client(name="Workflow independent", hubspot_company_id="company-2")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "workflow")
    deal = await _deal(session, client=client, owner=owner, pipeline="workflow", stage=stages[4], name="Qualifying")
    await session.commit()

    first = await list_command_accounts(session, scope=PipelineFilters(include_closed=True))
    deal.governance_status = "Handoff"
    await session.commit()
    second = await list_command_accounts(session, scope=PipelineFilters(include_closed=True))

    assert [row.opportunity_id for row in first.items] == [deal.id]
    assert [row.opportunity_id for row in second.items] == [deal.id]


@pytest.mark.asyncio
async def test_unknown_unlinked_lost_and_unconfigured_rows_are_explicit(session):
    owner = User(email="owner3@example.test", name="Owner Three", groups=[])
    client = Client(name="Boundary account", hubspot_company_id="company-3")
    session.add_all([owner, client])
    await session.flush()
    good = await _pipeline(session, "good")
    short = await _pipeline(session, "short", count=4)
    eligible = await _deal(session, client=client, owner=owner, pipeline="good", stage=good[4], name="Included")
    await _deal(session, client=client, owner=owner, pipeline="good", stage=None, name="Unknown")
    await _deal(session, client=client, owner=owner, pipeline="good", stage=good[4], name="Local", source="sow_upload")
    await _deal(session, client=client, owner=owner, pipeline="good", stage=good[6], name="Lost", lost=True)
    await _deal(session, client=client, owner=owner, pipeline="short", stage=short[3], name="No threshold")
    await session.commit()

    page = await list_command_accounts(session, scope=PipelineFilters(include_closed=True))

    assert [row.opportunity_id for row in page.items] == [eligible.id]
    assert page.configuration_gaps == ("Pipeline short has no identifiable Stage 5 threshold",)


@pytest.mark.asyncio
async def test_search_pagination_and_csv_share_the_eligible_population(session):
    owner = User(email="owner4@example.test", name="Owner Four", groups=[])
    client = Client(name="Searchable account", hubspot_company_id="company-4")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "search")
    await _deal(session, client=client, owner=owner, pipeline="search", stage=stages[4], name="Alpha engagement")
    await _deal(session, client=client, owner=owner, pipeline="search", stage=stages[5], name="Beta engagement", won=True)
    await _deal(session, client=client, owner=owner, pipeline="search", stage=stages[3], name="Hidden engagement")
    await session.commit()

    filters = CommandAccountFilters(search="engagement", page=2, page_size=1)
    page = await list_command_accounts(session, scope=PipelineFilters(include_closed=True), filters=filters)
    csv_text = await command_accounts_csv(
        session,
        scope=PipelineFilters(include_closed=True),
        filters=CommandAccountFilters(search="engagement", page=1, page_size=100),
    )

    assert page.total == 2
    assert len(page.items) == 1
    assert "Alpha engagement" in csv_text
    assert "Beta engagement" in csv_text
    assert "Hidden engagement" not in csv_text


@pytest.mark.asyncio
async def test_command_center_endpoints_require_a_pipeline_reader_role(session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: AuthUser(
        uuid.uuid4(), "viewer@example.test", "Viewer", ()
    )

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        accounts = await client.get("/command-center/accounts")
        overview = await client.get("/command-center/overview")

    assert accounts.status_code == 403
    assert overview.status_code == 403
