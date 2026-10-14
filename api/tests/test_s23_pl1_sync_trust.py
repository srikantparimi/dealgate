"""S23-PL1 — make the Pipeline data trustworthy (docs/directives/s23-pl1-sync-trust.md).

Item 10 tests: run records (ok / partial / failed), freshness at 1 h, 35 h,
37 h and after a failed attempt with a frozen clock, per-record isolation,
closed and Hold stages preserved on the nightly path, the webhook guard, and
the intake heartbeat no longer affecting freshness. Plus the endpoint's role
gate, the worker's exit code and the SystemAdmin trigger's run record.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session
from app.integrations.hubspot import StubHubSpotClient, get_hubspot_client
from app.main import app as main_app
from app.models.client import Client
from app.models.hubspot_sync_run import HubspotSyncRun
from app.models.integration import IntegrationEvent
from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus
from app.routers.pipeline import _load_freshness
from app.services import hubspot_backfill, hubspot_sync_runs
from app.services.hubspot_backfill import run_backfill
from app.services.hubspot_intake import (
    StageMapRequiredError,
    UnmappedStageError,
    _upsert_opportunity,
    handle_event,
)
from app.services.hubspot_stage_mirror import load_stage_map
from app.services.hubspot_sync_runs import compute_sync_health, run_deal_sync, start_run
from worker import hubspot_reconcile

T0 = datetime(2026, 10, 14, 4, 2, tzinfo=UTC)

STAGING_PIPELINE = {
    "id": "710688094", "label": "SmarTek21 Global Pipeline", "displayOrder": 2, "archived": False,
    "stages": [
        {"id": "1038193692", "label": "1-Initial Contact/Prospecting", "displayOrder": 0,
         "archived": False, "metadata": {"isClosed": "false", "probability": "0.1"}},
        {"id": "1038553758", "label": "7-Closed Won", "displayOrder": 6, "archived": False,
         "metadata": {"isClosed": "true", "probability": "1.0"}},
        {"id": "1038553759", "label": "8-Closed Lost", "displayOrder": 7, "archived": False,
         "metadata": {"isClosed": "true", "probability": "0.0"}},
        {"id": "1182672128", "label": "Hold", "displayOrder": 8, "archived": False,
         "metadata": {"isClosed": "false", "probability": "0.1"}},
    ],
}
OPEN, WON, LOST, HOLD = "1038193692", "1038553758", "1038553759", "1182672128"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("SALES_LEADER_EMAIL", raising=False)
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


@pytest_asyncio.fixture
async def engine(savepoint_engine):
    # S23-PL1: per-deal SAVEPOINTs must roll back with their page, as on PostgreSQL.
    return savepoint_engine


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _deal(deal_id: str, stage: str, *, pipeline: str = "default", company: str | None = None,
          modified: str = "2026-10-13T12:00:00Z") -> dict:
    payload = {"id": deal_id, "properties": {
        "dealname": f"Deal {deal_id}", "dealstage": stage, "pipeline": pipeline,
        "amount": "1000", "deal_currency_code": "USD", "closedate": "2026-12-31",
        "hs_lastmodifieddate": modified}}
    if company:
        payload["associations"] = {"companies": {"results": [{"id": company, "type": "deal_to_company"}]}}
    return payload


async def _opps(factory) -> dict[str, Opportunity]:
    async with factory() as s:
        rows = (await s.scalars(select(Opportunity))).all()
    return {row.hubspot_deal_id: row for row in rows}


async def _runs(factory) -> list[HubspotSyncRun]:
    async with factory() as s:
        return list((await s.scalars(select(HubspotSyncRun).order_by(HubspotSyncRun.started_at))).all())


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.hubapi.com/x")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(status, request=request))


# --- items 1, 3, 4: run records ----------------------------------------------


async def test_ok_run_writes_one_complete_row(factory):
    stub = StubHubSpotClient(deals={"d1": _deal("d1", "qualifiedtobuy"), "d2": _deal("d2", "closedwon")})
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)

    assert outcome.status == "ok"
    [run] = await _runs(factory)
    assert run.kind == "nightly" and run.status == "ok"
    assert run.started_at is not None and run.finished_at is not None
    assert (run.deals_seen, run.deals_written, run.error_count, run.errors) == (2, 2, 0, [])
    async with factory() as s:
        legacy = await s.get(SyncStatus, "hubspot_reconcile")
    assert legacy.last_success_at is not None and legacy.last_error is None


async def test_partial_run_lists_the_bad_deal_and_saves_the_rest(factory):
    stub = StubHubSpotClient(deals={
        "d1": _deal("d1", "qualifiedtobuy"),
        "d2": _deal("d2", "no-such-stage"),
        "d3": _deal("d3", "contractsent")})
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)

    assert outcome.status == "partial"
    assert outcome.error_count == 1
    assert outcome.errors == [{"hubspot_id": "d2", "reason": "deal: stage no-such-stage not mapped"}]
    assert set(await _opps(factory)) == {"d1", "d3"}
    [run] = await _runs(factory)
    assert (run.status, run.deals_seen, run.deals_written, run.error_count) == ("partial", 3, 2, 1)
    async with factory() as s:
        legacy = await s.get(SyncStatus, "hubspot_reconcile")
    # Never recorded as success when it did not succeed.
    assert legacy.last_success_at is None and legacy.last_error.startswith("partial")


async def test_run_that_cannot_read_hubspot_fails_with_its_reason(factory):
    class Unreadable(StubHubSpotClient):
        async def list_deals_page(self, **_kwargs):
            raise _http_error(401)

    outcome = await run_deal_sync("nightly", Unreadable(deals={"d1": _deal("d1", "qualifiedtobuy")}),
        session_factory=factory)

    assert outcome.status == "failed"
    assert outcome.fatal_error == "deal scan: HTTP 401"
    assert outcome.errors[0] == {"hubspot_id": "", "reason": "deal scan: HTTP 401"}
    assert await _opps(factory) == {}
    async with factory() as s:
        legacy = await s.get(SyncStatus, "hubspot_reconcile")
    assert legacy.last_success_at is None and legacy.last_error.startswith("failed")


async def test_stage_metadata_outage_is_fatal_not_silent(factory):
    class NoPipelines(StubHubSpotClient):
        async def list_pipelines(self):
            raise httpx.ConnectError("down")

    outcome = await run_deal_sync("manual", NoPipelines(deals={"d1": _deal("d1", "qualifiedtobuy")}),
        session_factory=factory)
    assert outcome.status == "failed"
    assert outcome.fatal_error == "stage metadata: ConnectError"
    assert await _opps(factory) == {}


async def test_unhandled_exception_ends_the_run_failed(factory, monkeypatch):
    async def explode(*_args, **_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(hubspot_sync_runs, "run_backfill", explode)
    outcome = await run_deal_sync("nightly", StubHubSpotClient(), session_factory=factory)
    assert outcome.status == "failed" and outcome.fatal_error == "sync: RuntimeError"
    [run] = await _runs(factory)
    assert run.status == "failed" and run.finished_at is not None


async def test_errors_list_keeps_five_and_counts_all(factory):
    deals = {f"d{i}": _deal(f"d{i}", f"bad-{i}") for i in range(7)}
    deals["ok"] = _deal("ok", "qualifiedtobuy")
    outcome = await run_deal_sync("nightly", StubHubSpotClient(deals=deals), session_factory=factory)
    assert outcome.status == "partial"
    assert outcome.error_count == 7
    assert len(outcome.errors) == 5
    assert all(set(e) == {"hubspot_id", "reason"} for e in outcome.errors)
    # Reasons are built from ids, never from deal names.
    assert not any("Deal " in e["reason"] for e in outcome.errors)


# --- item 3: the worker fails loudly ------------------------------------------


async def test_test_failure_run_records_failed_and_reads_nothing(factory, monkeypatch):
    monkeypatch.setattr(hubspot_sync_runs, "default_session_factory", factory)
    outcome = await hubspot_reconcile.run_once(test_failure=True)

    assert (outcome.kind, outcome.status) == ("test", "failed")
    assert outcome.fatal_error == "stage metadata: InjectedSyncFailure"
    assert hubspot_reconcile.exit_code(outcome) == 1
    assert await _opps(factory) == {}
    async with factory() as s:
        # A test run never touches the nightly reconcile row.
        assert await s.get(SyncStatus, "hubspot_reconcile") is None


def test_main_exit_code_is_non_zero_only_for_failed(monkeypatch):
    def outcome(status):
        return hubspot_sync_runs.SyncRunOutcome(uuid.uuid4(), "nightly", status, 1, 1, 0)

    for status, code in (("ok", 0), ("partial", 0), ("failed", 1)):
        async def fake(*, client=None, test_failure=False, _status=status):
            return outcome(_status)

        monkeypatch.setattr(hubspot_reconcile, "run_once", fake)
        assert hubspot_reconcile.main([]) == code


# --- item 2: freshness with a frozen clock ------------------------------------


async def _add_run(session, *, status="ok", finished=T0, written=10, kind="nightly",
                   started=None, errors=None):
    session.add(HubspotSyncRun(id=uuid.uuid4(), kind=kind, status=status,
        started_at=started or (finished - timedelta(minutes=2) if finished else T0),
        finished_at=finished, deals_seen=written, deals_written=written,
        error_count=len(errors or []), errors=errors or []))
    await session.commit()


@pytest.mark.parametrize(("hours", "state"), [(1, "fresh"), (35, "fresh"), (37, "stale")])
async def test_state_by_age_of_last_success(session, hours, state):
    await _add_run(session)
    health = await compute_sync_health(session, now=T0 + timedelta(hours=hours))
    assert health["state"] == state
    assert health["last_success_at"] == "2026-10-14T04:02:00Z"
    assert health["last_status"] == "ok" and health["schedule"] == "nightly"


async def test_state_failed_after_a_failed_attempt(session):
    await _add_run(session)
    await _add_run(session, status="failed", finished=T0 + timedelta(hours=24), written=0,
        errors=[{"hubspot_id": "", "reason": "deal scan: HTTP 401"}])
    health = await compute_sync_health(session, now=T0 + timedelta(hours=25))
    assert health["state"] == "failed" and health["last_status"] == "failed"
    assert health["last_success_at"] == "2026-10-14T04:02:00Z"
    assert health["last_attempt_at"] == "2026-10-15T04:02:00Z"
    assert health["errors"] == [{"hubspot_id": "", "reason": "deal scan: HTTP 401"}]


async def test_partial_run_is_the_success_time_but_state_is_failed(session):
    await _add_run(session, status="partial", errors=[{"hubspot_id": "9", "reason": "deal: x"}])
    health = await compute_sync_health(session, now=T0 + timedelta(hours=1))
    assert (health["state"], health["last_status"]) == ("failed", "partial")
    assert health["last_success_at"] == "2026-10-14T04:02:00Z"


async def test_run_that_wrote_nothing_is_not_a_success(session):
    await _add_run(session, finished=T0 - timedelta(hours=40))
    await _add_run(session, finished=T0, written=0)
    health = await compute_sync_health(session, now=T0 + timedelta(hours=1))
    assert health["last_success_at"] == "2026-10-12T12:02:00Z"
    assert health["state"] == "stale"


async def test_in_flight_run_is_ignored_and_abandoned_run_is_failed(session, factory):
    await _add_run(session)
    session.add(HubspotSyncRun(id=uuid.uuid4(), kind="nightly", status="running",
        started_at=T0 + timedelta(hours=20), errors=[]))
    await session.commit()
    in_flight = await compute_sync_health(session, now=T0 + timedelta(hours=20, minutes=5))
    assert in_flight["state"] == "fresh" and in_flight["last_status"] == "ok"
    abandoned = await compute_sync_health(session, now=T0 + timedelta(hours=23))
    assert abandoned["state"] == "failed" and abandoned["last_status"] == "failed"
    assert abandoned["errors"][0]["reason"] == "run did not finish"
    await session.rollback()  # release the shared SQLite connection
    # The next run closes the dead row as failed.
    await start_run(factory, "nightly", now=T0 + timedelta(hours=23))
    async with factory() as s:
        dead = await s.scalar(select(HubspotSyncRun).where(
            HubspotSyncRun.started_at == T0 + timedelta(hours=20)))
    assert dead.status == "failed" and dead.fatal_error == "run did not finish"


async def test_a_run_refused_by_the_lease_does_not_mask_the_real_run(session):
    # Nightly starts while a manual run holds the scan lease: it fails at once.
    await _add_run(session, status="failed", started=T0 - timedelta(seconds=90),
        finished=T0 - timedelta(seconds=89), written=0,
        errors=[{"hubspot_id": "", "reason": "deal scan: ScanConflict: Scan is already leased"}])
    # The manual run that held the lease finishes after it.
    await _add_run(session, kind="manual", started=T0 - timedelta(minutes=2), finished=T0)
    health = await compute_sync_health(session, now=T0 + timedelta(minutes=1))
    assert (health["state"], health["last_status"]) == ("fresh", "ok")


async def test_a_dead_run_does_not_hide_a_later_successful_run(session):
    # Nightly started at T and died; an admin run recovered at T+30m.
    session.add(HubspotSyncRun(id=uuid.uuid4(), kind="nightly", status="running", started_at=T0, errors=[]))
    await session.commit()
    await _add_run(session, kind="manual", started=T0 + timedelta(minutes=30), finished=T0 + timedelta(minutes=32))
    for hours in (3, 20):
        health = await compute_sync_health(session, now=T0 + timedelta(hours=hours))
        assert (health["state"], health["last_status"]) == ("fresh", "ok")


async def test_a_closed_dead_run_stays_the_failed_attempt_until_a_newer_run_ends(session, factory):
    await _add_run(session, finished=T0)
    session.add(HubspotSyncRun(id=uuid.uuid4(), kind="nightly", status="running",
        started_at=T0 + timedelta(hours=24), errors=[]))
    await session.commit()
    await session.rollback()
    # The next night's run closes the dead row and is itself still in flight.
    await start_run(factory, "nightly", now=T0 + timedelta(hours=48))
    async with factory() as s:
        health = await compute_sync_health(s, now=T0 + timedelta(hours=48, minutes=1))
    assert (health["state"], health["last_status"]) == ("failed", "failed")
    assert health["last_attempt_at"] == "2026-10-15T04:02:00Z"
    assert health["errors"][0]["reason"] == "run did not finish"


async def test_a_partial_or_failed_run_never_marks_the_backfill_row_successful(factory):
    stub = StubHubSpotClient(deals={"d1": _deal("d1", "qualifiedtobuy"), "d2": _deal("d2", "nope")})
    assert (await run_deal_sync("nightly", stub, session_factory=factory)).status == "partial"
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row.scan_phase == "completed"
    assert row.last_success_at is None and row.last_error == "partial: 1 record errors"
    only_bad = StubHubSpotClient(deals={"d3": _deal("d3", "nope")})
    assert (await run_deal_sync("nightly", only_bad, session_factory=factory)).status == "failed"
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row.last_success_at is None and row.last_error.startswith("failed: ")
    clean = StubHubSpotClient(deals={"d1": _deal("d1", "qualifiedtobuy", modified="2026-10-14T00:00:00Z")})
    assert (await run_deal_sync("nightly", clean, session_factory=factory)).status == "ok"
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row.last_success_at is not None and row.last_error is None


async def test_stage_errors_mark_the_pipeline_mirror_row(factory):
    pipeline = {**STAGING_PIPELINE, "stages": [*STAGING_PIPELINE["stages"],
        {"id": "bad", "label": "Bad", "displayOrder": 9, "archived": False,
         "metadata": {"isClosed": "true", "probability": "0.5"}}]}
    stub = StubHubSpotClient(pipelines=[pipeline], deals={"d1": _deal("d1", OPEN, pipeline="710688094")})
    await run_deal_sync("nightly", stub, session_factory=factory)
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_pipeline_mirror")
    assert row.last_success_at is None and row.last_error == "1 stage errors"


async def test_a_closed_dead_run_does_not_outrank_a_later_recovery(session, factory):
    # Nightly A died at T; admin run B recovered at T+1h; the next night closes A.
    session.add(HubspotSyncRun(id=uuid.uuid4(), kind="nightly", status="running", started_at=T0, errors=[]))
    await session.commit()
    await _add_run(session, kind="manual", started=T0 + timedelta(hours=1), finished=T0 + timedelta(hours=1, minutes=3))
    await session.rollback()
    await start_run(factory, "nightly", now=T0 + timedelta(hours=24))
    async with factory() as s:
        health = await compute_sync_health(s, now=T0 + timedelta(hours=24, minutes=1))
    assert (health["state"], health["last_status"]) == ("fresh", "ok")


async def test_before_any_run_the_last_completed_scan_is_used(session):
    session.add(SyncStatus(source="hubspot_backfill", scan_phase="completed",
        scan_completed_at=T0, last_success_at=T0, last_attempt_at=T0))
    await session.commit()
    health = await compute_sync_health(session, now=T0 + timedelta(hours=2))
    assert (health["state"], health["last_status"]) == ("fresh", "ok")
    assert health["last_success_at"] == "2026-10-14T04:02:00Z"


async def test_before_any_run_a_refused_completed_scan_reads_failed(session):
    session.add(SyncStatus(source="hubspot_backfill", scan_phase="completed", scan_completed_at=T0,
        last_success_at=None, last_attempt_at=T0, last_error="failed: 1 record errors"))
    await session.commit()
    health = await compute_sync_health(session, now=T0 + timedelta(minutes=5))
    assert (health["state"], health["last_status"]) == ("failed", "failed")
    assert health["last_success_at"] is None


async def test_with_no_history_state_is_failed_with_a_reason(session):
    health = await compute_sync_health(session, now=T0)
    assert health["state"] == "failed" and health["last_success_at"] is None
    assert health["errors"][0]["reason"] == "no completed deal sync recorded"


# --- item 8: the intake heartbeat no longer affects freshness -----------------


async def test_heartbeat_does_not_affect_sync_health_or_list_freshness(session):
    await _add_run(session, finished=T0)
    session.add_all([
        SyncStatus(source="hubspot_webhook", last_success_at=T0 - timedelta(days=12),
            last_attempt_at=T0 - timedelta(days=12)),
        SyncStatus(source="hubspot_consumer", last_success_at=T0 - timedelta(days=12),
            last_attempt_at=T0 - timedelta(days=12), last_error="stale"),
    ])
    await session.commit()
    now = T0 + timedelta(hours=2)
    health = await compute_sync_health(session, now=now)
    meta = await _load_freshness(session, now=now)
    assert health["state"] == "fresh" and health["last_success_at"] == "2026-10-14T04:02:00Z"
    assert meta.state == "verified working" and meta.reconciled_at == T0

    # A brand-new heartbeat cannot rescue a failed sync either.
    for row in (await session.scalars(select(SyncStatus))).all():
        row.last_success_at, row.last_error = now, None
    await _add_run(session, status="failed", finished=T0 + timedelta(hours=1), written=0)
    assert (await compute_sync_health(session, now=now))["state"] == "failed"
    assert (await _load_freshness(session, now=now)).state == "Failed"


# --- item 4: per-record isolation ---------------------------------------------


async def test_one_poisoned_deal_rolls_back_alone(factory, monkeypatch):
    real = hubspot_backfill._upsert_opportunity

    async def poisoned(session, deal_id, *args, **kwargs):
        if deal_id == "d2":
            raise RuntimeError("poison")
        return await real(session, deal_id, *args, **kwargs)

    monkeypatch.setattr(hubspot_backfill, "_upsert_opportunity", poisoned)
    stub = StubHubSpotClient(deals={d: _deal(d, "qualifiedtobuy") for d in ("d1", "d2", "d3")})
    counts = await run_backfill(stub, session_factory=factory)

    assert counts.fatal_error is None and counts.scan_completed
    assert counts.record_errors == [{"hubspot_id": "d2", "reason": "deal: RuntimeError"}]
    assert set(await _opps(factory)) == {"d1", "d3"}
    async with factory() as s:
        # d2's placeholder client was created inside its savepoint and rolled back.
        assert await s.scalar(select(func.count()).select_from(Client)) == 2


async def test_bad_company_is_listed_and_its_deal_skipped(factory):
    class FlakyCompanies(StubHubSpotClient):
        async def get_company(self, company_id, *, additional_properties=()):
            if company_id == "c2":
                raise _http_error(500)
            return await super().get_company(company_id, additional_properties=additional_properties)

    stub = FlakyCompanies(
        deals={"d1": _deal("d1", "qualifiedtobuy", company="c1"),
               "d2": _deal("d2", "qualifiedtobuy", company="c2")},
        companies={"c1": {"id": "c1", "properties": {"name": "Acme"}}})
    counts = await run_backfill(stub, session_factory=factory)

    assert counts.fatal_error is None
    assert {"hubspot_id": "c2", "reason": "company: HTTP 500"} in counts.record_errors
    assert {"hubspot_id": "d2", "reason": "deal: company c2 unavailable (HTTP 500)"} in counts.record_errors
    assert set(await _opps(factory)) == {"d1"}


async def test_an_unavailable_secondary_company_blocks_the_deal_and_keeps_its_secondaries(factory):
    class Flaky(StubHubSpotClient):
        down = set()

        async def get_company(self, company_id, *, additional_properties=()):
            if company_id in self.down:
                raise _http_error(500)
            return await super().get_company(company_id, additional_properties=additional_properties)

    deal = _deal("d1", "qualifiedtobuy", company="c1")
    deal["associations"]["companies"]["results"].append({"id": "c2", "type": "deal_to_company"})
    stub = Flaky(deals={"d1": deal}, companies={
        "c1": {"id": "c1", "properties": {"name": "One"}}, "c2": {"id": "c2", "properties": {"name": "Two"}}})
    await run_backfill(stub, session_factory=factory)
    stored = (await _opps(factory))["d1"].hubspot_secondary_client_ids
    assert stored and len(stored) == 1

    stub.down = {"c2"}
    stub.deals["d1"]["properties"]["hs_lastmodifieddate"] = "2026-10-14T00:00:00Z"
    counts = await run_backfill(stub, session_factory=factory)
    assert {"hubspot_id": "d1", "reason": "deal: company c2 unavailable (HTTP 500)"} in counts.record_errors
    assert (await _opps(factory))["d1"].hubspot_secondary_client_ids == stored


async def test_long_standing_unconfirmable_absences_cannot_starve_real_deletions(factory):
    class Provider(StubHubSpotClient):
        unconfirmable: set = set()
        async def get_archived_deal(self, deal_id):
            return None if deal_id in self.unconfirmable else {"id": deal_id, "archived": True}

    stub = Provider(deals={f"d{i}": _deal(f"d{i}", "qualifiedtobuy") for i in range(1, 8)})
    await run_backfill(stub, session_factory=factory)
    # Night 2: five deals vanish and HubSpot never confirms them (merged, purged).
    stub.unconfirmable = {f"d{i}" for i in range(1, 6)}
    for i in range(1, 6):
        del stub.deals[f"d{i}"]
    await run_backfill(stub, session_factory=factory)
    # Night 3: two more deals are really deleted.
    del stub.deals["d6"], stub.deals["d7"]
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.deals_archived == 2
    opps = await _opps(factory)
    assert opps["d6"].archived_at is not None and opps["d7"].archived_at is not None
    assert all(opps[f"d{i}"].archived_at is None for i in range(1, 6))


async def test_a_failed_scan_older_than_twelve_hours_restarts_at_page_one(factory):
    class FailsOnPageTwo(StubHubSpotClient):
        fail = True
        async def list_deals_page(self, *, after=None, limit=100, **kwargs):
            if after and self.fail:
                self.fail = False
                raise _http_error(500)
            return await super().list_deals_page(after=after, limit=limit, **kwargs)

    stub = FailsOnPageTwo(deals={"a": _deal("a", "qualifiedtobuy"), "b": _deal("b", "qualifiedtobuy")})
    first = await run_backfill(stub, session_factory=factory, page_size=1)
    assert first.fatal_error == "deal scan: HTTP 500"
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
        row.scan_started_at = datetime.now(UTC) - timedelta(hours=13)
        await s.commit()
    second = await run_backfill(stub, session_factory=factory, page_size=1)
    assert second.scan_completed and second.scan_generation == first.scan_generation + 1
    assert second.deals_seen == 2  # page one was read again, not trusted from 13 h ago


async def test_a_scan_whose_earlier_pages_refused_records_is_restarted_not_resumed(factory):
    class FailsOnPageTwo(StubHubSpotClient):
        fail = True
        async def list_deals_page(self, *, after=None, limit=100, **kwargs):
            if after and self.fail:
                self.fail = False
                raise _http_error(503)
            return await super().list_deals_page(after=after, limit=limit, **kwargs)

    stub = FailsOnPageTwo(deals={"a": _deal("a", "renamed-stage"), "b": _deal("b", "qualifiedtobuy")})
    first = await run_backfill(stub, session_factory=factory, page_size=1)
    assert first.fatal_error == "deal scan: HTTP 503"
    assert {"hubspot_id": "a", "reason": "deal: stage renamed-stage not mapped"} in first.record_errors
    # The recovery run must not resume at page two and forget the refusal.
    second = await run_deal_sync("manual", stub, session_factory=factory)
    assert second.status == "partial" and second.deals_seen == 2
    assert {"hubspot_id": "a", "reason": "deal: stage renamed-stage not mapped"} in second.errors
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row.last_success_at is None and row.last_error == "partial: 1 record errors"


async def test_bad_stage_is_listed_and_the_rest_of_the_pipeline_maps(factory):
    pipeline = {**STAGING_PIPELINE, "stages": [
        *STAGING_PIPELINE["stages"],
        {"id": "bad", "label": "Contradictory", "displayOrder": 9, "archived": False,
         "metadata": {"isClosed": "true", "probability": "0.5"}}]}
    stub = StubHubSpotClient(pipelines=[pipeline], deals={
        "d1": _deal("d1", OPEN, pipeline="710688094"),
        "d2": _deal("d2", "bad", pipeline="710688094")})
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)

    assert outcome.status == "partial"
    assert {"hubspot_id": "bad", "reason": "stage: stage_metadata_contradictory_closed_classification"} in outcome.errors
    assert {"hubspot_id": "d2", "reason": "deal: stage bad not mapped"} in outcome.errors
    assert set(await _opps(factory)) == {"d1"}


async def test_unconfirmed_deletion_is_listed_not_archived_and_scan_completes(factory):
    stub = StubHubSpotClient(deals={"d1": _deal("d1", "qualifiedtobuy"), "d2": _deal("d2", "qualifiedtobuy")})
    await run_backfill(stub, session_factory=factory)

    class Unconfirmed(StubHubSpotClient):
        async def get_archived_deal(self, deal_id):
            return None  # HubSpot no longer knows the deal at all

    second = Unconfirmed(deals={"d1": _deal("d1", "qualifiedtobuy", modified="2026-10-13T13:00:00Z")})
    counts = await run_backfill(second, session_factory=factory)
    assert counts.scan_completed and counts.fatal_error is None
    assert counts.record_errors == [{"hubspot_id": "d2", "reason": "deal: missing from HubSpot but deletion not confirmed"}]
    assert (await _opps(factory))["d2"].archived_at is None


# --- item 5: stage mapping keeps closed deals closed and Hold as Hold ----------


async def test_nightly_keeps_closed_won_and_lost_closed_and_hold_as_hold(factory):
    deals = {"won": _deal("won", WON, pipeline="710688094"),
             "lost": _deal("lost", LOST, pipeline="710688094"),
             "hold": _deal("hold", HOLD, pipeline="710688094"),
             "open": _deal("open", OPEN, pipeline="710688094")}
    stub = StubHubSpotClient(pipelines=[STAGING_PIPELINE], deals=deals)
    for _ in range(2):  # a second nightly run must not move anything
        assert (await run_deal_sync("nightly", stub, session_factory=factory)).status == "ok"
        opps = await _opps(factory)
        assert (opps["won"].is_closed_won, opps["won"].is_closed_lost) == (True, False)
        assert (opps["lost"].is_closed_won, opps["lost"].is_closed_lost) == (False, True)
        assert (opps["hold"].stage_label, opps["hold"].stage_order) == ("Hold", 8)
        assert not opps["hold"].is_closed_won and not opps["hold"].is_closed_lost
        assert opps["open"].stage_label == "1-Initial Contact/Prospecting"

    # HubSpot now reports a stage the map does not know: the deal is refused,
    # so a closed deal can never be reopened by a guessed mapping.
    stub.deals["won"] = _deal("won", "renamed-stage", pipeline="710688094",
        modified="2026-10-14T00:00:00Z")
    outcome = await run_deal_sync("nightly", stub, session_factory=factory)
    assert outcome.status == "partial"
    assert (await _opps(factory))["won"].is_closed_won is True


async def test_deal_writer_refuses_to_write_without_a_stage_map(session):
    with pytest.raises(StageMapRequiredError):
        await _upsert_opportunity(session, "x", _deal("x", "qualifiedtobuy"), None, None, "c")


# --- item 6: the webhook writer goes through the same stage mapping -------------


def _event(event_id: int, deal_id: str) -> dict:
    return {"eventId": event_id, "subscriptionType": "deal.propertyChange",
        "objectId": int(deal_id), "portalId": 1, "occurredAt": 1737000000000}


async def test_webhook_keeps_a_closed_won_deal_closed(factory):
    stub = StubHubSpotClient(pipelines=[STAGING_PIPELINE],
        deals={"101": _deal("101", WON, pipeline="710688094")})
    await run_deal_sync("nightly", stub, session_factory=factory)
    stub.deals["101"] = _deal("101", WON, pipeline="710688094", modified="2026-10-14T00:00:00Z")
    stub.deals["101"]["properties"]["amount"] = "2000"
    async with factory() as s:
        await handle_event(s, _event(1, "101"), stub)
    row = (await _opps(factory))["101"]
    assert (row.is_closed_won, row.stage_label, str(row.amount)) == (True, "7-Closed Won", "2000.00")


async def test_webhook_refuses_an_unmapped_stage_and_leaves_the_deal_alone(factory):
    stub = StubHubSpotClient(pipelines=[STAGING_PIPELINE],
        deals={"102": _deal("102", LOST, pipeline="710688094")})
    await run_deal_sync("nightly", stub, session_factory=factory)
    stub.deals["102"] = _deal("102", "mystery", pipeline="710688094", modified="2026-10-14T00:00:00Z")
    async with factory() as s:
        with pytest.raises(UnmappedStageError):
            await handle_event(s, _event(2, "102"), stub)
        await s.rollback()
    row = (await _opps(factory))["102"]
    assert (row.is_closed_lost, row.stage_label) == (True, "8-Closed Lost")
    async with factory() as s:
        stored = await s.scalar(select(IntegrationEvent).where(IntegrationEvent.source_event_id == "2"))
    assert stored is None or stored.processed_at is None


async def test_webhook_maps_a_new_stage_by_refreshing_the_mirror_once(factory):
    stub = StubHubSpotClient(pipelines=[STAGING_PIPELINE], deals={"103": _deal("103", HOLD, pipeline="710688094")})
    async with factory() as s:
        assert (await load_stage_map(s)).by_id == {}
        await handle_event(s, _event(3, "103"), stub)
    row = (await _opps(factory))["103"]
    assert (row.stage_label, row.is_closed_won, row.is_closed_lost) == ("Hold", False, False)


async def test_webhook_stage_refresh_commits_in_its_own_transaction(factory, monkeypatch):
    from app.services import hubspot_intake

    async def fail_after_refresh(*_args, **_kwargs):
        raise RuntimeError("deal write failed")

    monkeypatch.setattr(hubspot_intake, "_upsert_opportunity", fail_after_refresh)
    stub = StubHubSpotClient(pipelines=[STAGING_PIPELINE], deals={"105": _deal("105", HOLD, pipeline="710688094")})
    async with factory() as s:
        with pytest.raises(RuntimeError):
            await handle_event(s, _event(5, "105"), stub)
        await s.rollback()
    async with factory() as s:
        assert (await load_stage_map(s)).resolve(HOLD, "710688094").label == "Hold"
    assert await _opps(factory) == {}


async def test_webhook_keeps_secondary_companies(factory):
    stub = StubHubSpotClient(deals={"104": _deal("104", "qualifiedtobuy")})
    await run_deal_sync("nightly", stub, session_factory=factory)
    async with factory() as s:
        row = await s.scalar(select(Opportunity).where(Opportunity.hubspot_deal_id == "104"))
        row.hubspot_secondary_client_ids = ["keep-me"]
        await s.commit()
    stub.deals["104"] = _deal("104", "contractsent", modified="2026-10-14T00:00:00Z")
    async with factory() as s:
        await handle_event(s, _event(4, "104"), stub)
    assert (await _opps(factory))["104"].hubspot_secondary_client_ids == ["keep-me"]


# --- item 2: the endpoint, and the trigger used for the staging proof ----------


@pytest_asyncio.fixture
async def wired(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    # The trigger runs the sync on the app's own session factory, like the worker.
    monkeypatch.setattr(hubspot_sync_runs, "default_session_factory", factory)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    stub = StubHubSpotClient(deals={"201": _deal("201", "qualifiedtobuy")})
    main_app.dependency_overrides[get_session] = _override
    main_app.dependency_overrides[get_hubspot_client] = lambda: stub
    try:
        yield factory
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_hubspot_client, None)


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main_app), base_url="http://test")


async def test_sync_health_endpoint_shape_and_roles(wired, monkeypatch):
    async with wired() as s:
        await _add_run(s, finished=datetime.now(UTC) - timedelta(hours=1))
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client() as c:
        ok = await c.get("/hubspot/sync-health", headers={"X-Test-User": "rep@smartek21.com"})
        assert ok.status_code == 200
        body = ok.json()
        assert {"state", "last_success_at", "last_attempt_at", "last_status", "schedule"} <= set(body)
        assert body["state"] == "fresh" and body["last_status"] == "ok"
        assert body["recovery"] == {"available": True, "admin_only": True}
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
        denied = await c.get("/hubspot/sync-health", headers={"X-Test-User": "m@smartek21.com"})
        assert denied.status_code == 403
        assert (await c.get("/hubspot/sync-health")).status_code == 401


async def test_admin_trigger_records_a_manual_run(wired, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client() as c:
        r = await c.post("/integrations/hubspot/backfill", headers={"X-Test-User": "admin@smartek21.com"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["deals_written"] == 1
    [run] = await _runs(wired)
    assert (run.kind, run.status) == ("manual", "ok")
