"""S20 W2 Session 3b · single-opportunity + pipeline-stages endpoints.

Powers the /deals/{id} detail page:
- `get_opportunity_row` returns the same shape as `list_opportunities`
  per row (OpportunityRow) but for a single id — reuses the same
  correlated subqueries so SOW state, attention flags, next-action
  counts, BU, pipeline_id and close flags are consistent.
- `list_pipeline_stages` returns ordered stages from the mirror for
  the ordered stage strip on /deals/{id}.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.client import Client
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_pipeline import (
    SowApprovalState,
    get_opportunity_row,
    list_pipeline_stages,
)


@pytest.mark.asyncio
async def test_get_opportunity_row_returns_same_shape_as_list(session):
    owner = User(email="rep@dealgate.local", name="Sam Rep", groups=[])
    client = Client(name="BSC Staffing Ltd", hubspot_company_id="34959929030")
    session.add_all([owner, client])
    await session.flush()

    opp = Opportunity(
        source="hubspot",
        hubspot_deal_id="65211153545",
        name="BSC Staffing - UX/UI Designer",
        owner_id=owner.id,
        client_id=client.id,
        sales_stage="4-Proposal",
        stage_label="4-Proposal",
        hubspot_pipeline_id="710688094",
        hubspot_stage_id="1038193695",
        stage_order=3,
        is_closed_won=False,
        is_closed_lost=False,
        amount=Decimal("20000"),
        currency="USD",
        close_date=date(2026, 10, 30),
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()

    row = await get_opportunity_row(session, opportunity_id=opp.id)
    assert row is not None
    assert row.opportunity_id == opp.id
    assert row.name == "BSC Staffing - UX/UI Designer"
    assert row.hubspot_deal_id == "65211153545"
    assert row.client_name == "BSC Staffing Ltd"
    assert row.stage_id == "1038193695"
    assert row.stage_label == "4-Proposal"
    assert row.owner_name == "Sam Rep"
    assert row.owner_email == "rep@dealgate.local"
    assert row.amount == Decimal("20000")
    assert row.currency == "USD"
    assert row.hubspot_pipeline_id == "710688094"
    assert row.is_closed_won is False
    assert row.is_closed_lost is False
    assert row.sow_approval_state == SowApprovalState.NONE.value


@pytest.mark.asyncio
async def test_get_opportunity_row_returns_none_when_missing(session):
    row = await get_opportunity_row(session, opportunity_id=uuid.uuid4())
    assert row is None


@pytest.mark.asyncio
async def test_get_opportunity_row_excludes_archived(session):
    client = Client(name="Archived Corp")
    session.add(client)
    await session.flush()

    opp = Opportunity(
        source="hubspot",
        hubspot_deal_id="99999",
        client_id=client.id,
        sales_stage="1-Discovery",
        stage_label="1-Discovery",
        hubspot_pipeline_id="710688094",
        hubspot_stage_id="1038193690",
        archived_at=datetime.now(tz=UTC) - timedelta(days=1),
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()

    row = await get_opportunity_row(session, opportunity_id=opp.id)
    assert row is None, "archived deals must not surface in /deals/:id"


@pytest.mark.asyncio
async def test_list_pipeline_stages_returns_ordered_mirror(session):
    pipeline = HubspotPipeline(id="710688094", label="Sales", display_order=0)
    session.add(pipeline)
    await session.flush()

    session.add_all(
        [
            HubspotStage(
                id="1038193690",
                pipeline_id="710688094",
                label="1-Discovery",
                display_order=0,
                is_closed=False,
                probability=Decimal("0.10"),
            ),
            HubspotStage(
                id="1038193695",
                pipeline_id="710688094",
                label="4-Proposal",
                display_order=3,
                is_closed=False,
                probability=Decimal("0.60"),
            ),
            HubspotStage(
                id="1038193692",
                pipeline_id="710688094",
                label="3-Proposal",
                display_order=2,
                is_closed=False,
                probability=Decimal("0.30"),
            ),
            HubspotStage(
                id="closedwon",
                pipeline_id="710688094",
                label="Closed Won",
                display_order=99,
                is_closed=True,
                probability=Decimal("1.0"),
            ),
            HubspotStage(
                id="closedlost",
                pipeline_id="710688094",
                label="Closed Lost",
                display_order=100,
                is_closed=True,
                probability=Decimal("0.0"),
            ),
            # archived stage — must NOT be returned.
            HubspotStage(
                id="oldstage",
                pipeline_id="710688094",
                label="Retired stage",
                display_order=50,
                archived=True,
            ),
        ]
    )
    await session.commit()

    stages = await list_pipeline_stages(session, pipeline_id="710688094")
    labels = [s.stage_label for s in stages]
    assert labels == ["1-Discovery", "3-Proposal", "4-Proposal", "Closed Won", "Closed Lost"]
    # Closed Won / Lost carry the right flags.
    won = next(s for s in stages if s.stage_id == "closedwon")
    lost = next(s for s in stages if s.stage_id == "closedlost")
    assert won.is_closed_won and not won.is_closed_lost
    assert lost.is_closed_lost and not lost.is_closed_won


@pytest.mark.asyncio
async def test_list_pipeline_stages_empty_when_pipeline_unknown(session):
    stages = await list_pipeline_stages(session, pipeline_id="99999")
    assert stages == ()


@pytest.mark.asyncio
async def test_list_pipeline_facets_returns_owners_from_deal_owners(session):
    """S3b Rev-2 · owners facet lists users with at least one non-archived
    HubSpot opportunity — never a HubSpot owner without a local deal."""
    from app.services.hubspot_pipeline import list_pipeline_facets

    owner_a = User(email="a@dealgate.local", name="Alice Owner", groups=[])
    owner_b = User(email="b@dealgate.local", name="Bob Owner", groups=[])
    owner_c = User(email="c@dealgate.local", name="Charlie NoDeals", groups=[])
    session.add_all([owner_a, owner_b, owner_c])
    client = Client(name="Facets Corp")
    session.add(client)
    await session.flush()
    session.add_all(
        [
            Opportunity(
                source="hubspot",
                hubspot_deal_id="F1",
                owner_id=owner_a.id,
                client_id=client.id,
                sales_stage="1-Discovery",
                stage_label="1-Discovery",
                hubspot_pipeline_id="710688094",
                hubspot_stage_id="STAGE",
                governance_status="Intake",
            ),
            Opportunity(
                source="hubspot",
                hubspot_deal_id="F2",
                owner_id=owner_b.id,
                client_id=client.id,
                sales_stage="1-Discovery",
                stage_label="1-Discovery",
                hubspot_pipeline_id="710688094",
                hubspot_stage_id="STAGE",
                governance_status="Intake",
            ),
        ]
    )
    await session.commit()

    facets = await list_pipeline_facets(session)
    names = [o.name for o in facets.owners]
    assert names == ["Alice Owner", "Bob Owner"], (
        f"expected only owners with deals; got {names}"
    )
    # BUs are empty in this seed (D10 evidence — property absent).
    assert facets.business_units == ()
