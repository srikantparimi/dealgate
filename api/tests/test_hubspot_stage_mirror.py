"""S19 slice 1 · pipeline / stage mirror + mapper.

Acceptance:
- sync_stage_mirror upserts every pipeline and stage HubSpot returns.
- The returned StageMap resolves stage id → label + is_closed + won/lost.
- Backfill through _upsert_opportunity populates every new opportunity
  column: stage_label (real label), is_closed_won / is_closed_lost,
  stage_order, currency, hubspot_created_at, hubspot_last_modified_at,
  hubspot_last_activity_at, primary_client_id, hubspot_pipeline_id,
  hubspot_stage_id.
- Multi-company deal fixture (G3) records secondary_client_ids.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.hubspot import StubHubSpotClient
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.services.hubspot_backfill import run_backfill
from app.services.hubspot_stage_mirror import sync_stage_mirror


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("SALES_LEADER_EMAIL", raising=False)


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _pipeline() -> dict:
    return {
        "id": "710688094",
        "label": "SmarTek21 Global Pipeline",
        "displayOrder": 2,
        "archived": False,
        "stages": [
            {"id": "1038193692", "label": "1-Initial Contact/Prospecting",
             "displayOrder": 0,
             "metadata": {"isClosed": "false", "probability": "0.1"}, "archived": False},
            {"id": "1038553758", "label": "7-Closed Won", "displayOrder": 6,
             "metadata": {"isClosed": "true", "probability": "1.0"}, "archived": False},
            {"id": "1038553759", "label": "8-Closed Lost", "displayOrder": 7,
             "metadata": {"isClosed": "true", "probability": "0.0"}, "archived": False},
        ],
    }


def _deal(deal_id: str, stage_id: str, *, amount="10000.00", currency="USD",
          owner="42", company_id: str | None = "555",
          extra_companies: list[str] | None = None) -> dict:
    companies_results = []
    if company_id:
        companies_results.append({"id": company_id, "type": "deal_to_company"})
        companies_results.append({"id": company_id, "type": "deal_to_company_unlabeled"})
    for cid in extra_companies or []:
        companies_results.append({"id": cid, "type": "deal_to_company"})
    return {
        "id": deal_id,
        "properties": {
            "dealname": f"Deal {deal_id}",
            "dealstage": stage_id,
            "pipeline": "710688094",
            "hubspot_owner_id": owner,
            "amount": amount,
            "deal_currency_code": currency,
            "closedate": "2026-12-31",
            "createdate": "2025-01-15T10:00:00Z",
            "hs_lastmodifieddate": "2026-09-20T12:34:56Z",
            "notes_last_updated": "2026-09-25T08:00:00Z",
        },
        "associations": {"companies": {"results": companies_results}},
    }


def _owner(owner_id: str = "42", email: str = "rep@smartek21.com") -> dict:
    return {"id": owner_id, "email": email, "firstName": "Rep", "lastName": "One"}


def _company(company_id: str = "555", name: str = "Acme") -> dict:
    return {"id": company_id, "properties": {"name": name, "domain": f"{name.lower()}.com"}}


async def test_sync_stage_mirror_upserts_and_resolves(factory):
    stub = StubHubSpotClient(pipelines=[_pipeline()])
    async with factory() as s:
        stage_map = await sync_stage_mirror(s, stub)
        await s.commit()

    async with factory() as s:
        pipelines = (await s.execute(select(HubspotPipeline))).scalars().all()
        stages = (await s.execute(select(HubspotStage))).scalars().all()
    assert {p.id for p in pipelines} == {"710688094"}
    assert {s.id for s in stages} == {"1038193692", "1038553758", "1038553759"}

    won = stage_map.resolve("1038553758")
    assert won and won.label == "7-Closed Won"
    assert won.is_closed and won.is_closed_won and not won.is_closed_lost
    lost = stage_map.resolve("1038553759")
    assert lost and lost.is_closed_lost and not lost.is_closed_won
    open_stage = stage_map.resolve("1038193692")
    assert open_stage and not open_stage.is_closed


async def test_backfill_populates_all_new_columns(factory):
    stub = StubHubSpotClient(
        pipelines=[_pipeline()],
        deals={"deal-won": _deal("deal-won", "1038553758")},
        owners={"42": _owner()},
        companies={"555": _company()},
    )
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.errors == 0
    assert counts.deals_created == 1

    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.stage_label == "7-Closed Won"        # was the id in §2a
    assert opp.hubspot_stage_id == "1038553758"
    assert opp.hubspot_pipeline_id == "710688094"
    assert opp.stage_order == 6
    assert opp.is_closed_won is True
    assert opp.is_closed_lost is False
    assert opp.currency == "USD"
    assert opp.hubspot_created_at is not None
    assert opp.hubspot_last_modified_at is not None
    assert opp.hubspot_last_activity_at is not None
    # G3: primary_client_id points at the resolved primary company; no
    # extras on this deal so secondary_client_ids is None.
    assert opp.primary_client_id is not None
    assert opp.hubspot_secondary_client_ids in (None, [])


async def test_backfill_records_secondary_companies_for_multi_company_deal(factory):
    stub = StubHubSpotClient(
        pipelines=[_pipeline()],
        deals={"ey-multi": _deal("ey-multi", "1038553759", company_id="555",
                                  extra_companies=["666", "777"])},
        owners={"42": _owner()},
        companies={"555": _company("555", "EY SA"),
                   "666": _company("666", "EY UK"),
                   "777": _company("777", "EY US")},
    )
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.errors == 0
    assert counts.multi_company_deals == 1

    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.primary_client_id is not None
    # secondary list contains the other two client ids (order preserved
    # from the deal's association list, primary already stripped)
    assert isinstance(opp.hubspot_secondary_client_ids, list)
    assert len(opp.hubspot_secondary_client_ids) == 2


async def test_backfill_marks_closed_lost_when_stage_is_lost(factory):
    stub = StubHubSpotClient(
        pipelines=[_pipeline()],
        deals={"deal-lost": _deal("deal-lost", "1038553759")},
        owners={"42": _owner()},
        companies={"555": _company()},
    )
    await run_backfill(stub, session_factory=factory)
    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.is_closed_won is False
    assert opp.is_closed_lost is True
    assert opp.stage_label == "8-Closed Lost"


async def test_backfill_leaves_open_deal_closed_flags_false(factory):
    stub = StubHubSpotClient(
        pipelines=[_pipeline()],
        deals={"deal-open": _deal("deal-open", "1038193692")},
        owners={"42": _owner()},
        companies={"555": _company()},
    )
    await run_backfill(stub, session_factory=factory)
    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.is_closed_won is False
    assert opp.is_closed_lost is False
    assert opp.stage_label == "1-Initial Contact/Prospecting"


async def test_backfill_falls_back_gracefully_when_stage_unknown(factory):
    """G11: an unknown stage id should not crash; the row keeps the id in
    stage_label so the drift is visible."""

    stub = StubHubSpotClient(
        pipelines=[_pipeline()],
        deals={"deal-drift": _deal("deal-drift", "999999_unmirrored")},
        owners={"42": _owner()},
        companies={"555": _company()},
    )
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.errors == 0
    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    # Unknown stage_id falls through: label = raw id, closed flags stay false.
    assert opp.stage_label == "999999_unmirrored"
    assert opp.is_closed_won is False
    assert opp.is_closed_lost is False
