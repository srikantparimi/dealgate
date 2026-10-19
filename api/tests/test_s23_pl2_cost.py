"""S23-PL2 B1 / B15 / T9 — the statement budget of the Pipeline workspace.

Statements are counted with the same ``before_cursor_execute`` listener the
query-service tests use (``test_hubspot_pipeline_query_service.py``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.models.hubspot_sync_run import HubspotSyncRun
from app.models.sync_status import SyncStatus
from app.services.hubspot_sync_runs import compute_sync_health

T0 = datetime(2026, 10, 14, 4, 2, tzinfo=UTC)


class Counter:
    def __init__(self) -> None:
        self.n = 0
        self.statements: list[str] = []


@pytest.fixture
def counter(engine):
    counter = Counter()

    def _before(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        counter.n += 1
        counter.statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before)


def _run(status="ok", *, started, finished, written=10, errors=None, kind="nightly"):
    return HubspotSyncRun(id=uuid.uuid4(), kind=kind, status=status, started_at=started,
        finished_at=finished, deals_seen=written, deals_written=written,
        error_count=len(errors or []), errors=errors or [])


async def _health_statements(session, counter, now):
    counter.n = 0
    health = await compute_sync_health(session, now=now)
    return health, counter.n


async def test_sync_health_is_one_statement_in_every_branch(session, counter):
    # No history at all (legacy fallback, no backfill row).
    health, n = await _health_statements(session, counter, T0)
    assert n == 1 and health["errors"][0]["reason"] == "no completed deal sync recorded"

    # Legacy fallback with a completed scan.
    session.add(SyncStatus(source="hubspot_backfill", scan_phase="completed",
        scan_completed_at=T0, last_success_at=T0, last_attempt_at=T0))
    await session.commit()
    health, n = await _health_statements(session, counter, T0 + timedelta(hours=1))
    assert n == 1 and (health["state"], health["last_status"]) == ("fresh", "ok")

    # Finished runs: an ok one, then a failed attempt.
    session.add(_run(started=T0 - timedelta(minutes=2), finished=T0))
    session.add(_run("failed", started=T0 + timedelta(hours=23), finished=T0 + timedelta(hours=24),
        written=0, errors=[{"hubspot_id": "", "reason": "deal scan: HTTP 401"}]))
    await session.commit()
    health, n = await _health_statements(session, counter, T0 + timedelta(hours=25))
    assert n == 1
    assert health == {
        "state": "failed",
        "last_success_at": "2026-10-14T04:02:00Z",
        "last_attempt_at": "2026-10-15T04:02:00Z",
        "last_status": "failed",
        "schedule": "nightly",
        "deals_seen": 0,
        "deals_written": 0,
        "error_count": 1,
        "errors": [{"hubspot_id": "", "reason": "deal scan: HTTP 401"}],
        "recovery": {"available": True, "admin_only": True},
    }

    # An abandoned run newer than every finished one is the last attempt.
    session.add(HubspotSyncRun(id=uuid.uuid4(), kind="nightly", status="running",
        started_at=T0 + timedelta(hours=30), errors=[]))
    await session.commit()
    health, n = await _health_statements(session, counter, T0 + timedelta(hours=33))
    assert n == 1
    assert (health["state"], health["last_status"]) == ("failed", "failed")
    assert health["last_attempt_at"] == "2026-10-15T10:02:00Z"
    assert health["errors"][0]["reason"] == "run did not finish"
    assert health["error_count"] == 1


# --- the workspace budget (T9) ------------------------------------------------------------

import os  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.models.client import Agreement, Client  # noqa: E402
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage  # noqa: E402
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap  # noqa: E402
from app.models.next_action import NextAction  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402
from app.models.sow import Sow  # noqa: E402
from app.models.tracking_group import TrackingGroup, TrackingGroupMember  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.watchlist import WatchedItem  # noqa: E402
from app.routers import pipeline as pipeline_routes  # noqa: E402
from app.services.hubspot_owners import HubspotOwner  # noqa: E402
from app.services.hubspot_properties import HubspotPropertyMapping  # noqa: E402
from tests import test_s23_pl2_workspace as shared  # noqa: E402
from tests.test_s23_pl2_workspace import (  # noqa: E402
    NOW,
    PIPELINE_ID,
    STAGES,
    VIEWER,
    VIEWER_DB_ID,
    client_for,
    seed_population,
)

# Shared fixtures, bound as module globals so pytest finds them here.
api, engine, frozen_clock, seeded = shared.api, shared.engine, shared.frozen_clock, shared.seeded

BUDGET = 8
SCENARIOS: dict[str, dict] = {
    "deals_default": {},
    "deals_filtered": {"status": "all", "stage": [1, 2, 9], "owner": ["101", "none"], "bu": ["ST21", "unmapped"],
                       "q": "a", "attention": "any", "missing": "msa", "date_field": "activity",
                       "date_preset": "last90", "watching": "true", "mine": "false", "sort": "activity",
                       "page_size": 50},
    "deals_group_board": {"layout": "board", "status": "all", "group": None},
    "clients_unmatched": {"tab": "clients", "include_unmatched_clients": "true", "account_owner": "101",
                          "sort": "name"},
}
# The old page's requests per filter change (backend map §1.1).
OLD_PAGE = ("/pipeline/clients", "/pipeline/opportunities", "/pipeline/opportunities?watching=true&page_size=25",
            "/pipeline/summary", "/sync-status", "/pipeline/facets", "/hubspot/sync-health")


async def _measure(api, counter, params: dict, *, runs: int = 1) -> tuple[int, float]:
    timings, statements = [], 0
    for _ in range(runs):
        counter.n = 0
        started = time.perf_counter()
        response = await api.get("/pipeline/workspace", params=params)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200, response.text
        statements = counter.n
    return statements, statistics.median(timings)


async def test_workspace_statement_budget(api, seeded, counter):
    measured = {}
    for name, params in SCENARIOS.items():
        params = {**params, "group": str(seeded.group)} if "group" in params else params
        measured[name], _ = await _measure(api, counter, params)
    assert all(n <= BUDGET for n in measured.values()), measured
    assert measured == {"deals_default": 7, "deals_filtered": 7, "deals_group_board": 7, "clients_unmatched": 8}
    counter.n = 0
    assert (await api.get("/pipeline/export", params={"status": "all"})).status_code == 200
    assert counter.n <= BUDGET


async def seed_staging_scale(session, *, region_map: bool = True) -> None:
    """About staging's size: 672 live HubSpot deals (110 open), 200 clients, 50 owners."""
    rng = random.Random(672)
    writer = User(email="scale-writer@example.test", name="Scale Writer", groups=["Legal"])
    viewer = User(id=VIEWER_DB_ID, email=VIEWER.email, name="Viewer Vance", groups=["SalesLeader"],
                  hubspot_owner_id="o0", hubspot_owner_link="email")
    session.add_all([writer, viewer, HubspotPipeline(id=PIPELINE_ID, label="SmarTek21 Global Pipeline",
                                                     display_order=2, archived=False)])
    await session.flush()
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order, is_closed=closed,
                                  probability=Decimal("0.10"), archived=False) for sid, label, order, closed in STAGES])
    session.add_all([HubspotOwner(id=f"o{i}", first_name=f"Owner{i}", last_name="Scale", email=f"o{i}@example.test",
                                  archived=i >= 26) for i in range(50)])
    regions = ["South Africa", "US - IT Avalon (Staffing)", "US - IT Avalon", "US"]
    session.add(HubspotPropertyMapping(key="business_unit", internal_name="region", object_type="deal",
                                       label="Region", field_type="enumeration", availability_state="configured",
                                       mapping_version=1, options=[{"value": v} for v in regions]))
    if region_map:
        session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    clients = [Client(name=f"Scale client {i:03}", hubspot_company_id=f"sc-{i}", hubspot_owner_id=f"o{i % 50}")
               for i in range(200)]
    session.add_all(clients)
    await session.flush()
    session.add_all([Agreement(client_id=c.id, kind=kind, file_key=f"a/{c.id}/{kind}", filename="a.pdf",
                               file_size=1, uploaded_by=writer.id)
                     for c in clients[:30] for kind in ("NDA", "MSA")[: 1 + (clients.index(c) % 2)]])
    deals = []
    for i in range(672):
        ordinal = rng.randint(1, 9) if i < 110 else rng.choice((7, 8))
        if i < 110 and ordinal in (7, 8):
            ordinal = 4
        sid, label, order, _ = STAGES[ordinal - 1]
        deals.append(Opportunity(
            source="hubspot", hubspot_deal_id=f"scale-{i}", name=f"Scale deal {i:03}",
            client_id=clients[i % 200].id, hubspot_owner_id=f"o{rng.randint(0, 49)}" if i % 40 else None,
            hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid, stage_label=label, stage_order=order,
            is_closed_won=ordinal == 7, is_closed_lost=ordinal == 8,
            amount=Decimal(rng.randint(1, 900) * 1000) if i % 25 else None, currency="USD",
            close_date=date(2026, 1, 1).replace(month=rng.randint(1, 12), day=rng.randint(1, 28)),
            # No activity timestamps: the old list code cannot read SQLite's naive values (pre-existing).
            hubspot_created_at=NOW, business_unit_value=rng.choice(regions), business_unit_mapping_version=1,
            business_unit_observed_at=NOW, governance_status="Intake"))
    session.add_all(deals)
    await session.flush()
    session.add_all([NextAction(opportunity_id=d.id, title=f"Step {n}", description="", owner_user_id=writer.id,
                                created_by=writer.id, due_date=date(2026, 10, 1 + n % 28))
                     for n, d in enumerate(deals[:60])])
    session.add_all([Sow(opportunity_id=d.id) for d in deals[:6]])
    session.add_all([WatchedItem(user_id=VIEWER_DB_ID, kind="opportunity", item_id=d.id) for d in deals[:5]])
    group = TrackingGroup(owner_id=VIEWER_DB_ID, name="Scale group", member_kind="opportunity")
    session.add(group)
    await session.flush()
    session.add_all([TrackingGroupMember(group_id=group.id, member_id=d.id) for d in deals[:3]])
    session.add(_run(started=NOW - timedelta(hours=3), finished=NOW - timedelta(hours=2)))
    await session.commit()


def _listener(counter: Counter):
    def _before(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        # The rolled-back Postgres harness wraps the session in SAVEPOINTs; they are not the endpoint's.
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT")):
            counter.n += 1
    return _before


async def _report(session, engine, label: str) -> dict:
    """Statements and median latency: the workspace vs the old page's seven requests."""
    counter = Counter()
    _before = _listener(counter)

    event.listen(engine.sync_engine, "before_cursor_execute", _before)
    try:
        async with client_for(session, VIEWER, pipeline_routes.router, pipeline_routes.sync_router,
                              pipeline_routes.sync_health_router) as client:
            after = {name: await _measure(client, counter, {k: v for k, v in params.items() if k != "group"},
                                          runs=5)
                     for name, params in SCENARIOS.items()}
            old_statements, old_seconds = 0, 0.0
            for _ in range(3):  # warm, then the measured passes
                counter.n, started = 0, time.perf_counter()
                for path in OLD_PAGE:
                    assert (await client.get(path)).status_code == 200, path
                old_statements, old_seconds = counter.n, time.perf_counter() - started
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before)
    report = {"label": label, "before": {"requests": len(OLD_PAGE), "statements": old_statements,
                                          "ms": round(old_seconds * 1000, 1)},
              "after": {name: {"statements": n, "median_ms": round(s * 1000, 1)} for name, (n, s) in after.items()}}
    print("T9", report)
    return report


async def test_workspace_cost_at_staging_scale(session, engine, frozen_clock):
    await seed_staging_scale(session)
    report = await _report(session, engine, "sqlite in-memory")
    assert all(row["statements"] <= BUDGET for row in report["after"].values()), report
    assert report["before"]["statements"] > report["after"]["deals_default"]["statements"]
    # In-process SQLite: a generous ceiling that still catches an N+1 or a quadratic filter.
    assert report["after"]["deals_default"]["median_ms"] < 2000, report


@asynccontextmanager
async def rolled_back_postgres():
    """A session on the local migrated Postgres whose work is always rolled back."""
    url = os.environ["DEALGATE_POSTGRES_URL"].replace("postgresql://", "postgresql+psycopg://")
    pg = create_async_engine(url)
    try:
        async with pg.connect() as connection:
            outer = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False,
                                   join_transaction_mode="create_savepoint")
            try:
                yield session, pg
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await pg.dispose()


POSTGRES = pytest.mark.skipif(not os.environ.get("DEALGATE_POSTGRES_URL"),
                              reason="requires the migrated local Postgres")


@POSTGRES
async def test_workspace_on_postgres(frozen_clock):
    """The dialect-sensitive SQL on PostgreSQL: same budget, same answers as SQLite."""
    async with rolled_back_postgres() as (session, pg):
        seed = await seed_population(session, region_map=False)  # migration 0070 seeds the map
        counter = Counter()
        _before = _listener(counter)

        event.listen(pg.sync_engine, "before_cursor_execute", _before)
        try:
            async with client_for(session, VIEWER) as client:
                counts = {}
                for name, params in SCENARIOS.items():
                    params = {**params, "group": str(seed.group)} if "group" in params else params
                    counts[name], _ = await _measure(client, counter, params)
                body = (await client.get("/pipeline/workspace")).json()
                clients = (await client.get("/pipeline/workspace",
                                            params={"tab": "clients", "include_unmatched_clients": "true"})).json()
        finally:
            event.remove(pg.sync_engine, "before_cursor_execute", _before)
    assert counts == {"deals_default": 7, "deals_filtered": 7, "deals_group_board": 7, "clients_unmatched": 8}, counts
    # Same answers as on SQLite (test_s23_pl2_workspace.test_default_response_has_the_contract_shape).
    assert body["metrics"]["open_deals"] == {"value": 12, "accounts": 5, "drill": {"tab": "deals", "status": "open"}}
    assert body["metrics"]["open_value_usd"]["value"] == "1075000.00"
    assert body["metrics"]["closing_this_month"]["value_usd"] == "855000.00"
    assert body["metrics"]["overdue_next_actions"]["with_next_action"] == 6
    assert body["metrics"]["pending_approvals"]["value"] == 3
    assert body["metrics"]["agreement_gap_clients"]["value"] == 3  # S24-AG1: Bolt, Cobalt, Echo need attention
    assert body["metrics"]["agreement_gap_clients"]["clients_total"] == 6
    assert body["focus"] == {"all_open": 12, "closing_this_month": 6, "mine": 2, "mine_available": True,
                             "needs_attention": 8, "watching": 2}
    assert [s["deals"] for s in body["stages"]] == [2, 3, 2, 1, 1, 1, 2, 1, 2]
    assert body["freshness"]["state"] == "fresh" and body["today"] == "2026-10-14"
    assert [seed.key_of(row["id"]) for row in body["rows"]] == [
        "d07", "d02", "d13", "d01", "d05", "d10", "d03", "d15", "d06", "d16", "d12", "d04"]
    assert clients["tab_counts"]["clients"] == 7


@POSTGRES
async def test_workspace_cost_on_postgres(frozen_clock):
    async with rolled_back_postgres() as (session, pg):
        await seed_staging_scale(session, region_map=False)
        # Staging's tables carry autovacuum statistics; rows inserted in this open transaction do not.
        await session.execute(text(
            "ANALYZE opportunity, client, hubspot_owner, next_action, agreement, watched_item, hubspot_pipeline, "
            "hubspot_stage, sow, sow_version, approval_package, tracking_group_member, hubspot_property_mapping, "
            "agreement_mark, agreements_settings, standard_agreement, engagement"))
        report = await _report(session, pg, "postgres local")
    assert all(row["statements"] <= BUDGET for row in report["after"].values()), report
    assert report["before"]["statements"] > report["after"]["deals_default"]["statements"]
