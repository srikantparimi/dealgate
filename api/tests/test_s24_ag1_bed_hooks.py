"""S24-AG1 lane BE-D — B8 the client-creation hook, F11's additive response fields.

The hook (app.services.agreement_hooks) stamps nothing before the cutover; after
it a client created by hand, from a SOW, by an import, as a fixture or as the
"Unknown company" placeholder starts net new at once; a client from a HubSpot
company waits for the end-of-sync settle, which applies the same rule
(agreement_status.relationship_of) once every deal has been read. A stamp never
moves an existing relationship and always writes one audit row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session
from app.integrations.hubspot import StubHubSpotClient
from app.main import app as main_app
from app.models.agreements import AgreementsSettings
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import agreement_audit, bulk_import, legacy_import
from app.services.agreement_hooks import load_cutover, settle_pending_relationships, stamp_new_client
from app.services.clients import upsert_client_from_hubspot, upsert_unknown_client_for_deal
from app.services.hubspot_sync_runs import run_deal_sync
from app.services.test_fixtures import create_fixture

CUTOVER = date(2026, 10, 1)


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("SALES_LEADER_EMAIL", raising=False)


async def _set_cutover(session: AsyncSession, *, set_at: datetime | None = None) -> datetime:
    at = set_at or (datetime.now(UTC) - timedelta(hours=1))
    session.add(AgreementsSettings(id=1, cutover_date=CUTOVER, set_at=at))
    await session.commit()
    return at


async def _stamps(session: AsyncSession, client_id: uuid.UUID) -> list[AuditEvent]:
    return list((await session.scalars(select(AuditEvent).where(
        AuditEvent.action == agreement_audit.RELATIONSHIP_STAMPED, AuditEvent.entity == "client",
        AuditEvent.entity_id == str(client_id)))).all())


@pytest_asyncio.fixture
async def api(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


def _http(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# --- the hook itself ---------------------------------------------------------------------------


async def test_load_cutover_without_a_settings_row(session):
    assert await load_cutover(session) == (None, None)


async def test_before_the_cutover_nothing_is_stamped(session):
    client = Client(id=uuid.uuid4(), name="Early Co")
    session.add(client)
    await session.flush()
    assert await stamp_new_client(session, client, actor_id=None, origin="manual") is None
    assert client.relationship is None and client.relationship_basis is None
    assert await _stamps(session, client.id) == []


async def test_after_the_cutover_a_client_with_no_hubspot_company_starts_net_new(session):
    await _set_cutover(session)
    actor = User(email="legal@example.test", name="Lee Legal", groups=["Legal"])
    session.add(actor)
    client = Client(id=uuid.uuid4(), name="Fresh Co")
    session.add(client)
    await session.flush()
    assert await stamp_new_client(session, client, actor_id=actor.id, origin="manual") == "net_new"
    assert (client.relationship, client.relationship_basis, client.relationship_set_by) == (
        "net_new", "none", actor.id)
    assert client.relationship_set_at is not None
    [row] = await _stamps(session, client.id)
    assert row.actor_id == actor.id
    assert row.after == {"client_id": str(client.id), "client_name": "Fresh Co", "relationship": "net_new",
                         "basis": "none", "origin": "manual", "cutover": "2026-10-01"}


async def test_a_stamp_never_moves_an_existing_relationship(session):
    await _set_cutover(session)
    client = Client(id=uuid.uuid4(), name="Corrected Co", relationship="existing", relationship_basis="manual")
    session.add(client)
    await session.flush()
    assert await stamp_new_client(session, client, actor_id=None, origin="manual") == "existing"
    assert (client.relationship, client.relationship_basis) == ("existing", "manual")
    assert await _stamps(session, client.id) == []


async def test_hubspot_company_client_waits_and_the_placeholder_is_net_new(session):
    await _set_cutover(session)
    company = await upsert_client_from_hubspot(
        session, company_payload={"id": "co-1", "properties": {"name": "Acme Corp"}}, correlation_id="c1")
    placeholder = await upsert_unknown_client_for_deal(session, deal_id="d-77", correlation_id="c1")
    await session.commit()
    # A HubSpot company's deals link after its row exists: judged by the settle, not at creation.
    assert company.relationship is None and await _stamps(session, company.id) == []
    assert (placeholder.relationship, placeholder.relationship_basis) == ("net_new", "none")
    assert placeholder.relationship_set_by is None  # HubSpot paths credit nobody (no system user)
    [row] = await _stamps(session, placeholder.id)
    assert row.actor_id is None and row.after["origin"] == "hubspot_placeholder"
    assert row.correlation_id == "c1"


# --- the settle -------------------------------------------------------------------------------


async def _hubspot_client(session, name: str, *, company: str) -> Client:
    client = Client(id=uuid.uuid4(), name=name, hubspot_company_id=company)
    session.add(client)
    await session.flush()
    return client


def _opp(client: Client, *, won: bool = False, close: date | None = None, archived: bool = False,
         source: str = "hubspot") -> Opportunity:
    return Opportunity(
        id=uuid.uuid4(), client_id=client.id, source=source, governance_status="Intake",
        hubspot_deal_id=f"d-{uuid.uuid4().hex[:8]}" if source == "hubspot" else None,
        is_closed_won=won, close_date=close,
        archived_at=datetime.now(UTC) if archived else None,
    )


async def test_settle_applies_the_creation_rule_once_every_deal_is_read(session):
    set_at = await _set_cutover(session)
    won_before = await _hubspot_client(session, "Won Before", company="c-a")
    won_after = await _hubspot_client(session, "Won After", company="c-b")
    undated = await _hubspot_client(session, "Undated Win", company="c-c")
    open_only = await _hubspot_client(session, "Open Only", company="c-d")
    archived_win = await _hubspot_client(session, "Archived Win", company="c-e")
    manual = await _hubspot_client(session, "Manual", company="c-f")
    manual.relationship, manual.relationship_basis = "existing", "manual"
    session.add_all([
        _opp(won_before, won=True, close=date(2026, 9, 15)),
        _opp(won_after, won=True, close=date(2026, 10, 10)),
        _opp(undated, won=True, close=None),
        _opp(open_only),
        _opp(archived_win, won=True, close=date(2026, 9, 1), archived=True),
        _opp(manual),
    ])
    await session.commit()
    # A client created before the cutover was set belongs to the batch that set it, not to the settle.
    older = Client(id=uuid.uuid4(), name="Pre-cutover", hubspot_company_id="c-g",
                   created_at=set_at - timedelta(days=3))
    session.add(older)
    await session.commit()

    assert await settle_pending_relationships(session, correlation_id="sync-1") == 5

    async def rel(client):
        row = await session.get(Client, client.id, populate_existing=True)
        return row.relationship, row.relationship_basis

    assert await rel(won_before) == ("existing", "closed_won")
    assert await rel(won_after) == ("net_new", "none")  # a win after the cutover never makes it existing
    assert await rel(undated) == ("existing", "closed_won")  # bugs #5: an undated win counts as before
    assert await rel(open_only) == ("net_new", "none")
    assert await rel(archived_win) == ("net_new", "none")  # an archived deal is not evidence
    assert await rel(manual) == ("existing", "manual")  # a writer's change always wins
    assert await rel(older) == (None, None)
    [row] = await _stamps(session, won_before.id)
    assert (row.actor_id, row.after["origin"], row.correlation_id) == (None, "hubspot_sync", "sync-1")
    # Idempotent: nothing left to stamp.
    assert await settle_pending_relationships(session) == 0


async def test_settle_does_nothing_before_the_cutover(session):
    client = await _hubspot_client(session, "Waiting", company="c-z")
    await session.commit()
    assert await settle_pending_relationships(session) == 0
    assert (await session.get(Client, client.id)).relationship is None


# --- every creation path calls the hook ---------------------------------------------------------


async def test_post_clients_returns_created_and_stamps_after_the_cutover(api, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _http(api) as http:
        first = await http.post("/clients", json={"name": "Before Cutover Co"},
                                headers={"X-Test-User": "rep@example.test"})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["created"] is True and body["source"] == "manual"
    assert (await session.get(Client, uuid.UUID(body["id"]))).relationship is None

    await _set_cutover(session)
    async with _http(api) as http:
        again = await http.post("/clients", json={"name": "before cutover co"},
                                headers={"X-Test-User": "rep@example.test"})
        fresh = await http.post("/clients", json={"name": "After Cutover Co"},
                                headers={"X-Test-User": "rep@example.test"})
    assert again.status_code == 201 and again.json()["created"] is False and again.json()["id"] == body["id"]
    # A matched client is never stamped by the hook.
    assert (await session.get(Client, uuid.UUID(body["id"]), populate_existing=True)).relationship is None
    created = fresh.json()
    assert created["created"] is True
    row = await session.get(Client, uuid.UUID(created["id"]), populate_existing=True)
    assert (row.relationship, row.relationship_basis, row.relationship_set_by) == (
        "net_new", "none", _uid("rep@example.test"))
    [stamp] = await _stamps(session, row.id)
    assert stamp.after["origin"] == "manual"


async def test_bulk_import_writes_client_created_and_stamps(session, monkeypatch):
    await _set_cutover(session)
    actor = User(email="finance@example.test", name="Fin", groups=["Finance"])
    session.add(actor)
    await session.flush()

    async def fake_pipeline(*_args, **_kwargs):
        return "retried"

    monkeypatch.setattr(bulk_import, "apply_pipeline", fake_pipeline)
    result = await bulk_import._auto_create_and_retry(
        session, payload=b"%PDF-", actor_id=actor.id,
        previous=SimpleNamespace(create_new={"legal_name": "Bulk Imported Co"}), bedrock=None)
    assert result == "retried"
    client = (await session.scalars(select(Client).where(Client.name == "Bulk Imported Co"))).one()
    created = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == "client.created", AuditEvent.entity_id == str(client.id)))).one()
    assert created.actor_id == actor.id and created.after == {"name": "Bulk Imported Co", "source": "bulk_import"}
    assert (client.relationship, client.relationship_set_by) == ("net_new", actor.id)
    [stamp] = await _stamps(session, client.id)
    assert stamp.after["origin"] == "bulk_import"


async def test_legacy_import_writes_client_created_and_stamps(session):
    await _set_cutover(session)
    actor = User(email="ceo@example.test", name="Cee", groups=["CEO"])
    session.add(actor)
    await session.flush()
    client_id = await legacy_import._find_or_create_client(session, "  Legacy Co  ", actor_id=actor.id)
    client = await session.get(Client, client_id)
    created = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == "client.created", AuditEvent.entity_id == str(client_id)))).one()
    assert created.after == {"name": "Legacy Co", "source": "legacy_import"} and created.actor_id == actor.id
    assert client.relationship == "net_new"
    # Found again by name: no second client, no second stamp.
    assert await legacy_import._find_or_create_client(session, "Legacy Co", actor_id=actor.id) == client_id
    assert len(await _stamps(session, client_id)) == 1


async def test_a_fixture_client_is_stamped_like_any_other(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "ag1-hooks")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    await _set_cutover(session)
    bot = User(email="bot@example.test", name="E2E bot", groups=["officeapp-e2e", "SystemAdmin"])
    session.add(bot)
    await session.flush()
    result = await create_fixture(session, actor_id=bot.id, label="Agreements", reviewer_ids=[])
    client = await session.get(Client, result["client_id"])
    assert (client.relationship, client.relationship_set_by) == ("net_new", bot.id)
    [stamp] = await _stamps(session, client.id)
    assert stamp.after["origin"] == "test_fixture" and stamp.correlation_id == str(result["run_id"])


# --- the sync settles new HubSpot clients (only after an ok run) ------------------------------


def _deal(deal_id: str, stage: str, *, company: str, close: str, msa: str | None = None) -> dict:
    props = {"dealname": f"Deal {deal_id}", "dealstage": stage, "pipeline": "default", "amount": "1000",
             "deal_currency_code": "USD", "closedate": close, "hs_lastmodifieddate": "2026-10-13T12:00:00Z"}
    if msa is not None:
        props["msa_type"] = msa
    return {"id": deal_id, "properties": props,
            "associations": {"companies": {"results": [{"id": company, "type": "deal_to_company"}]}}}


@pytest_asyncio.fixture
async def factory(savepoint_engine):
    return async_sessionmaker(savepoint_engine, expire_on_commit=False, class_=AsyncSession)


async def test_an_ok_sync_settles_new_companies_and_a_partial_one_does_not(factory):
    async with factory() as s:
        await _set_cutover(s)
    stub = StubHubSpotClient(
        deals={"d1": _deal("d1", "closedwon", company="c1", close="2026-09-20"),
               "d2": _deal("d2", "closedwon", company="c2", close="2026-10-12"),
               "d3": _deal("d3", "qualifiedtobuy", company="c3", close="2026-12-31")},
        companies={"c1": {"id": "c1", "properties": {"name": "Old Friend"}},
                   "c2": {"id": "c2", "properties": {"name": "First Win"}},
                   "c3": {"id": "c3", "properties": {"name": "Prospect"}}})
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)
    assert outcome.status == "ok"
    async with factory() as s:
        rels = {c.name: (c.relationship, c.relationship_basis, c.relationship_set_by)
                for c in (await s.scalars(select(Client))).all()}
    assert rels == {"Old Friend": ("existing", "closed_won", None),
                    "First Win": ("net_new", "none", None),
                    "Prospect": ("net_new", "none", None)}

    # A partial run leaves a new company pending (its deciding deal may be the one refused).
    stub.deals["d4"] = _deal("d4", "qualifiedtobuy", company="c4", close="2026-12-31")
    stub.deals["d5"] = _deal("d5", "no-such-stage", company="c4", close="2026-09-01")
    stub.companies["c4"] = {"id": "c4", "properties": {"name": "Half Read"}}
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)
    assert outcome.status == "partial"
    async with factory() as s:
        half = (await s.scalars(select(Client).where(Client.name == "Half Read"))).one()
    assert half.relationship is None


async def test_a_failing_settle_never_fails_the_sync(factory, monkeypatch):
    from app.services import agreement_hooks

    async def boom(*_args, **_kwargs):
        raise RuntimeError("settle exploded")

    monkeypatch.setattr(agreement_hooks, "settle_pending_relationships", boom)
    stub = StubHubSpotClient(deals={"d1": _deal("d1", "qualifiedtobuy", company="c1", close="2026-12-31")},
                             companies={"c1": {"id": "c1", "properties": {"name": "Acme"}}})
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)
    assert outcome.status == "ok" and outcome.error_count == 0


# --- F11: the SOW studio pick names the client it created ---------------------------------------


async def test_sow_pick_create_new_returns_the_client_and_stamps_it(session, monkeypatch):
    from app.integrations.bedrock_sow_extract import get_bedrock_sow
    from app.integrations.s3_sow import StubS3, get_sow_s3
    from tests.test_sow_upload_router import _load_pdf, _override_bedrock

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    await _set_cutover(session)
    stub_s3 = StubS3()

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    main_app.dependency_overrides[get_sow_s3] = lambda: stub_s3
    try:
        _override_bedrock("Picked New Client Inc")
        owner = {"X-Test-User": "sow-owner@example.test"}
        async with _http(main_app) as http:
            upload = await http.post("/sows/upload", headers=owner,
                                     files={"file": ("sow.pdf", _load_pdf("05_tm_capped.pdf"), "application/pdf")})
            assert upload.status_code == 200, upload.text
            job_id = upload.json()["job_id"]
            poll = await http.get(f"/sows/jobs/{job_id}", headers=owner)
            pick = await http.post(f"/sows/jobs/{job_id}/pick", headers=owner,
                                   json={"create_new": {"legal_name": "Picked New Client Inc"}})
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_sow_s3, None)
        main_app.dependency_overrides.pop(get_bedrock_sow, None)
    assert poll.json()["client_id"] is None and poll.json()["created"] is None  # status poll: not named
    assert pick.status_code == 200, pick.text
    body = pick.json()
    assert body["resolution"] == "created" and body["created"] is True
    assert body["client_name"] == "Picked New Client Inc"
    client = await session.get(Client, uuid.UUID(body["client_id"]))
    assert client.name == "Picked New Client Inc"
    assert (client.relationship, client.relationship_set_by) == ("net_new", _uid("sow-owner@example.test"))
    [stamp] = await _stamps(session, client.id)
    assert stamp.after["origin"] == "sow_upload"
