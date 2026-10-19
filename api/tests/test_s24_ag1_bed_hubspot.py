"""S24-AG1 lane BE-D — B9 HubSpot ``msa_type`` (T8 shape, fixtures only, no real token).

The value is stored raw on the deal inside the existing opportunity audit row;
GET /agreements/hubspot-values lists each value with its client count for every
role; SystemAdmin alone saves the mapping and applies it (403 for everyone else,
and for a test identity outside local/test). Apply fills only clients that hold
nothing for the MSA, never overwrites or re-adds a record, credits the admin who
last saved the mapping, runs after an ok sync and leaves the sync-run record
exactly as it was.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.hubspot import HubSpotClient, StubHubSpotClient
from app.main import app as main_app
from app.models.agreements import AgreementHubspotMap, AgreementMark
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.hubspot_sync_run import HubspotSyncRun
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import agreement_audit, agreement_hubspot
from app.services.agreement_hubspot import apply_mapping, hubspot_values, save_mapping
from app.services.hubspot_intake import _parse_msa_type
from app.services.hubspot_sync_runs import run_deal_sync

ROLES = ("Marketing", "Sales", "SalesLeader", "Presales", "Delivery", "HR", "Finance", "Legal", "CEO",
         "SystemAdmin")


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("SALES_LEADER_EMAIL", raising=False)


def _deal(deal_id: str, *, company: str, msa: str | None = None, stage: str = "qualifiedtobuy",
          modified: str = "2026-10-13T12:00:00Z") -> dict:
    props = {"dealname": f"Deal {deal_id}", "dealstage": stage, "pipeline": "default", "amount": "1000",
             "deal_currency_code": "USD", "closedate": "2026-12-31", "hs_lastmodifieddate": modified}
    if msa is not None:
        props["msa_type"] = msa
    return {"id": deal_id, "properties": props,
            "associations": {"companies": {"results": [{"id": company, "type": "deal_to_company"}]}}}


@pytest_asyncio.fixture
async def factory(savepoint_engine):
    return async_sessionmaker(savepoint_engine, expire_on_commit=False, class_=AsyncSession)


# --- the property is requested and stored ------------------------------------------------------


def test_msa_type_is_requested_with_every_deal_read():
    assert "msa_type" in HubSpotClient._DEAL_PROPERTIES.split(",")


def test_parse_msa_type_trims_blanks_and_caps_at_200():
    assert _parse_msa_type(None) is None
    assert _parse_msa_type("   ") is None
    assert _parse_msa_type("  Signed MSA ") == "Signed MSA"
    assert _parse_msa_type("x" * 250) == "x" * 200


async def _opps(factory) -> dict[str, Opportunity]:
    async with factory() as s:
        return {o.hubspot_deal_id: o for o in (await s.scalars(select(Opportunity))).all()}


async def _opportunity_audits(factory, opp_id) -> list[AuditEvent]:
    async with factory() as s:
        return list((await s.scalars(select(AuditEvent).where(
            AuditEvent.entity == "opportunity", AuditEvent.entity_id == str(opp_id)
        ).order_by(AuditEvent.ts, AuditEvent.id))).all())


async def test_the_sync_stores_the_raw_value_inside_the_existing_audit_row(factory):
    stub = StubHubSpotClient(
        deals={"d1": _deal("d1", company="c1", msa=" Signed MSA "), "d2": _deal("d2", company="c2")},
        companies={"c1": {"id": "c1", "properties": {"name": "Acme"}},
                   "c2": {"id": "c2", "properties": {"name": "Beta"}}})
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)
    assert outcome.status == "ok"
    opps = await _opps(factory)
    assert opps["d1"].hubspot_msa_type == "Signed MSA" and opps["d2"].hubspot_msa_type is None
    [created] = await _opportunity_audits(factory, opps["d1"].id)
    assert created.action == "opportunity.created" and created.after["hubspot_msa_type"] == "Signed MSA"

    # HubSpot changes the value: stored and recorded in the ONE opportunity.updated row for the deal (a
    # second opportunity row in the run would make the backfill's per-deal update check raise).
    stub.deals["d1"] = _deal("d1", company="c1", msa="MSA in progress", modified="2026-10-14T12:00:00Z")
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)
    assert outcome.status == "ok" and outcome.error_count == 0
    assert (await _opps(factory))["d1"].hubspot_msa_type == "MSA in progress"
    rows = await _opportunity_audits(factory, opps["d1"].id)
    assert [r.action for r in rows] == ["opportunity.created", "opportunity.updated"]
    assert (rows[1].before["hubspot_msa_type"], rows[1].after["hubspot_msa_type"]) == (
        "Signed MSA", "MSA in progress")

    # Cleared in HubSpot: cleared here. Not requested (absent): left alone.
    stub.deals["d1"] = _deal("d1", company="c1", msa="", modified="2026-10-15T12:00:00Z")
    await run_deal_sync("nightly", stub, session_factory=factory)
    assert (await _opps(factory))["d1"].hubspot_msa_type is None


# --- the values, the mapping and the apply (service) -------------------------------------------


async def _client(session, name: str, *, company: str | None = None) -> Client:
    client = Client(id=uuid.uuid4(), name=name, hubspot_company_id=company or f"co-{uuid.uuid4().hex[:6]}")
    session.add(client)
    await session.flush()
    return client


def _hint(client: Client, value: str | None, *, modified: datetime, archived: bool = False,
          source: str = "hubspot") -> Opportunity:
    return Opportunity(id=uuid.uuid4(), client_id=client.id, source=source, governance_status="Intake",
                       hubspot_deal_id=f"d-{uuid.uuid4().hex[:8]}", hubspot_msa_type=value,
                       hubspot_last_modified_at=modified,
                       archived_at=datetime.now(UTC) if archived else None)


async def _user(session, email: str, name: str, groups=("SystemAdmin",)) -> User:
    user = User(id=_uid(email), email=email, name=name, groups=list(groups))
    session.add(user)
    await session.flush()
    return user


T1 = datetime(2026, 10, 1, tzinfo=UTC)
T2 = datetime(2026, 10, 5, tzinfo=UTC)


async def _seed(session):
    """Clients and their hints (the value on the most recently modified live deal that has one)."""
    signed = [await _client(session, f"Signed {i}") for i in range(3)]
    for c in signed:
        session.add(_hint(c, "Signed MSA", modified=T1))
    moved = await _client(session, "Moved On")  # older deal says signed, newer says in progress
    session.add_all([_hint(moved, "Signed MSA", modified=T1), _hint(moved, "MSA in progress", modified=T2)])
    held = await _client(session, "Holds A File")
    session.add(_hint(held, "Signed MSA", modified=T1))
    marked = await _client(session, "Marked By Hand")
    session.add(_hint(marked, "Signed MSA", modified=T1))
    removed = await _client(session, "Mark Removed")
    session.add(_hint(removed, "Signed MSA", modified=T1))
    archived_deal = await _client(session, "Archived Deal")
    session.add(_hint(archived_deal, "Signed MSA", modified=T2, archived=True))
    gone = await _client(session, "Archived Client")
    gone.archived_at = datetime.now(UTC)
    session.add(_hint(gone, "Signed MSA", modified=T1))
    legal = await _user(session, "legal@example.test", "Lee Legal", ("Legal",))
    session.add(Agreement(id=uuid.uuid4(), client_id=held.id, kind="MSA", file_key="k", filename="msa.pdf",
                          file_size=10, uploaded_by=legal.id))
    session.add(AgreementMark(id=uuid.uuid4(), client_id=marked.id, kind="MSA", reason="confirmed_with_client",
                              marked_on=date(2026, 10, 2), marked_by=legal.id))
    session.add(AgreementMark(id=uuid.uuid4(), client_id=removed.id, kind="MSA", reason="other",
                              marked_on=date(2026, 10, 2), marked_by=legal.id,
                              removed_at=datetime.now(UTC), removed_by=legal.id))
    await session.commit()
    return {"signed": signed, "moved": moved, "held": held, "marked": marked, "removed": removed}


async def test_values_before_the_sync_stores_anything(session):
    assert await hubspot_values(session) == {"stored": False, "items": [], "saved_by": None, "saved_at": None,
                                             "can_edit": False}


async def test_values_count_clients_by_their_hint(session):
    await _seed(session)
    values = await hubspot_values(session)
    assert values["stored"] is True
    by_value = {item["value"]: item for item in values["items"]}
    # 3 signed + held + marked + removed (the archived deal and the archived client do not count).
    assert by_value["Signed MSA"] == {"value": "Signed MSA", "clients": 6, "action": "ignore", "would_mark": 3}
    assert by_value["MSA in progress"] == {"value": "MSA in progress", "clients": 1, "action": "ignore",
                                           "would_mark": 1}
    assert [item["value"] for item in values["items"]] == ["Signed MSA", "MSA in progress"]


async def test_apply_fills_only_clients_holding_nothing_and_credits_the_last_saver(session):
    seeded = await _seed(session)
    saver = await _user(session, "admin-one@example.test", "Ada Admin")
    other_admin = await _user(session, "admin-two@example.test", "Otto Admin")
    await session.commit()
    await save_mapping(session, actor_id=saver.id, items=[("Signed MSA", "covered"), ("MSA in progress", "ignore")])
    await session.commit()

    dry = await apply_mapping(session, dry_run=True, trigger="dialog", actor_id=None)
    assert dry.as_dict() == {"dry_run": True, "would_mark": 3, "marked": 0}
    assert (await session.scalar(select(func.count()).select_from(AgreementMark))) == 2  # nothing written

    result = await apply_mapping(session, dry_run=False, trigger="dialog", actor_id=other_admin.id,
                                 now=datetime(2026, 10, 16, 3, 0, tzinfo=UTC))
    assert result.as_dict() == {"dry_run": False, "would_mark": 3, "marked": 3}
    marks = (await session.scalars(select(AgreementMark).where(AgreementMark.source == "hubspot"))).all()
    assert {m.client_id for m in marks} == {c.id for c in seeded["signed"]}
    for mark in marks:
        assert (mark.kind, mark.reason, mark.hubspot_value, mark.marked_by) == (
            "MSA", "per_hubspot", "Signed MSA", saver.id)  # the last saver, not whoever pressed Apply
        assert mark.note == "msa_type “Signed MSA”"
        assert mark.marked_on == date(2026, 10, 15)  # the Los Angeles calendar date
        assert mark.removed_at is None
    # The client with a file, the hand mark and the removed mark are untouched; "in progress" is not mapped.
    for key in ("held", "marked", "removed", "moved"):
        held = (await session.scalars(select(AgreementMark).where(
            AgreementMark.client_id == seeded[key].id, AgreementMark.source == "hubspot"))).all()
        assert held == []
    marked_rows = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == agreement_audit.HUBSPOT_MARKED))).all()
    assert len(marked_rows) == 3 and all(r.actor_id == other_admin.id for r in marked_rows)
    assert {r.after["client_name"] for r in marked_rows} == {"Signed 0", "Signed 1", "Signed 2"}
    [summary] = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == agreement_audit.HUBSPOT_APPLIED))).all()
    assert summary.entity == "agreement_hubspot_map" and summary.actor_id == other_admin.id
    assert (summary.after["marked"], summary.after["credited_to"], summary.after["values"]) == (
        3, "Ada Admin", ["Signed MSA"])
    # The Activity feed shows the summary sentence.
    total, items = await agreement_audit.activity(session, q=None, page=1, page_size=25)
    assert any(i["action"] == "hubspot_applied"
               and i["text"] == "Applied HubSpot msa_type mapping: marked MSA covered for 3 clients" for i in items)

    # Idempotent: a second apply finds nobody (DealGate's record now exists).
    again = await apply_mapping(session, dry_run=False, trigger="sync", actor_id=None)
    assert again.as_dict() == {"dry_run": False, "would_mark": 0, "marked": 0}
    assert len((await session.scalars(select(AuditEvent).where(
        AuditEvent.action == agreement_audit.HUBSPOT_APPLIED))).all()) == 1  # no nightly zero rows


async def test_apply_commits_in_chunks(session, monkeypatch):
    monkeypatch.setattr(agreement_hubspot, "APPLY_CHUNK", 2)
    for i in range(5):
        c = await _client(session, f"Chunked {i}")
        session.add(_hint(c, "Yes", modified=T1))
    saver = await _user(session, "admin@example.test", "Ada Admin")
    await session.commit()
    await save_mapping(session, actor_id=saver.id, items=[("Yes", "covered")])
    await session.commit()
    commits = 0
    real_commit = session.commit

    async def counting_commit():
        nonlocal commits
        commits += 1
        await real_commit()

    monkeypatch.setattr(session, "commit", counting_commit)
    result = await apply_mapping(session, dry_run=False, trigger="dialog", actor_id=saver.id)
    assert result.marked == 5
    assert commits == 1 + 3 + 1  # end of the read, three chunks of at most 2, the summary


async def test_a_stopped_apply_keeps_its_committed_chunks_and_says_how_far_it_got(session, monkeypatch):
    monkeypatch.setattr(agreement_hubspot, "APPLY_CHUNK", 2)
    for i in range(5):
        c = await _client(session, f"Stopped {i}")
        session.add(_hint(c, "Yes", modified=T1))
    saver = await _user(session, "admin@example.test", "Ada Admin")
    await session.commit()
    await save_mapping(session, actor_id=saver.id, items=[("Yes", "covered")])
    await session.commit()
    real_record, seen = agreement_audit.record, 0

    async def failing_record(session_, **kwargs):
        nonlocal seen
        if kwargs["action"] == agreement_audit.HUBSPOT_MARKED:
            seen += 1
            if seen == 3:  # the first client of the second chunk
                raise RuntimeError("database went away")
        return await real_record(session_, **kwargs)

    monkeypatch.setattr(agreement_audit, "record", failing_record)
    with pytest.raises(RuntimeError, match="database went away"):
        await apply_mapping(session, dry_run=False, trigger="dialog", actor_id=saver.id)
    # The first chunk stays committed; the failed chunk rolled back.
    assert (await session.scalar(select(func.count()).select_from(AgreementMark).where(
        AgreementMark.source == "hubspot"))) == 2
    [summary] = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == agreement_audit.HUBSPOT_APPLIED))).all()
    assert (summary.after["marked"], summary.after["would_mark"], summary.after["stopped"]) == (2, 5, True)
    assert summary.after["exception"] == "RuntimeError"
    total, items = await agreement_audit.activity(session, q=None, page=1, page_size=25)
    assert any(i["action"] == "hubspot_applied"
               and i["text"] == "HubSpot msa_type mapping stopped after marking MSA covered for 2 clients"
               for i in items)


async def test_save_mapping_replaces_everything_and_is_audited(session):
    first = await _user(session, "a1@example.test", "First Admin")
    second = await _user(session, "a2@example.test", "Second Admin")
    await session.commit()
    await save_mapping(session, actor_id=first.id, items=[("A", "covered"), ("B", "ignore")])
    await session.commit()
    await save_mapping(session, actor_id=second.id, items=[("B", "covered")])
    await session.commit()
    rows = (await session.execute(select(AgreementHubspotMap.value, AgreementHubspotMap.action,
                                         AgreementHubspotMap.updated_by))).all()
    assert [tuple(r) for r in rows] == [("B", "covered", second.id)]
    saved = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == agreement_audit.HUBSPOT_MAPPING_SAVED).order_by(AuditEvent.ts, AuditEvent.id))).all()
    assert len(saved) == 2
    assert saved[1].before == {"items": [{"value": "A", "action": "covered"}, {"value": "B", "action": "ignore"}]}
    assert saved[1].after == {"items": [{"value": "B", "action": "covered"}], "covered": ["B"]}
    values = await hubspot_values(session)
    assert values["saved_by"] == "Second Admin" and values["saved_at"].endswith("Z")


# --- the routes and their roles -----------------------------------------------------------------


@pytest_asyncio.fixture
async def api(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(current_user, None)


def _http(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_every_role_reads_and_only_systemadmin_saves_or_applies(api, session, monkeypatch):
    seeded = await _seed(session)
    headers = {"X-Test-User": "someone@example.test"}
    async with _http(api) as http:
        for role in ROLES:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", role)
            got = await http.get("/agreements/hubspot-values", headers=headers)
            assert got.status_code == 200, (role, got.text)
            assert got.json()["can_edit"] is (role == "SystemAdmin")
            assert {i["value"] for i in got.json()["items"]} == {"Signed MSA", "MSA in progress"}
        # A read writes nothing (no user provisioning, no audit row).
        assert (await session.scalar(select(func.count()).select_from(User).where(
            User.email == "someone@example.test"))) == 0
        for role in ROLES:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", role)
            put = await http.put("/agreements/hubspot-mapping", headers=headers,
                                 json={"items": [{"value": "Signed MSA", "action": "covered"}]})
            dry = await http.post("/agreements/hubspot-mapping/apply", headers=headers)
            real = await http.post("/agreements/hubspot-mapping/apply?dry_run=false", headers=headers)
            if role == "SystemAdmin":
                assert put.status_code == 200, put.text
                assert {i["value"]: i["action"] for i in put.json()["items"]}["Signed MSA"] == "covered"
                assert dry.json() == {"dry_run": True, "would_mark": 3, "marked": 0}
                assert real.json() == {"dry_run": False, "would_mark": 3, "marked": 3}
            else:
                assert (put.status_code, dry.status_code, real.status_code) == (403, 403, 403), role
    marks = (await session.scalars(select(AgreementMark).where(AgreementMark.source == "hubspot"))).all()
    assert {m.client_id for m in marks} == {c.id for c in seeded["signed"]}
    assert all(m.marked_by == _uid("someone@example.test") for m in marks)


async def test_put_validates_the_values(api, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    headers = {"X-Test-User": "admin@example.test"}
    async with _http(api) as http:
        blank = await http.put("/agreements/hubspot-mapping", headers=headers,
                               json={"items": [{"value": "   ", "action": "covered"}]})
        twice = await http.put("/agreements/hubspot-mapping", headers=headers,
                               json={"items": [{"value": "A", "action": "covered"}, {"value": " A ", "action": "ignore"}]})
        bad = await http.put("/agreements/hubspot-mapping", headers=headers,
                             json={"items": [{"value": "A", "action": "maybe"}]})
        long = await http.put("/agreements/hubspot-mapping", headers=headers,
                              json={"items": [{"value": "x" * 201, "action": "covered"}]})
        empty = await http.put("/agreements/hubspot-mapping", headers=headers, json={"items": []})
    assert [r.status_code for r in (blank, twice, bad, long)] == [422, 422, 422, 422]
    assert empty.status_code == 200 and empty.json()["items"] == []


async def test_a_test_identity_cannot_change_the_mapping_outside_local_and_test(api, session, monkeypatch):
    bot = AuthUser(id=uuid.uuid4(), email="bot@example.test", name="E2E bot",
                   groups=("SystemAdmin", "officeapp-e2e"))
    main_app.dependency_overrides[current_user] = lambda: bot
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    async with _http(api) as http:
        got = await http.get("/agreements/hubspot-values")
        put = await http.put("/agreements/hubspot-mapping", json={"items": [{"value": "A", "action": "covered"}]})
        dry = await http.post("/agreements/hubspot-mapping/apply")
        real = await http.post("/agreements/hubspot-mapping/apply?dry_run=false")
    assert got.status_code == 200 and got.json()["can_edit"] is False
    assert put.status_code == 403 and "nightly sync" in put.json()["detail"]
    assert dry.status_code == 200 and dry.json()["marked"] == 0
    assert real.status_code == 403
    assert (await session.scalar(select(func.count()).select_from(AgreementHubspotMap))) == 0


# --- after a sync -------------------------------------------------------------------------------


async def _run_columns(factory) -> list[tuple]:
    async with factory() as s:
        runs = (await s.scalars(select(HubspotSyncRun).order_by(HubspotSyncRun.started_at))).all()
        return [(r.kind, r.status, r.deals_seen, r.deals_written, r.error_count, r.errors, r.fatal_error,
                 r.counts) for r in runs]


async def test_the_nightly_sync_applies_the_mapping_and_leaves_its_run_record_unchanged(factory):
    from tests.conftest import _memory_engine

    def stub() -> StubHubSpotClient:
        return StubHubSpotClient(
            deals={"d1": _deal("d1", company="c1", msa="Signed MSA"),
                   "d2": _deal("d2", company="c2", msa="Signed MSA"),
                   "d3": _deal("d3", company="c3", msa="Verbal only")},
            companies={f"c{i}": {"id": f"c{i}", "properties": {"name": f"Company {i}"}} for i in (1, 2, 3)})

    # Baseline: the same sync on a database with no mapping.
    plain_engine = await _memory_engine(postgres_like_transactions=True)
    try:
        plain = async_sessionmaker(plain_engine, expire_on_commit=False, class_=AsyncSession)
        plain_outcome = await run_deal_sync("nightly", stub(), session_factory=plain)
        plain_runs = await _run_columns(plain)
    finally:
        await plain_engine.dispose()

    async with factory() as s:
        saver = await _user(s, "saver@example.test", "Sam Saver")
        await s.commit()
        await save_mapping(s, actor_id=saver.id, items=[("Signed MSA", "covered")])
        await s.commit()
    outcome = await run_deal_sync("nightly", stub(), session_factory=factory)
    assert outcome.status == "ok"
    async with factory() as s:
        marks = (await s.scalars(select(AgreementMark))).all()
        names = {(await s.get(Client, m.client_id)).name for m in marks}
        summary = (await s.scalars(select(AuditEvent).where(
            AuditEvent.action == agreement_audit.HUBSPOT_APPLIED))).one()
    assert names == {"Company 1", "Company 2"}
    assert all(m.marked_by == saver.id and m.source == "hubspot" for m in marks)
    assert summary.actor_id is None and summary.after["trigger"] == "sync" and summary.after["marked"] == 2
    # The run record and the outcome are exactly what a run without a mapping records.
    assert await _run_columns(factory) == plain_runs
    assert (outcome.status, outcome.deals_seen, outcome.deals_written, outcome.error_count, outcome.errors,
            outcome.fatal_error, outcome.counts) == (
        plain_outcome.status, plain_outcome.deals_seen, plain_outcome.deals_written, plain_outcome.error_count,
        plain_outcome.errors, plain_outcome.fatal_error, plain_outcome.counts)


async def test_a_partial_sync_does_not_apply_and_a_failing_apply_never_fails_the_sync(factory, monkeypatch):
    async with factory() as s:
        saver = await _user(s, "saver@example.test", "Sam Saver")
        await s.commit()
        await save_mapping(s, actor_id=saver.id, items=[("Signed MSA", "covered")])
        await s.commit()
    stub = StubHubSpotClient(
        deals={"d1": _deal("d1", company="c1", msa="Signed MSA"),
               "d2": _deal("d2", company="c2", stage="no-such-stage")},
        companies={"c1": {"id": "c1", "properties": {"name": "Acme"}},
                   "c2": {"id": "c2", "properties": {"name": "Beta"}}})
    assert (await run_deal_sync("nightly", stub, session_factory=factory)).status == "partial"
    async with factory() as s:
        assert (await s.scalar(select(func.count()).select_from(AgreementMark))) == 0

    async def boom(*_args, **_kwargs):
        raise RuntimeError("apply exploded")

    monkeypatch.setattr(agreement_hubspot, "apply_mapping", boom)
    del stub.deals["d2"]
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)
    assert outcome.status == "ok" and outcome.error_count == 0
    async with factory() as s:
        assert (await s.scalar(select(func.count()).select_from(AgreementMark))) == 0
        [last] = (await s.scalars(select(HubspotSyncRun).order_by(HubspotSyncRun.started_at.desc())
                                  .limit(1))).all()
    assert last.status == "ok" and last.error_count == 0
