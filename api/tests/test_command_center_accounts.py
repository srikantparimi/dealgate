from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.client import Client
from app.models.approval import ApprovalPackage
from app.models.approval_routing import ApprovalAssignment
from app.models.engagement import (
    Allocation,
    AllocationActual,
    CalendarLocation,
    Engagement,
    ForecastPolicy,
    Resource,
)
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.auth import AuthUser, current_user
from app.db import get_session
from app.routers.command_center import router
from app.services.command_center import (
    CommandAccountFilters,
    build_command_overview,
    command_accounts_csv,
    list_command_accounts,
)
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
    close_date: date | None = None,
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
        close_date=close_date,
        currency="USD",
        governance_status="Signature",
        business_unit_value="ST21",
    )
    session.add(row)
    await session.flush()
    return row


async def _fixed_fee_engagement(
    session,
    *,
    client: Client,
    owner: User,
    opportunity: Opportunity | None,
    cost_per_hour: Decimal | None,
) -> Engagement:
    session.add(
        ForecastPolicy(
            hours_per_day=Decimal("8"), project_floor_pct=Decimal("0.35")
        )
    )
    session.add(
        CalendarLocation(
            name="US",
            burden_pct_w2=Decimal("0"),
            burden_pct_1099=Decimal("0"),
            resource_floor_pct=Decimal("0.35"),
        )
    )
    resource = Resource(
        name="Named consultant",
        location="US",
        employment_type="w2_employee",
        seniority="Senior",
    )
    engagement = Engagement(
        client_id=client.id,
        opportunity_id=opportunity.id if opportunity else None,
        hubspot_deal_id=opportunity.hubspot_deal_id if opportunity else None,
        name="Signed delivery",
        type="fixed_cost",
        start=date(2026, 10, 1),
        end=date(2026, 12, 31),
        total_price=Decimal("90000"),
        currency="USD",
        same_dates_for_all=True,
        owner_user_id=owner.id,
        business_unit="ST21",
    )
    session.add_all([resource, engagement])
    await session.flush()
    session.add(
        Allocation(
            engagement_id=engagement.id,
            resource_id=resource.id,
            role="Consultant",
            seniority="Senior",
            location="US",
            employment_type="w2_employee",
            utilization=Decimal("1"),
            bill_rate=None,
            cost_per_hour=cost_per_hour,
            rate_basis="hourly",
        )
    )
    await session.flush()
    return engagement


async def _approval_package(
    session,
    *,
    opportunity: Opportunity,
    submitter: User,
    status: str,
    submitted_at: datetime,
) -> ApprovalPackage:
    sow = Sow(opportunity_id=opportunity.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        sow_id=sow.id,
        uploaded_by=submitter.id,
        file_s3_key=f"command-center/{uuid.uuid4()}.pdf",
        file_hash="a" * 64,
    )
    session.add(version)
    await session.flush()
    model = GmModel(
        opportunity_id=opportunity.id,
        sow_id=sow.id,
        sow_version_id=version.id,
        engagement_type="fixed_assignment",
    )
    session.add(model)
    await session.flush()
    package = ApprovalPackage(
        opportunity_id=opportunity.id,
        sow_version_id=version.id,
        gm_model_id=model.id,
        package_hash=uuid.uuid4().hex * 2,
        routing_policy_version=2,
        status=status,
        submitted_by=submitter.id,
        submitted_at=submitted_at,
    )
    session.add(package)
    await session.flush()
    return package


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
    later = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="beta",
        stage=b[5],
        name="Later won",
        won=True,
        close_date=date.today(),
    )
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
    await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="search",
        stage=stages[5],
        name="Beta engagement",
        won=True,
        close_date=date.today(),
    )
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
    assert "Period revenue,Forecast GM,Assigned FTE,Required FTE,Financial status" in csv_text


@pytest.mark.asyncio
async def test_historical_closed_won_requires_current_delivery_context(session):
    owner = User(email="closed@example.test", name="Closed Owner", groups=[])
    client = Client(name="Closed account", hubspot_company_id="company-closed")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "closed")
    historical = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="closed",
        stage=stages[5],
        name="Historical win without current work",
        won=True,
        close_date=date(2025, 10, 2),
    )
    current = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="closed",
        stage=stages[5],
        name="Current-period win",
        won=True,
        close_date=date.today(),
    )
    delivering = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="closed",
        stage=stages[5],
        name="Historical win with current delivery",
        won=True,
        close_date=date(2025, 9, 1),
    )
    engagement = await _fixed_fee_engagement(
        session,
        client=client,
        owner=owner,
        opportunity=delivering,
        cost_per_hour=Decimal("50"),
    )
    await session.commit()

    page = await list_command_accounts(
        session, scope=PipelineFilters(include_closed=True)
    )

    ids = {row.opportunity_id for row in page.items}
    assert historical.id not in ids
    assert ids == {current.id, delivering.id}
    delivered_row = next(row for row in page.items if row.opportunity_id == delivering.id)
    assert delivered_row.engagement_id == engagement.id


@pytest.mark.asyncio
async def test_overview_excludes_historical_wins_and_period_scopes_potential(session):
    owner = User(email="period@example.test", name="Period Owner", groups=[])
    client = Client(name="Period account", hubspot_company_id="company-period")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "period")
    historical_win = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="period",
        stage=stages[5],
        name="2025 closed win",
        won=True,
        close_date=date(2025, 10, 2),
    )
    current_win = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="period",
        stage=stages[5],
        name="Current closed win",
        won=True,
        close_date=date.today(),
    )
    current_open = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="period",
        stage=stages[4],
        name="Current open deal",
        close_date=date.today(),
    )
    old_open = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="period",
        stage=stages[4],
        name="Overdue open deal",
        close_date=date(2025, 8, 1),
    )
    await session.commit()

    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        period="this_quarter",
        currency="USD",
    )

    assert overview["lifecycle"]["pipeline"] == 2
    # A CRM close date is not a service schedule. Both open deals remain in
    # weighted pipeline, but no amount is inserted into a monthly revenue bar.
    assert Decimal(overview["tiles"]["pipeline"]["gross"]) == Decimal("250000")
    assert Decimal(overview["tiles"]["pipeline"]["weighted"]) == Decimal("125000")
    assert Decimal(overview["tiles"]["pipeline"]["unscheduled_weighted"]) == Decimal("125000")
    assert Decimal(overview["revenue"]["potential_upside"]) == Decimal("0")
    assert Decimal(overview["revenue"]["potential_expected"]) == Decimal("0")
    action_ids = {row["id"] for row in overview["actions"]}
    assert str(current_win.id) in action_ids
    assert str(historical_win.id) not in action_ids
    assert str(current_open.id) not in action_ids
    assert str(old_open.id) not in action_ids


@pytest.mark.asyncio
async def test_overview_keeps_stage4_in_its_population_while_accounts_do_not(session):
    owner = User(email="scope@example.test", name="Scope Owner", groups=[])
    client = Client(name="Scope account", hubspot_company_id="company-scope")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "scope")
    await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="scope",
        stage=stages[3],
        name="Stage four remains in pulse",
    )
    included = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="scope",
        stage=stages[4],
        name="Stage five appears in table",
    )
    await session.commit()

    overview = await build_command_overview(
        session, scope=PipelineFilters(include_closed=True)
    )
    accounts = await list_command_accounts(
        session, scope=PipelineFilters(include_closed=True)
    )

    assert Decimal(overview["metrics"]["open_opportunity_value"]) == Decimal(
        "250000"
    )
    assert overview["lifecycle"]["pipeline"] == 2
    assert [row.opportunity_id for row in accounts.items] == [included.id]


@pytest.mark.asyncio
async def test_overview_uses_canonical_distinct_sow_approval_population(session):
    actor = User(
        email="command-approvals@example.test",
        name="Command Approver",
        groups=["SystemAdmin"],
    )
    client = Client(name="Approval account", hubspot_company_id="approval-account")
    session.add_all([actor, client])
    await session.flush()
    stages = await _pipeline(session, "approval-overview")
    deal = await _deal(
        session,
        client=client,
        owner=actor,
        pipeline="approval-overview",
        stage=stages[4],
        name="Two SOW approval packages",
    )
    first = await _approval_package(
        session,
        opportunity=deal,
        submitter=actor,
        status="pending_delivery_hr",
        submitted_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    second = await _approval_package(
        session,
        opportunity=deal,
        submitter=actor,
        status="pending_ceo_exception",
        submitted_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    await _approval_package(
        session,
        opportunity=deal,
        submitter=actor,
        status="ready_to_sign",
        submitted_at=datetime(2026, 10, 3, tzinfo=UTC),
    )
    session.add_all(
        [
            ApprovalAssignment(
                package_id=first.id,
                function=function,
                approver_id=actor.id,
                due_date=date(2026, 10, 20),
            )
            for function in ("delivery", "hr")
        ]
        + [
            ApprovalAssignment(
                package_id=second.id,
                function="executive",
                approver_id=actor.id,
                due_date=date(2026, 10, 21),
            )
        ]
    )
    await session.commit()

    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        actor=AuthUser(actor.id, actor.email, actor.name, tuple(actor.groups)),
    )

    lifecycle = next(
        row for row in overview["lifecycle_items"] if row["key"] == "sow_in_approval"
    )
    assert lifecycle["count"] == overview["metrics"]["sows_in_progress"] == 2
    assert lifecycle["href"].startswith(
        "/sows?status=in_review&population_revision="
    )
    revision = lifecycle["href"].rsplit("=", 1)[-1]
    assert len(revision) == 64 and int(revision, 16) >= 0
    approval_actions = [
        row for row in overview["actions"] if row["category"] == "Your SOW approval"
    ]
    assert {row["id"].split(":")[1] for row in approval_actions} == {
        str(first.id),
        str(second.id),
    }


@pytest.mark.asyncio
async def test_overview_keeps_later_page_ceo_approval_visible(session, monkeypatch):
    actor = User(
        email="older-ceo@example.test",
        name="Older CEO Approver",
        groups=["SystemAdmin"],
    )
    client = Client(name="Older approval account", hubspot_company_id="older-approval")
    session.add_all([actor, client])
    await session.flush()
    stages = await _pipeline(session, "older-approval")
    deal = await _deal(
        session,
        client=client,
        owner=actor,
        pipeline="older-approval",
        stage=stages[4],
        name="Older CEO package",
    )
    older = await _approval_package(
        session,
        opportunity=deal,
        submitter=actor,
        status="pending_ceo_exception",
        submitted_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    session.add(
        ApprovalAssignment(
            package_id=older.id,
            function="executive",
            approver_id=actor.id,
            due_date=date(2026, 10, 20),
        )
    )
    await session.commit()

    newer = [
        SimpleNamespace(
            id=uuid.uuid4(),
            opportunity_id=deal.id,
            status="pending_delivery_hr",
            routing_policy_version=2,
        )
        for _ in range(200)
    ]
    revision = "c" * 64
    calls = []

    async def paged_packages(_session, filters, *, expected_population_revision=None):
        calls.append((filters.page, expected_population_revision))
        rows = newer if filters.page == 1 else [older]
        return rows, 201, revision

    monkeypatch.setattr(
        "app.services.command_center_overview.list_in_review_packages",
        paged_packages,
    )

    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        actor=AuthUser(actor.id, actor.email, actor.name, tuple(actor.groups)),
    )

    assert calls == [(1, None), (2, revision)]
    lifecycle = next(
        row for row in overview["lifecycle_items"] if row["key"] == "sow_in_approval"
    )
    assert lifecycle == {
        "key": "sow_in_approval",
        "label": "SOW in approval",
        "count": 201,
        "entity": "SOWs",
        "href": f"/sows?status=in_review&population_revision={revision}",
    }
    assert any(
        row["id"] == f"approval:{older.id}:executive" for row in overview["actions"]
    )


@pytest.mark.asyncio
async def test_overview_reconciles_real_forecast_without_double_counting_pipeline(session):
    owner = User(email="finance@example.test", name="Finance Owner", groups=[])
    client = Client(name="Finance account", hubspot_company_id="company-finance")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "finance")
    deal = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="finance",
        stage=stages[4],
        name="Signed fixed fee",
    )
    engagement = await _fixed_fee_engagement(
        session,
        client=client,
        owner=owner,
        opportunity=deal,
        cost_per_hour=Decimal("50"),
    )
    engagement.start = date(2026, 9, 1)
    engagement.total_price = Decimal("120000")
    allocation = await session.scalar(
        select(Allocation).where(Allocation.engagement_id == engagement.id)
    )
    assert allocation is not None
    session.add(AllocationActual(
        allocation_id=allocation.id,
        month="2026-09",
        hours=Decimal("120"),
        revenue=Decimal("24000"),
    ))
    await session.commit()

    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        period="this_quarter",
        currency="USD",
    )

    # The GM tile is current month, not a quarter-wide blended margin.
    # October carries one third of the fixed fee and has 22 weekdays.
    expected_gm = (Decimal("30000") - Decimal("8800")) / Decimal("30000")
    assert Decimal(overview["revenue"]["remaining_signed"]) == Decimal("90000")
    assert overview["revenue"]["actual"] is None
    assert overview["tiles"]["revenue"]["actual_to_date"] is None
    assert overview["tiles"]["revenue"]["actual_cutoff"] is None
    assert overview["tiles"]["revenue"]["latest_actual_month"] == "2026-09"
    assert Decimal(overview["tiles"]["revenue"]["latest_actual"]) == Decimal("24000")
    assert Decimal(overview["metrics"]["committed_gm_pct"]) == expected_gm
    assert Decimal(overview["revenue"]["potential_expected"]) == 0
    assert Decimal(overview["revenue"]["potential_upside"]) == 0
    assert overview["revenue"]["cost_coverage_complete"] is True
    assert overview["metrics"]["planned_people"] == 1
    assert overview["lifecycle"]["active"] == 1
    assert overview["lifecycle"]["pipeline"] == 0


@pytest.mark.asyncio
async def test_known_revenue_stays_visible_when_a_staff_cost_is_missing(session):
    owner = User(email="missing@example.test", name="Missing Cost Owner", groups=[])
    client = Client(name="Missing cost account", hubspot_company_id="company-missing")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "missing")
    deal = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="missing",
        stage=stages[4],
        name="Known fee, unknown cost",
    )
    await _fixed_fee_engagement(
        session,
        client=client,
        owner=owner,
        opportunity=deal,
        cost_per_hour=None,
    )
    await session.commit()

    overview = await build_command_overview(
        session, scope=PipelineFilters(include_closed=True), currency="USD"
    )

    assert Decimal(overview["revenue"]["remaining_signed"]) == Decimal("90000")
    assert overview["metrics"]["committed_gm_pct"] is None
    assert overview["revenue"]["cost_coverage_complete"] is False
    assert overview["tiles"]["gm"]["covered_engagements"] == 0
    assert overview["tiles"]["gm"]["total_engagements"] == 1
    assert Decimal(overview["tiles"]["gm"]["revenue_coverage_pct"]) == 0
    assert overview["tiles"]["gm"]["missing_cost_engagements"] == 1
    assert any(
        "cost" in blocker.lower()
        for blocker in overview["revenue"]["financial_blockers"]
    )


@pytest.mark.asyncio
async def test_future_missing_rate_does_not_hide_current_month_gm(session):
    owner = User(email="future-cost@example.test", name="Future Cost Owner", groups=[])
    client = Client(name="Future cost account", hubspot_company_id="company-future-cost")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "future-cost")
    deal = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="future-cost",
        stage=stages[4],
        name="Current cost is complete",
    )
    engagement = await _fixed_fee_engagement(
        session,
        client=client,
        owner=owner,
        opportunity=deal,
        cost_per_hour=Decimal("50"),
    )
    engagement.same_dates_for_all = False
    future_resource = Resource(
        name="Future consultant",
        location="US",
        employment_type="w2_employee",
        seniority="Senior",
    )
    session.add(future_resource)
    await session.flush()
    session.add(Allocation(
        engagement_id=engagement.id,
        resource_id=future_resource.id,
        role="Consultant",
        seniority="Senior",
        location="US",
        employment_type="w2_employee",
        utilization=Decimal("1"),
        cost_per_hour=None,
        start=date(2026, 12, 1),
        end=date(2026, 12, 31),
        rate_basis="hourly",
    ))
    await session.commit()

    overview = await build_command_overview(
        session, scope=PipelineFilters(include_closed=True), currency="USD"
    )

    assert overview["tiles"]["gm"]["value"] is not None
    assert overview["tiles"]["gm"]["covered_engagements"] == 1
    assert overview["tiles"]["gm"]["missing_cost_engagements"] == 0
    assert not any(row["category"] == "Missing costs" for row in overview["actions"])


@pytest.mark.asyncio
async def test_capacity_uses_the_existing_dated_allocation_service(session, monkeypatch):
    owner = User(email="capacity@example.test", name="Capacity Owner", groups=[])
    client = Client(name="Capacity account", hubspot_company_id="company-capacity")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "capacity")
    deal = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="capacity",
        stage=stages[4],
        name="Dated staffed delivery",
    )
    await _fixed_fee_engagement(
        session,
        client=client,
        owner=owner,
        opportunity=deal,
        cost_per_hour=Decimal("50"),
    )
    await session.commit()

    async def allocation(*_args, **_kwargs):
        return {
            "complete": True,
            "missing": [],
            "sources": [{"source_as_of": "2026-10-12T20:00:00+00:00"}],
            "intervals": [
                {
                    "start": "2026-10-01",
                    "end": "2026-12-31",
                    "demands": [
                        {
                            "id": "demand-1",
                            "source_id": "plan-1",
                            "account_id": str(client.id),
                            "account_name": client.name,
                            "title": "Delivery plan",
                            "role": "Consultant",
                            "required_fte": "2.5",
                            "gap_fte": "0.5",
                            "source_url": f"/forecast?account_id={client.id}",
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr("app.services.people_allocation.demand_allocation", allocation)
    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        currency="USD",
        actor=AuthUser(owner.id, owner.email, owner.name, ("SystemAdmin",)),
    )

    capacity = overview["capacity"]
    assert Decimal(capacity["required_fte"]) == Decimal("2.5")
    assert Decimal(capacity["allocated_fte"]) == Decimal("2.0")
    assert Decimal(capacity["gap_fte"]) == Decimal("0.5")
    assert capacity["status"] == "attention"
    assert capacity["source_as_of"] == "2026-10-12T20:00:00+00:00"
    assert capacity["locations"][0]["location"] == "US"
    assert capacity["gaps"] == [{
        "account": "Capacity account",
        "title": "Delivery plan",
        "role": "Consultant",
        "href": f"/forecast?account_id={client.id}",
        "gap_fte": "0.50",
    }]
    workforce = next(row for row in overview["sources"] if row["name"] == "Workforce supply")
    assert workforce["status"] == "current"

    accounts = await list_command_accounts(
        session,
        scope=PipelineFilters(include_closed=True),
        actor=AuthUser(owner.id, owner.email, owner.name, ("SystemAdmin",)),
    )
    assert accounts.items[0].assigned_fte == Decimal("1")
    assert accounts.items[0].required_fte == Decimal("2.5")

    async def incomplete_allocation(*_args, **_kwargs):
        result = await allocation(*_args, **_kwargs)
        result["complete"] = False
        result["missing"] = ["workforce_capability"]
        return result

    monkeypatch.setattr(
        "app.services.people_allocation.demand_allocation", incomplete_allocation
    )
    incomplete = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        currency="USD",
        actor=AuthUser(owner.id, owner.email, owner.name, ("SystemAdmin",)),
    )
    assert incomplete["capacity"]["required_fte"] == "2.50"
    assert incomplete["capacity"]["allocated_fte"] is None
    assert incomplete["capacity"]["gap_fte"] is None
    assert incomplete["capacity"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_overview_includes_unlinked_imported_engagement_actuals_and_open_seats(session):
    owner = User(email="ledger@example.test", name="Ledger Owner", groups=[])
    client = Client(name="Imported ledger account", hubspot_company_id="company-ledger")
    session.add_all([owner, client])
    await session.flush()
    engagement = await _fixed_fee_engagement(
        session,
        client=client,
        owner=owner,
        opportunity=None,
        cost_per_hour=Decimal("50"),
    )
    named = await session.scalar(
        select(Allocation).where(Allocation.engagement_id == engagement.id)
    )
    assert named is not None
    named.utilization = Decimal("0.5")
    session.add(
        AllocationActual(
            allocation_id=named.id,
            month="2026-10",
            hours=Decimal("40"),
            revenue=Decimal("10000"),
        )
    )
    open_resource = Resource(
        name="TBC",
        location="US",
        employment_type="w2_employee",
        seniority="Senior",
    )
    session.add(open_resource)
    await session.flush()
    session.add(
        Allocation(
            engagement_id=engagement.id,
            resource_id=open_resource.id,
            person="TBC",
            role="Consultant",
            seniority="Senior",
            location="US",
            employment_type="w2_employee",
            utilization=Decimal("0.5"),
            bill_rate=None,
            cost_per_hour=Decimal("50"),
            rate_basis="hourly",
        )
    )
    await session.commit()

    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        currency="USD",
    )

    assert Decimal(overview["tiles"]["revenue"]["forecast"]) == Decimal("30000")
    assert Decimal(overview["tiles"]["revenue"]["actual_to_date"]) == Decimal("10000")
    assert overview["tiles"]["revenue"]["actual_cutoff"] is not None
    assert overview["tiles"]["people"]["billable_people"] == 1
    assert Decimal(overview["tiles"]["people"]["billable_fte"]) == Decimal("0.5")
    assert overview["tiles"]["people"]["open_seats"] == 1
    assert Decimal(overview["tiles"]["people"]["open_seat_fte"]) == Decimal("0.5")
    assert overview["lifecycle"]["engagement_created"] == 1


@pytest.mark.asyncio
async def test_forecast_beyond_signed_term_becomes_contract_coverage_action(session, monkeypatch):
    owner = User(email="coverage@example.test", name="Coverage Owner", groups=[])
    client = Client(name="Coverage account", hubspot_company_id="company-coverage")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "coverage")
    deal = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="coverage",
        stage=stages[4],
        name="Forecast extends past contract",
    )
    engagement = await _fixed_fee_engagement(
        session,
        client=client,
        owner=owner,
        opportunity=deal,
        cost_per_hour=Decimal("50"),
    )
    await session.commit()

    async def forecast(*_args, **_kwargs):
        return {
            "rows": [{
                "opportunity_id": str(deal.id),
                "month": "2027-01-01",
                "lifecycle": "tentative",
                "expected": "12000",
                "revenue": "15000",
            }],
        }

    monkeypatch.setattr(
        "app.services.command_center_overview._forecast_outlook", forecast
    )
    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        currency="USD",
        actor=AuthUser(owner.id, owner.email, owner.name, ("SystemAdmin",)),
    )

    action = next(
        row for row in overview["actions"]
        if row["category"] == "Contract coverage"
    )
    assert action["id"] == f"contract-coverage:{engagement.id}"
    assert Decimal(action["impact"]) == Decimal("12000")
    assert action["period"] == "2027-01"
    assert action["action"] == "Review contract coverage"


@pytest.mark.asyncio
async def test_expected_renewal_allocates_over_its_full_proposed_term(session):
    owner = User(email="renewal-view@example.test", name="Renewal View Owner", groups=[])
    client = Client(name="Renewal view account", hubspot_company_id="company-renewal-view")
    session.add_all([owner, client])
    await session.flush()
    stages = await _pipeline(session, "renewal-view")
    deal = await _deal(
        session,
        client=client,
        owner=owner,
        pipeline="renewal-view",
        stage=stages[4],
        name="Twelve-month renewal",
    )
    session.add(Renewal(
        opportunity_id=deal.id,
        term_end=date(2026, 12, 31),
        trigger_date=date(2026, 10, 31),
        status="open",
        likelihood="likely",
        proposed_amount=Decimal("120000"),
        currency="USD",
        proposed_start=date(2027, 1, 1),
        proposed_end=date(2027, 12, 31),
        probability=Decimal("0.75"),
        probability_basis="Priced proposal sent to client",
    ))
    await session.commit()

    overview = await build_command_overview(
        session,
        scope=PipelineFilters(include_closed=True),
        period="next_two_quarters",
        currency="USD",
    )

    assert all(
        Decimal(row["expected_renewal"]) == Decimal("7500")
        for row in overview["revenue"]["months"]
    )
    assert Decimal(overview["revenue"]["potential_expected"]) == Decimal("45000")


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
