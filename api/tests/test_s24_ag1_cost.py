"""S24-AG1 T13 (lane T-B): what the Agreements page costs per call, before and after, on SQLite.

The population is realistic and synthetic, shaped like staging at discovery (AG0) but with no real names:
230 clients — 66 existing (Closed Won, an SOW, both, a forecast-style engagement with no HubSpot link, three whose
open deals are only in stage 1, one run-tagged test client) and 164 net new (10 past stage 1, 2 on Hold, 9 stage-1
only, 40 with only lost deals, 101 with no deal, the two "Unknown company (deal …)" placeholders) — with deals
across every stage carrying HubSpot regions (mapped, unmapped and blank), two duplicate-name pairs, the standard
NDA and MSA, 19 client copies (one with two versions), two covered marks and a removed one. Every document and
mark goes through the routes, so the audit log and the version history are the real ones.

Per call: the statements sent (SQLAlchemy ``before_cursor_execute``; SAVEPOINT/RELEASE left out, as in every
statement budget of this suite) and the median of 5 timed runs through the production routers, one database
session per request as the app runs:

* after — the redesigned page needs one request per view: GET /agreements/workspace for the default view,
  status=attention, a heavily filtered view and page_size=100, each at most 8 statements (directive B3, T13),
  snapshotted exactly; the client panel GET /clients/{id}/agreements and the batch dry run POST
  /agreements/batches, bounded and snapshotted;
* before — the old register page's two calls, GET /agreements and GET /clients?size=200, reported.

The "after" counts must not grow with the population: 25 more clients leave every one of them unchanged. The
Postgres numbers, the 67-client real batch and the one combined table are in test_s24_ag1_cost_pg.py, which
imports the builder and the harness below. Run with ``pytest -s`` to see the table.
"""

from __future__ import annotations

import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import AuthUser
from app.models.client import Client
from app.models.engagement import Engagement
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
from app.models.sow import Sow
from app.models.user import User
from app.services.hubspot_properties import HubspotPropertyMapping
from tests.test_s24_ag1_beb_client import (  # noqa: F401  (env: fixture)
    ADMIN,
    FINANCE,
    LEGAL,
    NOW,
    PDF,
    PIPELINE_ID,
    SALES,
    STAGES,
    TODAY,
    deal,
    env,
    upload,
)
from tests.test_s24_ag1_shared_object_pg import VersionedStore, api_for

# --- the population -----------------------------------------------------------------------------------------

# group -> clients. 66 existing + 164 net new = 230.
GROUPS: tuple[tuple[str, int], ...] = (
    ("won", 38), ("sow", 14), ("won_sow", 6), ("engagement", 4), ("sow_stage_1", 3), ("test", 1),
    ("past_stage_1", 10), ("hold", 2), ("stage_1", 9), ("lost", 40), ("none", 101), ("placeholder", 2),
)
# 25 more for the growth check: no new target, so the batch numbers stay put.
MORE: tuple[tuple[str, int], ...] = (("stage_1", 5), ("lost", 10), ("none", 10))
TREES = ("Alder", "Birch", "Cedar", "Dogwood", "Elm", "Fir", "Ginkgo", "Hazel", "Ivy", "Juniper", "Kapok", "Larch",
         "Maple", "Nutmeg", "Oak", "Pine", "Quince", "Rowan", "Spruce", "Teak", "Umber", "Vine", "Willow", "Yew")
TRADES = ("Analytics", "Bakery", "Cargo", "Dental", "Energy", "Foods", "Gaming", "Health", "Insurance", "Joinery",
          "Kitchens", "Labs", "Media", "Networks", "Optics", "Pharma", "Quarry", "Retail", "Systems", "Textiles")
SPECIAL = {
    ("test", 0): "smoke Umber Pilot 999",  # run-tagged: test data
    ("placeholder", 0): "Unknown company (deal 7001)",
    ("placeholder", 1): "Unknown company (deal 7002)",
    ("none", 0): "Rowan Textiles 900 LLC", ("none", 1): "Rowan Textiles 900, Inc.",  # possible duplicates
    ("won", 37): "Teak Optics 901 Co.", ("lost", 39): "Teak Optics 901",
}
# HubSpot region values on the deals: mapped to each business unit, unmapped ("Brazil") and blank.
REGIONS = ("US", "US - IT Avalon", "South Africa", "US - IT Avalon (Staffing)", None, "Brazil")
BU_OPTIONS = ("South Africa", "US - IT Avalon (Staffing)", "US - IT Avalon", "US", "Brazil")


def positions(group: str, i: int) -> list[int]:
    """Deal stage positions: 1-6 open, 7 Closed Won, 8 Closed Lost, 9 Hold."""
    return {
        "won": [7] + ([2 + i % 5] if i % 3 == 0 else []) + ([8] if i % 4 == 1 else []),
        "sow": [3 + i % 4] + ([8] if i % 3 == 2 else []),
        "won_sow": [7, 2 + i % 5],
        "engagement": [],
        "sow_stage_1": [1],
        "test": [7],
        "past_stage_1": [2 + i % 5] + ([1] if i % 2 else []) + ([8] if i % 3 == 0 else []),
        "hold": [9] if i % 2 == 0 else [9, 4],
        "stage_1": [1] + ([1] if i % 3 == 0 else []) + ([8] if i % 4 == 2 else []),
        "lost": [8] + ([8] if i % 5 == 0 else []),
        "none": [],
        "placeholder": [1] if i % 2 == 0 else [8],
    }[group]


@dataclass
class World:
    groups: dict[str, list[uuid.UUID]] = field(default_factory=dict)
    next_n: int = 0

    def __getitem__(self, key: tuple[str, int]) -> uuid.UUID:
        group, i = key
        return self.groups[group][i]

    @property
    def size(self) -> int:
        return sum(len(ids) for ids in self.groups.values())


async def reference_data(session) -> None:
    """Users, the staging stage mirror, the region map (a migrated Postgres already holds it) and the configured
    HubSpot business-unit property the deals' region values are read through."""
    for user in (ADMIN, LEGAL, SALES, FINANCE):
        session.add(User(id=user.id, email=user.email, name=user.name, groups=list(user.groups)))
    session.add(HubspotPipeline(id=PIPELINE_ID, label="Global Pipeline", display_order=0, archived=False))
    await session.flush()
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order,
                                  is_closed=closed, probability=Decimal("0.10"), archived=False)
                     for sid, label, order, closed in STAGES])
    if not await session.scalar(select(func.count()).select_from(HubspotRegionMap)):
        session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    mapping = await session.get(HubspotPropertyMapping, "business_unit")
    if mapping is None:
        mapping = HubspotPropertyMapping(key="business_unit")
        session.add(mapping)
    mapping.internal_name, mapping.object_type, mapping.label = "region", "deal", "Region"
    mapping.field_type, mapping.availability_state, mapping.mapping_version = "enumeration", "configured", 1
    mapping.options = [{"value": v, "label": v} for v in BU_OPTIONS]
    await session.commit()


async def add_clients(factory, world: World, groups: tuple[tuple[str, int], ...]) -> None:
    async with factory() as session:
        for group, size in groups:
            bucket = world.groups.setdefault(group, [])
            for i in range(len(bucket), len(bucket) + size):
                n = world.next_n
                world.next_n += 1
                name = SPECIAL.get((group, i)) or f"{TREES[n % len(TREES)]} {TRADES[n // len(TREES) % len(TRADES)]} {n:03d}"
                company = None if group in ("engagement", "placeholder") else f"co-{n:04d}"
                client = Client(name=name, hubspot_company_id=company)
                session.add(client)
                await session.flush()
                deals = []
                for j, position in enumerate(positions(group, i)):
                    row = deal(client.id, position, f"{n:03d}-{j}")
                    region = REGIONS[(n + j) % len(REGIONS)]
                    row.business_unit_value = region
                    row.business_unit_mapping_version = 1 if region else None
                    row.business_unit_observed_at = NOW if region else None
                    deals.append(row)
                session.add_all(deals)
                await session.flush()
                if group in ("sow", "won_sow", "sow_stage_1"):
                    session.add(Sow(opportunity_id=deals[0].id, created_at=NOW - timedelta(days=60 + i)))
                if group == "engagement":
                    session.add(Engagement(
                        client_id=client.id, name=f"{name} retainer", type="time_and_materials",
                        start=TODAY - timedelta(days=200), end=TODAY + timedelta(days=100),
                        business_unit=("IT Avalon", "Retro Rabbit", "ST21")[i % 3],
                        # On the frozen clock: a server-default (real) time after the frozen cutover would make
                        # these clients net new at the cutover whenever the suite runs after midnight in LA.
                        created_at=NOW - timedelta(days=200 - i)))
                bucket.append(client.id)
        await session.commit()


async def add_documents(factory, world: World, store: VersionedStore) -> None:
    """The standard NDA and MSA, 19 client copies, two covered marks and a removed mark, through the routes."""
    copies = [
        *((world["won", i], kind) for i in range(5) for kind in ("NDA", "MSA")),  # hold both: never a target
        (world["won", 0], "NDA"),  # a second version, with a note
        *((world["past_stage_1", i], kind) for i in range(2) for kind in ("NDA", "MSA")),
        *((world["won", i], "NDA") for i in range(5, 8)),  # targets that hold the NDA: skipped for it
        (world["none", 2], "NDA"),  # a net-new client that brought its own copy
    ]
    async with api_for(factory, LEGAL, storage=store) as legal:
        for kind in ("NDA", "MSA"):
            response = await legal.post(f"/agreements/standard/{kind}", **upload(f"Standard {kind}.pdf", PDF))
            assert response.status_code == 201, response.text
        for n, (client_id, kind) in enumerate(copies):
            note = "Updated payment terms" if n == 10 else None
            response = await legal.post(f"/clients/{client_id}/agreements/{kind}/client-copy",
                                        **upload(f"{kind.lower()}-copy-{n:02d}.pdf", PDF, note))
            assert response.status_code == 201, response.text
        for client_id in (world["sow", 0], world["sow", 1]):  # targets that hold the MSA as a mark
            response = await legal.put(f"/clients/{client_id}/agreements/MSA/mark",
                                       json={"reason": "signed_outside_dealgate", "marked_on": TODAY.isoformat()})
            assert response.status_code == 200, response.text
        lost = world["lost", 0]
        response = await legal.put(f"/clients/{lost}/agreements/NDA/mark",
                                   json={"reason": "other", "marked_on": TODAY.isoformat(), "note": "To confirm"})
        assert response.status_code == 200, response.text
        assert (await legal.delete(f"/clients/{lost}/agreements/NDA/mark")).status_code == 200


async def build_world(factory) -> tuple[World, VersionedStore]:
    world, store = World(), VersionedStore()
    async with factory() as session:
        await reference_data(session)
    await add_clients(factory, world, GROUPS)
    await add_documents(factory, world, store)
    assert world.size == 230
    return world, store


# --- the calls and the measurement -------------------------------------------------------------------------

HEAVY = {"relationship": "net_new", "status": "attention", "stage": "past_stage_1", "bu": ["ST21", "IT Avalon"],
         "q": "a", "sort": "stage", "page_size": 50}
DRY_RUN = {"kinds": ["NDA", "MSA"], "dry_run": True, "include_net_new_past_stage_1": True}


@dataclass(frozen=True)
class Call:
    key: str
    label: str
    user: AuthUser
    method: str
    path: str
    params: dict[str, Any] | None = None
    body: dict[str, Any] | None = None


def calls(world: World) -> list[Call]:
    panel = world["won", 0]  # an NDA client copy with two versions and an MSA client copy
    return [
        Call("workspace", "GET /agreements/workspace (default view)", SALES, "GET", "/agreements/workspace"),
        Call("attention", "GET /agreements/workspace?status=attention", SALES, "GET", "/agreements/workspace",
             {"status": "attention"}),
        Call("filtered", "GET /agreements/workspace (heavily filtered)", SALES, "GET", "/agreements/workspace",
             HEAVY),
        Call("page_100", "GET /agreements/workspace?page_size=100", SALES, "GET", "/agreements/workspace",
             {"page_size": 100}),
        Call("panel", "GET /clients/{id}/agreements (client panel)", SALES, "GET", f"/clients/{panel}/agreements"),
        Call("dry_run", "POST /agreements/batches (dry run)", ADMIN, "POST", "/agreements/batches", body=DRY_RUN),
        Call("old_agreements", "before: GET /agreements (old register)", LEGAL, "GET", "/agreements"),
        Call("old_clients", "before: GET /clients?size=200 (old register)", LEGAL, "GET", "/clients",
             {"size": 200}),
    ]


AFTER = ("workspace", "attention", "filtered", "page_100", "panel", "dry_run")
WORKSPACE_VIEWS = ("workspace", "attention", "filtered", "page_100")


@dataclass
class Cost:
    key: str
    label: str
    db: str
    counts: list[int]
    median_ms: float
    runs: int = 5

    @property
    def statements(self) -> int:
        return self.counts[-1]


class StatementCounter:
    """Every statement the engine sends (SAVEPOINT and RELEASE left out), while ``on``."""

    def __init__(self, engine) -> None:
        self.engine, self.seen, self.on = engine, [], True

    def __call__(self, conn, cursor, statement, parameters, context, executemany):  # noqa: ARG002
        if self.on and not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
            self.seen.append(statement)

    def __enter__(self) -> StatementCounter:
        event.listen(self.engine.sync_engine, "before_cursor_execute", self)
        return self

    def __exit__(self, *exc) -> None:
        event.remove(self.engine.sync_engine, "before_cursor_execute", self)


async def measure(engine, factory, call: Call, db: str, runs: int = 5) -> tuple[Cost, Any]:
    counts: list[int] = []
    times: list[float] = []
    async with api_for(factory, call.user) as api:
        with StatementCounter(engine) as counter:
            for _ in range(runs):
                counter.seen.clear()
                started = time.perf_counter()
                response = await api.request(call.method, call.path, params=call.params, json=call.body)
                times.append((time.perf_counter() - started) * 1000.0)
                assert response.status_code == 200, (call.label, response.status_code, response.text[:400])
                counts.append(len(counter.seen))
    return Cost(call.key, call.label, db, counts, statistics.median(times), runs), response.json()


async def measure_all(engine, factory, world: World, db: str, keys=None) -> tuple[dict[str, Cost], dict[str, Any]]:
    costs: dict[str, Cost] = {}
    bodies: dict[str, Any] = {}
    for call in calls(world):
        if keys is None or call.key in keys:
            costs[call.key], bodies[call.key] = await measure(engine, factory, call, db)
    return costs, bodies


def cost_table(rows: list[Cost]) -> str:
    head = ("Endpoint", "DB", "Statements", "Median ms")
    body = [(r.label, r.db, str(r.statements), f"{r.median_ms:.1f}" + ("" if r.runs == 5 else f" ({r.runs} run)"))
            for r in rows]
    widths = [max(len(line[i]) for line in (head, *body)) for i in range(len(head))]

    def line(cells) -> str:
        return "| " + " | ".join(c.ljust(w) if i < 2 else c.rjust(w)
                                 for i, (c, w) in enumerate(zip(cells, widths, strict=True))) + " |"

    rule = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([line(head), rule, *(line(cells) for cells in body)])


# --- what every run must show --------------------------------------------------------------------------------


def check_population(bodies: dict[str, Any], *, size: int = 230) -> None:
    """The population is the one the docstring describes, read through the same calls that were measured."""
    workspace = bodies["workspace"]
    cards = {card["key"]: card["value"] for card in workspace["cards"]}
    assert cards == {"clients": size, "existing": 66, "net_new": size - 66, "needs_attention": 10,
                     "standard_attached": 0, "client_copies": 11}
    assert (workspace["total"], len(workspace["items"])) == (size, 25)
    attention = bodies["attention"]
    assert attention["total"] == len(attention["items"]) == cards["needs_attention"]
    assert {row["relationship"] for row in attention["items"]} == {"net_new"}
    filtered = bodies["filtered"]
    assert 0 < filtered["total"] < attention["total"] and filtered["total"] == len(filtered["items"])
    assert all(row["needs_attention"] and row["requirement"] == "required" for row in filtered["items"])
    assert (bodies["page_100"]["total"], len(bodies["page_100"]["items"])) == (size, 100)
    panel = bodies["panel"]
    assert (panel["nda"]["state"], panel["nda"]["version_no"], panel["msa"]["state"]) == ("client", 2, "client")
    assert len(panel["nda"]["history"]) == 2
    dry = bodies["dry_run"]
    assert (dry["will_receive"], dry["net_new_included"], dry["existing_included"], dry["already_hold"],
            dry["net_new_untouched"]) == (67, 10, 57, 7, size - 66 - 10)
    assert sorted(t["reason"] for t in dry["targets"] if not t["included"]) == [
        "stage_1_only", "stage_1_only", "stage_1_only", "test_data"]
    assert len(bodies["old_agreements"]["items"]) == 18  # one row per client copy (no standard attached yet)
    assert (len(bodies["old_clients"]["items"]), bodies["old_clients"]["total"]) == (200, size)


def check_after(costs: dict[str, Cost], expected: dict[str, int]) -> None:
    for key in AFTER:
        cost = costs[key]
        assert len(set(cost.counts)) == 1, (key, cost.counts)  # the same work on every run
    for key in WORKSPACE_VIEWS:
        assert costs[key].statements <= 8, (key, costs[key].statements)  # directive B3 / T13
    assert costs["panel"].statements <= 10  # the reader, the shared loader (7) and the history (2)
    assert costs["dry_run"].statements <= 8  # the reader and the shared loader
    assert {key: costs[key].statements for key in AFTER} == expected


# Exact counts (snapshot). One shared loader serves every view, so the four workspace views cost the same.
EXPECTED: dict[str, dict[str, int]] = {
    "SQLite": {"workspace": 8, "attention": 8, "filtered": 8, "page_100": 8, "panel": 10, "dry_run": 8},
    "Postgres": {"workspace": 8, "attention": 8, "filtered": 8, "page_100": 8, "panel": 10, "dry_run": 8},
}


def sqlite_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def test_t13_statements_and_latency_per_call_on_sqlite_before_and_after(env, fk_engine):  # noqa: F811
    factory = sqlite_factory(fk_engine)
    world, _store = await build_world(factory)
    costs, bodies = await measure_all(fk_engine, factory, world, "SQLite")
    print("\nS24-AG1 T13 on SQLite, 230 clients (statements per call; median of 5 runs):\n"
          + cost_table(list(costs.values())))
    check_population(bodies)
    check_after(costs, EXPECTED["SQLite"])

    # 25 more clients (none of them a target): no "after" count moves. The old clients call grows with them.
    await add_clients(factory, world, MORE)
    grown, grown_bodies = await measure_all(fk_engine, factory, world, "SQLite")
    assert world.size == 255 and grown_bodies["workspace"]["total"] == 255
    assert grown_bodies["dry_run"]["will_receive"] == 67
    assert {k: grown[k].statements for k in AFTER} == {k: costs[k].statements for k in AFTER}
    print(f"255 clients: old GET /clients?size=200 {costs['old_clients'].statements} -> "
          f"{grown['old_clients'].statements} statements; every 'after' count unchanged")
