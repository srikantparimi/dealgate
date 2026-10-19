"""S24-AG1 T8 (lane T-C) — HubSpot msa_type with fixtures only (StubHubSpotClient; never a real token).

Extends test_s24_ag1_bed_hubspot.py / test_s24_ag1_bed_pg.py (lane BE-D) through the nightly sync itself
(run_deal_sync('nightly', ...) on the savepoint engine, as test_s23_pl1_sync_trust.py does) and through the
routes people use:

* the value is stored on the deal and reaches the client panel as the MSA card's hint, never as a state;
* after an admin saves a mapping, the post-sync apply marks the MSA covered only for clients holding nothing
  for the MSA: a client copy, a standard copy, a DealGate mark and a mark Legal removed are untouched
  (DealGate's record always wins); it credits the admin who LAST saved the mapping; the HubspotSyncRun record
  and the outcome counts are exactly those of the same sync on a database without a mapping;
* it never runs after a failed sync (HubSpot unreadable, stage metadata down, a crash) or a partial one, and
  runs after the next successful one;
* the hint is the value on the most recently modified deal that has one, and follows HubSpot's later edits;
  a mark already made stays when HubSpot later clears the value or the mapping is emptied;
* GET /agreements/hubspot-values says stored=false (no items) before any value, even with a saved mapping;
* a stopped post-sync apply keeps its committed chunks and says how far it got (bug #97), the sync still ends
  ok with an unchanged run record, and the next nightly sync finishes the rest without duplicates.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.hubspot import StubHubSpotClient
from app.models.agreements import AgreementMark, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.hubspot_sync_run import HubspotSyncRun
from app.models.opportunity import Opportunity
from app.models.user import User
from app.routers.agreements_hubspot import router as hubspot_router
from app.routers.agreements_workspace import router as workspace_router
from app.routers.client_agreements import router as panel_router
from app.services import agreement_audit, agreement_hubspot, hubspot_sync_runs
from app.services.agreement_hubspot import save_mapping
from app.services.agreement_status import load_agreement_population
from app.services.hubspot_sync_runs import run_deal_sync
from tests.conftest import _memory_engine
from tests.s24_pg import POSTGRES, scratch_postgres

ADMIN_A = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000008a1"), "ada@example.test", "Ada Admin", ("SystemAdmin",))
ADMIN_B = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000008b2"), "bea@example.test", "Bea Admin", ("SystemAdmin",))
LEGAL = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000008c3"), "lee@example.test", "Lee Legal", ("Legal",))
SALES = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000008d4"), "sam@example.test", "Sam Sales", ("Sales",))
SIGNED = "Signed MSA"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("SALES_LEADER_EMAIL", raising=False)
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


@pytest_asyncio.fixture
async def engine(savepoint_engine):
    # Per-deal SAVEPOINTs roll back with their page, as on PostgreSQL (S23-PL1).
    return savepoint_engine


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def fresh_factory():
    """A second database: the same sync without a mapping (the baseline for the run record)."""
    engine = await _memory_engine(postgres_like_transactions=True)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()


def hs_deal(deal_id: str, *, company: str, msa: str | None = None, stage: str = "qualifiedtobuy",
            modified: str = "2026-10-13T12:00:00Z") -> dict:
    props = {"dealname": f"Deal {deal_id}", "dealstage": stage, "pipeline": "default", "amount": "1000",
             "deal_currency_code": "USD", "closedate": "2026-12-31", "hs_lastmodifieddate": modified}
    if msa is not None:
        props["msa_type"] = msa
    return {"id": deal_id, "properties": props,
            "associations": {"companies": {"results": [{"id": company, "type": "deal_to_company"}]}}}


def hs_company(company: str, name: str) -> dict:
    return {"id": company, "properties": {"name": name}}


@asynccontextmanager
async def api_as(factory, user: AuthUser):
    app = FastAPI()
    for router in (hubspot_router, panel_router, workspace_router):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def _db():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t8") as http:
        yield http


async def add_users(factory) -> None:
    async with factory() as s:
        s.add_all([User(id=u.id, email=u.email, name=u.name, groups=list(u.groups))
                   for u in (ADMIN_A, ADMIN_B, LEGAL, SALES)])
        await s.commit()


async def save(factory, user: AuthUser, items: list[tuple[str, str]]) -> None:
    async with factory() as s:
        await save_mapping(s, actor_id=user.id, items=items)
        await s.commit()


async def run_columns(factory) -> list[tuple]:
    async with factory() as s:
        runs = (await s.scalars(select(HubspotSyncRun).order_by(HubspotSyncRun.started_at))).all()
        return [(r.kind, r.status, r.deals_seen, r.deals_written, r.error_count, r.errors, r.fatal_error, r.counts)
                for r in runs]


def outcome_fields(outcome) -> tuple:
    return (outcome.status, outcome.deals_seen, outcome.deals_written, outcome.error_count, outcome.errors,
            outcome.fatal_error, outcome.counts)


async def hubspot_marks(factory) -> list[AgreementMark]:
    async with factory() as s:
        return list((await s.scalars(select(AgreementMark).where(AgreementMark.source == "hubspot")
                                     .order_by(AgreementMark.created_at))).all())


async def applied_summaries(factory) -> list[AuditEvent]:
    async with factory() as s:
        return list((await s.scalars(select(AuditEvent).where(AuditEvent.action == agreement_audit.HUBSPOT_APPLIED)
                                     .order_by(AuditEvent.ts, AuditEvent.id))).all())


async def statuses(factory) -> dict[str, object]:
    async with factory() as s:
        pop = await load_agreement_population(s, SALES)
    return {facts.input.name: facts for facts in pop.clients.values()}


# --- the value is stored and is only ever a hint ---------------------------------------------------------


async def test_the_sync_stores_msa_type_and_the_panel_shows_it_as_a_hint_never_a_state(factory):
    await add_users(factory)
    stub = StubHubSpotClient(
        deals={"d1": hs_deal("d1", company="c1", msa=f"  {SIGNED} "), "d2": hs_deal("d2", company="c2")},
        companies={"c1": hs_company("c1", "Arvella Foods"), "c2": hs_company("c2", "Brintmoor Logistics")})
    assert (await run_deal_sync("nightly", stub, session_factory=factory)).status == "ok"
    async with factory() as s:
        stored = dict((await s.execute(select(Opportunity.hubspot_deal_id, Opportunity.hubspot_msa_type))).all())
        clients = dict((await s.execute(select(Client.name, Client.id))).all())
    assert stored == {"d1": SIGNED, "d2": None}  # the raw value, trimmed
    async with api_as(factory, SALES) as http:
        panel = (await http.get(f"/clients/{clients['Arvella Foods']}/agreements")).json()
        other = (await http.get(f"/clients/{clients['Brintmoor Logistics']}/agreements")).json()
        rows = {r["name"]: r for r in (await http.get("/agreements/workspace")).json()["items"]}
    # The hint sits on the MSA card only; the state is what DealGate holds: nothing, so missing (net new, stage 2).
    assert (panel["msa"]["hubspot_hint"], panel["nda"]["hubspot_hint"], other["msa"]["hubspot_hint"]) == (
        SIGNED, None, None)
    assert (panel["msa"]["state"], panel["needs_attention"]) == ("missing", True)
    assert rows["Arvella Foods"]["msa"]["state"] == "missing" and rows["Arvella Foods"]["needs_attention"] is True
    assert await hubspot_marks(factory) == []  # no mapping saved: nothing is marked


# --- after a saved mapping, the post-sync apply --------------------------------------------------------------

HOLDERS = {  # company id -> (client name, msa_type on its deal)
    "c1": ("Arvella Foods", SIGNED),  # holds nothing: marked
    "c2": ("Brintmoor Logistics", SIGNED),  # MSA client copy: untouched
    "c3": ("Cassowin Health", SIGNED),  # MSA standard copy: untouched
    "c4": ("Dellford Media", SIGNED),  # active DealGate mark: untouched
    "c5": ("Embertine Labs", SIGNED),  # a HubSpot mark Legal removed: never put back
    "c6": ("Fenwick Orchard", "Verbal only"),  # value not mapped to covered: untouched
    "c7": ("Glimmerbay Systems", SIGNED),  # NDA client copy only, nothing for the MSA: marked
}


def holders_stub() -> StubHubSpotClient:
    return StubHubSpotClient(
        deals={f"d-{cid}": hs_deal(f"d-{cid}", company=cid, msa=value) for cid, (_name, value) in HOLDERS.items()},
        companies={cid: hs_company(cid, name) for cid, (name, _value) in HOLDERS.items()})


async def seed_holders(factory) -> dict[str, uuid.UUID]:
    """The same clients and records on any database: what each one holds for the MSA before the sync."""
    await add_users(factory)
    async with factory() as s:
        ids = {}
        for cid, (name, _value) in HOLDERS.items():
            client = Client(id=uuid.uuid4(), name=name, hubspot_company_id=cid)
            s.add(client)
            ids[name] = client.id
        await s.flush()
        standard = StandardAgreement(kind="MSA", version_no=1, file_key="agreements/standard/MSA/t8-std.pdf",
                                     filename="Standard MSA.pdf", file_size=2048, sha256="a" * 64,
                                     uploaded_by=ADMIN_A.id)
        s.add(standard)
        await s.flush()
        s.add_all([
            Agreement(client_id=ids["Brintmoor Logistics"], kind="MSA", file_key="agreements/t8/own-msa.pdf",
                      filename="own-msa.pdf", file_size=100, uploaded_by=LEGAL.id),
            Agreement(client_id=ids["Cassowin Health"], kind="MSA", source="standard",
                      standard_agreement_id=standard.id, file_key=standard.file_key, filename=standard.filename,
                      file_size=standard.file_size, uploaded_by=ADMIN_A.id),
            AgreementMark(client_id=ids["Dellford Media"], kind="MSA", reason="confirmed_with_client",
                          marked_on=datetime(2026, 10, 1).date(), marked_by=LEGAL.id),
            AgreementMark(client_id=ids["Embertine Labs"], kind="MSA", reason="per_hubspot", source="hubspot",
                          hubspot_value=SIGNED, marked_on=datetime(2026, 9, 1).date(), marked_by=ADMIN_A.id,
                          removed_at=datetime(2026, 9, 5, tzinfo=UTC), removed_by=LEGAL.id),
            Agreement(client_id=ids["Glimmerbay Systems"], kind="NDA", file_key="agreements/t8/own-nda.pdf",
                      filename="own-nda.pdf", file_size=100, uploaded_by=LEGAL.id),
        ])
        await s.commit()
    return ids


async def records(factory) -> tuple[list[tuple], list[tuple]]:
    async with factory() as s:
        agreements = sorted((str(a.id), str(a.client_id), a.kind, a.source, a.version_no, a.file_key)
                            for a in (await s.scalars(select(Agreement))).all())
        marks = sorted((str(m.id), str(m.client_id), m.kind, m.source, m.reason, str(m.marked_by),
                        m.removed_at is not None, m.hubspot_value)
                       for m in (await s.scalars(select(AgreementMark))).all())
    return agreements, marks


async def holders_scenario(factory, plain) -> None:
    """``plain``: another database with the same clients and records and no mapping (the baseline run)."""
    await seed_holders(plain)
    plain_outcome = await run_deal_sync("nightly", holders_stub(), session_factory=plain)
    plain_runs = await run_columns(plain)

    ids = await seed_holders(factory)
    await save(factory, ADMIN_A, [(SIGNED, "covered")])
    await save(factory, ADMIN_B, [(SIGNED, "covered"), ("Verbal only", "ignore")])  # the last save
    before_agreements, before_marks = await records(factory)
    outcome = await run_deal_sync("nightly", holders_stub(), session_factory=factory)
    assert outcome.status == "ok"

    marks = await hubspot_marks(factory)
    new = [m for m in marks if m.removed_at is None]
    assert {m.client_id for m in new} == {ids["Arvella Foods"], ids["Glimmerbay Systems"]}
    for mark in new:
        assert (mark.kind, mark.reason, mark.source, mark.hubspot_value, mark.marked_by) == (
            "MSA", "per_hubspot", "hubspot", SIGNED, ADMIN_B.id)  # credits the admin who last saved
    # Every record that existed is untouched; the only change is the two new marks.
    after_agreements, after_marks = await records(factory)
    assert after_agreements == before_agreements
    assert sorted(set(after_marks) - set(before_marks), key=repr) == sorted(
        ((str(m.id), str(m.client_id), "MSA", "hubspot", "per_hubspot", str(ADMIN_B.id), False, SIGNED) for m in new),
        key=repr)
    assert set(before_marks) <= set(after_marks)

    seen = await statuses(factory)
    assert (seen["Arvella Foods"].status.msa, seen["Arvella Foods"].status.msa_label) == ("covered", "Marked by HubSpot")
    assert seen["Brintmoor Logistics"].status.msa == "client"
    assert seen["Cassowin Health"].status.msa == "standard"
    assert (seen["Dellford Media"].status.msa, seen["Dellford Media"].status.msa_label) == ("covered", "Marked covered")
    assert seen["Embertine Labs"].status.msa == "missing"  # Legal's removal stands
    assert seen["Fenwick Orchard"].status.msa == "missing"  # "Verbal only" is not mapped
    assert (seen["Glimmerbay Systems"].status.nda, seen["Glimmerbay Systems"].status.msa) == ("client", "covered")

    [summary] = await applied_summaries(factory)
    assert summary.actor_id is None  # a sync run credits nobody as the presser
    assert (summary.after["trigger"], summary.after["marked"], summary.after["credited_to"]) == ("sync", 2, "Bea Admin")
    async with factory() as s:
        _total, feed = await agreement_audit.activity(s, q=None, page=1, page_size=25)
    applied = [item for item in feed if item["action"] == "hubspot_applied"]
    assert [(item["by"], item["text"]) for item in applied] == [
        ("DealGate", "Applied HubSpot msa_type mapping: marked MSA covered for 2 clients")]
    # The run record and the outcome are exactly those of the same sync without a mapping.
    assert await run_columns(factory) == plain_runs
    assert outcome_fields(outcome) == outcome_fields(plain_outcome)

    # The mapping is emptied: a new client with the same value is not marked, and the marks made stay.
    await save(factory, ADMIN_B, [])
    stub = holders_stub()
    stub.deals["d-c8"] = hs_deal("d-c8", company="c8", msa=SIGNED)
    stub.companies["c8"] = hs_company("c8", "Hollowmere Systems")
    assert (await run_deal_sync("nightly", stub, session_factory=factory)).status == "ok"
    assert {m.client_id for m in await hubspot_marks(factory) if m.removed_at is None} == {
        ids["Arvella Foods"], ids["Glimmerbay Systems"]}
    assert len(await applied_summaries(factory)) == 1  # a sync that marks nobody writes no summary


async def test_after_a_saved_mapping_the_nightly_sync_marks_only_clients_holding_nothing(factory):
    async with fresh_factory() as plain:
        await holders_scenario(factory, plain)


@POSTGRES
async def test_after_a_saved_mapping_the_nightly_sync_marks_only_clients_holding_nothing_on_postgres():
    """The same on Postgres: the chunk's FOR UPDATE locks, the correlated EXISTS re-check and the partial unique
    index on active marks are real there."""
    async with scratch_postgres() as (_engine, factory), scratch_postgres() as (_plain_engine, plain):
        await holders_scenario(factory, plain)


# --- never after a failed or partial sync -----------------------------------------------------------------


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.hubapi.com/x")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(status, request=request))


class Unreadable(StubHubSpotClient):
    async def list_deals_page(self, **_kwargs):
        raise _http_error(401)


class NoPipelines(StubHubSpotClient):
    async def list_pipelines(self):
        raise httpx.ConnectError("down")


async def test_the_apply_never_runs_after_a_failed_or_partial_sync_and_runs_after_the_next_ok_one(factory, monkeypatch):
    await add_users(factory)
    deals = {"d1": hs_deal("d1", company="c1", msa=SIGNED), "d2": hs_deal("d2", company="c2", msa=SIGNED)}
    companies = {"c1": hs_company("c1", "Arvella Foods"), "c2": hs_company("c2", "Brintmoor Logistics")}
    # The values are already stored by an earlier ok sync, before any mapping existed.
    assert (await run_deal_sync("nightly", StubHubSpotClient(deals=dict(deals), companies=companies),
                                session_factory=factory)).status == "ok"
    await save(factory, ADMIN_A, [(SIGNED, "covered")])

    failed = [await run_deal_sync("nightly", Unreadable(deals=dict(deals), companies=companies), session_factory=factory),
              await run_deal_sync("nightly", NoPipelines(deals=dict(deals), companies=companies),
                                  session_factory=factory)]

    async def crash(*_args, **_kwargs):
        raise RuntimeError("unexpected")

    with monkeypatch.context() as patch:
        patch.setattr(hubspot_sync_runs, "run_backfill", crash)
        failed.append(await run_deal_sync("nightly", StubHubSpotClient(deals=dict(deals), companies=companies),
                                          session_factory=factory))
    assert [(o.status, o.fatal_error) for o in failed] == [
        ("failed", "deal scan: HTTP 401"), ("failed", "stage metadata: ConnectError"), ("failed", "sync: RuntimeError")]
    partial = await run_deal_sync("nightly", StubHubSpotClient(
        deals={**deals, "d3": hs_deal("d3", company="c1", stage="no-such-stage")}, companies=companies),
        session_factory=factory)
    assert partial.status == "partial"
    assert await hubspot_marks(factory) == [] and await applied_summaries(factory) == []

    ok = await run_deal_sync("nightly", StubHubSpotClient(deals=dict(deals), companies=companies),
                             session_factory=factory)
    assert ok.status == "ok"
    marked = await hubspot_marks(factory)
    assert len(marked) == 2 and {m.marked_by for m in marked} == {ADMIN_A.id}
    [summary] = await applied_summaries(factory)
    assert summary.after["marked"] == 2


# --- the hint ---------------------------------------------------------------------------------------------


async def test_the_hint_is_the_value_on_the_most_recently_modified_deal_and_a_mark_stays(factory):
    await add_users(factory)
    await save(factory, ADMIN_A, [(SIGNED, "covered")])
    companies = {"c1": hs_company("c1", "Arvella Foods")}
    deals = {
        "d1": hs_deal("d1", company="c1", msa=SIGNED, modified="2026-10-01T12:00:00Z"),
        "d2": hs_deal("d2", company="c1", msa="MSA in progress", modified="2026-10-05T12:00:00Z"),
        "d3": hs_deal("d3", company="c1", modified="2026-10-10T12:00:00Z"),  # newest, but has no value
    }
    assert (await run_deal_sync("nightly", StubHubSpotClient(deals=dict(deals), companies=companies),
                                session_factory=factory)).status == "ok"
    async with factory() as s:
        client_id = await s.scalar(select(Client.id).where(Client.hubspot_company_id == "c1"))

    async def hint_and_values():
        async with api_as(factory, SALES) as http:
            panel = (await http.get(f"/clients/{client_id}/agreements")).json()
            values = (await http.get("/agreements/hubspot-values")).json()
        return panel, {i["value"]: (i["clients"], i["action"]) for i in values["items"]}

    panel, values = await hint_and_values()
    assert panel["msa"]["hubspot_hint"] == "MSA in progress"
    assert values == {"MSA in progress": (1, "ignore"), SIGNED: (0, "covered")}
    assert await hubspot_marks(factory) == []  # the hint is "in progress": the mapped value is not the hint

    # HubSpot edits the older deal: it is now the most recently modified one with a value.
    deals["d1"] = hs_deal("d1", company="c1", msa=SIGNED, modified="2026-10-12T12:00:00Z")
    assert (await run_deal_sync("nightly", StubHubSpotClient(deals=dict(deals), companies=companies),
                                session_factory=factory)).status == "ok"
    panel, values = await hint_and_values()
    assert panel["msa"]["hubspot_hint"] == SIGNED and values[SIGNED] == (1, "covered")
    [mark] = await hubspot_marks(factory)
    assert (mark.client_id, mark.hubspot_value, mark.marked_by) == (client_id, SIGNED, ADMIN_A.id)
    assert (panel["msa"]["state"], panel["msa"]["mark"]["source"]) == ("covered", "hubspot")

    # HubSpot clears the value: the hint goes back to the other deal, and the mark DealGate made stays.
    deals["d1"] = hs_deal("d1", company="c1", msa="", modified="2026-10-14T12:00:00Z")
    assert (await run_deal_sync("nightly", StubHubSpotClient(deals=dict(deals), companies=companies),
                                session_factory=factory)).status == "ok"
    panel, _values = await hint_and_values()
    assert panel["msa"]["hubspot_hint"] == "MSA in progress"
    assert panel["msa"]["state"] == "covered" and [m.id for m in await hubspot_marks(factory)] == [mark.id]


# --- stored=false before any value ----------------------------------------------------------------------------


async def test_hubspot_values_says_not_stored_before_any_value_even_with_a_saved_mapping(factory):
    await add_users(factory)
    async with api_as(factory, SALES) as http:
        first = await http.get("/agreements/hubspot-values")
    assert first.status_code == 200
    assert (first.json()["stored"], first.json()["items"]) == (False, [])
    async with api_as(factory, ADMIN_A) as http:
        put = await http.put("/agreements/hubspot-mapping", json={"items": [{"value": SIGNED, "action": "covered"}]})
        after_save = (await http.get("/agreements/hubspot-values")).json()
    assert put.status_code == 200, put.text
    assert (after_save["stored"], after_save["items"], after_save["saved_by"]) == (False, [], "Ada Admin")

    stub = StubHubSpotClient(deals={"d1": hs_deal("d1", company="c1", msa=SIGNED)},
                             companies={"c1": hs_company("c1", "Arvella Foods")})
    assert (await run_deal_sync("nightly", stub, session_factory=factory)).status == "ok"
    async with api_as(factory, SALES) as http:
        stored = (await http.get("/agreements/hubspot-values")).json()
    assert stored["stored"] is True
    assert [(i["value"], i["clients"], i["action"]) for i in stored["items"]] == [(SIGNED, 1, "covered")]


# --- a stopped post-sync apply (bug #97) -----------------------------------------------------------------------


async def test_a_stopped_post_sync_apply_keeps_its_chunks_and_the_next_sync_finishes(factory, monkeypatch):
    names = {f"c{i}": f"Lunavale Client {i}" for i in range(1, 6)}

    def stub() -> StubHubSpotClient:
        return StubHubSpotClient(
            deals={f"d{i}": hs_deal(f"d{i}", company=f"c{i}", msa=SIGNED) for i in range(1, 6)},
            companies={cid: hs_company(cid, name) for cid, name in names.items()})

    async with fresh_factory() as plain:
        await add_users(plain)
        plain_outcome = await run_deal_sync("nightly", stub(), session_factory=plain)
        plain_runs = await run_columns(plain)

    await add_users(factory)
    await save(factory, ADMIN_A, [(SIGNED, "covered")])
    monkeypatch.setattr(agreement_hubspot, "APPLY_CHUNK", 2)
    real_record, seen = agreement_audit.record, 0

    async def failing_record(session_, **kwargs):
        nonlocal seen
        if kwargs["action"] == agreement_audit.HUBSPOT_MARKED:
            seen += 1
            if seen == 3:  # the first client of the second chunk
                raise RuntimeError("database went away")
        return await real_record(session_, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(agreement_audit, "record", failing_record)
        outcome = await run_deal_sync("nightly", stub(), session_factory=factory)
    # The sync is not failed by its post step, and its record is exactly the plain run's.
    assert outcome.status == "ok"
    assert await run_columns(factory) == plain_runs
    assert outcome_fields(outcome) == outcome_fields(plain_outcome)
    assert len(await hubspot_marks(factory)) == 2  # the first chunk stays committed
    [stopped] = await applied_summaries(factory)
    assert (stopped.after["trigger"], stopped.after["marked"], stopped.after["would_mark"], stopped.after["stopped"]) == (
        "sync", 2, 5, True)
    async with factory() as s:
        _total, items = await agreement_audit.activity(s, q=None, page=1, page_size=25)
    assert any(i["action"] == "hubspot_applied"
               and i["text"] == "HubSpot msa_type mapping stopped after marking MSA covered for 2 clients" for i in items)

    # The next nightly sync finishes the rest: one mark per client, no duplicates.
    assert (await run_deal_sync("nightly", stub(), session_factory=factory)).status == "ok"
    marks = await hubspot_marks(factory)
    assert len(marks) == 5 and len({m.client_id for m in marks}) == 5
    finished = (await applied_summaries(factory))[-1]
    assert (finished.after["marked"], finished.after.get("stopped")) == (3, None)
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(AgreementMark)) == 5
