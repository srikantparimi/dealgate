"""S24-AG1 B10 / F6 / F7 (lane BE-C) — the Pipeline and the Command Center on the shared agreement service.

* Parity (T12's API half): the Pipeline's "Agreement gaps" card equals the Agreements page's Needs-attention
  card for the same caller, the list it drills into is exactly those clients, and every Pipeline row carries
  the state the Agreements page gives that client — one service (``agreement_status.classify``), one deal set.
* The meaning of ``missing=nda|msa|agreements``: the state ``missing``, never "no file".
* The Command Center tile counts every client the caller may see, whatever its business-unit or owner filter.
* The Agreements page's own loader still reads the population without the facts join (``with_agreements``
  defaults to False), and the derived table is built once.

The shared PL2 seed (tests/test_s23_pl2_workspace.py) carries the cutover and stored relationships; the cases
it lacks (stage 1 only, Hold only, a first Closed Won deal after the cutover) are added per test.
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import get_args

import pytest
from sqlalchemy import update

from app.auth import AuthUser
from app.models.agreements import AgreementsSettings
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.routers.pipeline import DocState
from app.services.agreement_pipeline import (
    agreement_scope,
    attention_clients,
    facts_subquery,
    needs_attention_href,
)
from app.services.agreement_status import DOC_STATES, load_agreement_population
from app.services.canonical_user import Viewer
from app.services.command_center import build_command_overview
from app.services.hubspot_pipeline import PipelineFilters
from app.services.pipeline_workspace import DRILLS, load_population, load_reference
from tests import test_s23_pl2_workspace as shared
from tests.test_s23_pl2_workspace import (
    NEEDS_ATTENTION,
    PIPELINE_ID,
    STAGES,
    TODAY,
    VIEWER,
    client_for,
    day,
    seed_population,
    workspace,
)

# Shared fixtures, bound as module globals so pytest finds them here.
api, engine, frozen_clock, seeded = shared.api, shared.engine, shared.frozen_clock, shared.seeded

GAP_DRILL = {"tab": "clients", "status": "all", "missing": "agreements", "include_unmatched_clients": "false"}


async def _add_client(session, name: str, *, relationship: str | None = None, deals=()) -> uuid.UUID:
    """A client with HubSpot deals given as (stage ordinal 1-9, close offset in days or None)."""
    client = Client(name=name, hubspot_company_id=f"c-{name.lower().replace(' ', '-')}",
                    relationship=relationship, relationship_basis="none" if relationship else None)
    session.add(client)
    await session.flush()
    for index, (ordinal, close) in enumerate(deals):
        sid, label, order, _ = STAGES[ordinal - 1]
        session.add(Opportunity(
            source="hubspot", hubspot_deal_id=f"hs-{client.id.hex[:8]}-{index}", name=f"{name} deal {index}",
            client_id=client.id, hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid, stage_label=label,
            stage_order=order, is_closed_won=ordinal == 7, is_closed_lost=ordinal == 8,
            amount=Decimal("1000"), currency="USD", close_date=day(close) if close is not None else None,
            governance_status="Intake"))
    await session.commit()
    return client.id


async def _agreements_side(session, user: AuthUser = VIEWER) -> dict[uuid.UUID, object]:
    """The Agreements page's statuses for the caller (its own loader and scope)."""
    pop = await load_agreement_population(session, user)
    return {client_id: facts.status for client_id, facts in pop.clients.items()}


async def _assert_parity(api, session) -> set[str]:
    """Gap card == Needs-attention card == the drilled list; every client's states equal on both pages."""
    statuses = await _agreements_side(session)
    attention = {str(cid) for cid, status in statuses.items() if status.needs_attention}
    body = await workspace(api)
    gap = body["metrics"]["agreement_gap_clients"]
    drilled = await workspace(api, **GAP_DRILL, page_size=100)
    assert gap["value"] == len(attention) == drilled["page"]["total_rows"]
    assert {row["id"] for row in drilled["rows"]} == attention
    every = await workspace(api, tab="clients", include_unmatched_clients="true", status="all", page_size=100)
    for row in every["rows"]:
        status = statuses[uuid.UUID(row["id"])]
        assert row["agreements"] == {
            "nda_on_file": status.nda in ("client", "standard"), "msa_on_file": status.msa in ("client", "standard"),
            "nda_state": status.nda, "msa_state": status.msa}, row["name"]
    deals = await workspace(api, status="all", page_size=100)
    for row in deals["rows"]:
        if row["client"]["id"] is not None:
            status = statuses[uuid.UUID(row["client"]["id"])]
            assert (row["agreements"]["nda_state"], row["agreements"]["msa_state"]) == (status.nda, status.msa)
    return attention


# --- parity -------------------------------------------------------------------------------------


async def test_the_gap_card_is_the_agreements_needs_attention_card(api, seeded, session):
    attention = await _assert_parity(api, session)
    assert attention == {str(seeded.clients[key]) for key in NEEDS_ATTENTION}
    assert DRILLS["agreement_gap_clients"] == {"tab": "clients", "status": "all", "missing": "agreements",
                                               "include_unmatched_clients": False}


async def test_parity_holds_before_the_cutover_too(api, seeded, session):
    # No cutover and nothing stamped: the relationship is live (provisional) on both pages.
    settings = await session.get(AgreementsSettings, 1)
    settings.cutover_date = None
    await session.execute(update(Client).values(relationship=None, relationship_basis=None,
                                                relationship_set_by=None, relationship_set_at=None))
    nova = await _add_client(session, "Nova Retail", deals=[(3, 20)])  # stage 3, nothing held
    await session.commit()
    attention = await _assert_parity(api, session)
    # Every seeded client with a deal has an SOW or a win (existing); Nova is net new past stage 1.
    assert attention == {str(nova)}


async def test_the_rules_the_seed_lacks(api, seeded, session):
    stage_one = await _add_client(session, "Orbit Media", relationship="net_new", deals=[(1, 10)])
    on_hold = await _add_client(session, "Pine Labs", relationship="net_new", deals=[(9, 10)])
    won_after = await _add_client(session, "Quartz Analytics", relationship="net_new", deals=[(7, -2)])
    unknown = await _add_client(session, "Rowan Health", relationship="net_new", deals=[(1, 5)])
    # Rowan's deal sits in a stage the mirror no longer has: it cannot be placed, so it warns.
    await session.execute(update(Opportunity).where(Opportunity.client_id == unknown).values(
        hubspot_stage_id="retired-stage"))
    await session.commit()
    attention = await _assert_parity(api, session)
    rows = {row["name"]: row for row in (await workspace(api, tab="clients", status="all", page_size=100))["rows"]}
    assert (rows["Orbit Media"]["agreements"]["nda_state"], rows["Orbit Media"]["agreements"]["msa_state"]) == (
        "due_later", "due_later")
    assert rows["Pine Labs"]["agreements"]["nda_state"] == "missing"  # Hold counts as past stage 1
    assert rows["Quartz Analytics"]["agreements"]["nda_state"] == "missing"  # a first win after the cutover
    assert rows["Rowan Health"]["agreements"]["nda_state"] == "missing"
    assert {str(on_hold), str(won_after), str(unknown)} <= attention and str(stage_one) not in attention
    # A Closed Won-only client is in the card (every status) but not in the default open list's filter.
    open_missing = await workspace(api, tab="clients", missing="agreements", page_size=100)
    assert "Quartz Analytics" not in {row["name"] for row in open_missing["rows"]}
    assert "Pine Labs" in {row["name"] for row in open_missing["rows"]}


# --- the missing filter -------------------------------------------------------------------------


async def test_missing_means_the_state_missing_also_for_clients_without_matching_deals(api, seeded):
    body = await workspace(api, tab="clients", include_unmatched_clients="true", missing="msa", sort="name")
    assert [row["name"] for row in body["rows"]] == ["Bolt Logistics", "Echo Media"]
    # Bolt and Echo have no Closed Won deal, so they come in as clients without matching deals.
    won = await workspace(api, tab="clients", include_unmatched_clients="true", missing="msa", status="won",
                          sort="name")
    assert [(row["name"], row["matching_deals"]) for row in won["rows"]] == [("Bolt Logistics", 0),
                                                                             ("Echo Media", 0)]
    every = await workspace(api, tab="clients", include_unmatched_clients="true", sort="name")
    assert len(every["rows"]) == 7  # without a missing filter every visible client is still listed


# --- the Agreements page's own loader and the derived table ------------------------------------------------


async def test_the_population_without_facts_is_unchanged(session, seeded):
    reference = await load_reference(session)
    deals, any_agreement = await load_population(
        session, PipelineFilters(include_closed=True, open_closed="any"), viewer=Viewer(None, None, None),
        reference=reference, today=TODAY, with_sow=False)
    assert len(deals) == 15 and any_agreement is True
    assert all(d.agreement_facts is None and d.nda_state is None and not d.nda for d in deals)
    assert facts_subquery() is facts_subquery()  # built once per process


def test_the_wire_states_are_the_shared_services():
    assert get_args(DocState) == DOC_STATES


# --- the Command Center tile (F7) -------------------------------------------------------------------------


async def _clear_activity(session) -> None:
    # The Command Center's old list code subtracts SQLite's naive activity timestamps from an aware "now"
    # (hubspot_pipeline.list_opportunities; pre-existing, never on Postgres), as test_s23_pl2_workspace notes.
    await session.execute(update(Opportunity).values(hubspot_last_activity_at=None))
    await session.commit()


async def test_the_command_center_tile_is_the_needs_attention_card(session, seeded):
    await _clear_activity(session)
    statuses = await _agreements_side(session)
    expected = sum(1 for status in statuses.values() if status.needs_attention)
    overview = await build_command_overview(session, scope=PipelineFilters(include_closed=True, open_closed="any"))
    assert overview["metrics"]["agreement_attention_clients"] == expected == len(NEEDS_ATTENTION)
    assert overview["metrics"]["agreement_attention_href"] == needs_attention_href() == "/agreements?status=attention"
    assert set(overview["tiles"]) == {"revenue", "gm", "backlog", "pipeline", "people"}  # no new tile key
    # The dashboard's business unit and owner do not narrow it: the NDA & MSA page counts every client.
    scoped = await build_command_overview(session, scope=PipelineFilters(
        business_unit=("US",), owner=(seeded.writer,), include_closed=True, open_closed="any"))
    assert scoped["metrics"]["agreement_attention_clients"] == expected


async def test_the_tile_keeps_fixture_visibility(session, seeded):
    hidden = PipelineFilters(include_closed=True, open_closed="any", hidden_client_ids=(seeded.clients["bolt"],),
                             business_unit=("US",))
    assert agreement_scope(hidden) == PipelineFilters(include_closed=True, open_closed="any",
                                                      hidden_client_ids=(seeded.clients["bolt"],))
    assert await attention_clients(session, hidden) == len(NEEDS_ATTENTION) - 1


async def test_the_overview_endpoint_sends_the_tile(session, seeded):
    from app.routers.command_center import router as command_router

    await _clear_activity(session)
    leader = AuthUser(uuid.uuid4(), "leader@example.test", "Lee Leader", ("SalesLeader",))
    async with client_for(session, leader, command_router) as client:
        response = await client.get("/command-center/overview", params={"business_unit": "US"})
    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    assert (metrics["agreement_attention_clients"], metrics["agreement_attention_href"]) == (
        len(NEEDS_ATTENTION), "/agreements?status=attention")


# --- Postgres (the dialect the derived table and the date conversions really run on) --------------------------

POSTGRES = pytest.mark.skipif(not os.environ.get("DEALGATE_POSTGRES_URL"),
                              reason="requires the migrated local Postgres")


@POSTGRES
async def test_parity_on_postgres(frozen_clock):
    from tests.test_s23_pl2_cost import rolled_back_postgres

    async with rolled_back_postgres() as (session, _pg):
        seed = await seed_population(session, region_map=False)
        async with client_for(session, VIEWER) as client:
            attention = await _assert_parity(client, session)
        assert attention == {str(seed.clients[key]) for key in NEEDS_ATTENTION}
        settings = await session.get(AgreementsSettings, 1)
        assert settings.cutover_date == TODAY - timedelta(days=30)
