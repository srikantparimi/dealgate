"""S24-AG1 T13 (lane T-B) on PostgreSQL: the same calls on the same population, the 67-client batch, one table.

test_s24_ag1_cost.py builds the realistic population (230 synthetic clients) and measures the calls on SQLite.
This file builds the same population on a fresh migrated scratch database (tests/s24_pg.py) and an in-memory
SQLite database, measures the same calls through the same routers on both (statements per call, median of 5
timed runs), so the two databases compare like with like, and then runs the real batch the dry run proposes:
67 clients, both kinds, as the API runs it.

* POST /agreements/batches answers 202 "within seconds" (directive B7); the job is
  ``agreement_batches.run_batch``, the function the API's launcher and the resume worker run.
* It commits once per chunk of 25 clients, ceil(67/25) = 3 chunk commits, then once to mark the batch done,
  while the browser's poll (GET /agreements/batches/AG-0001) reads 25, 50 and 67.
* The whole run — the 202 and the job — finishes in under 60 seconds (directive T13).
* Afterwards the workspace still costs the same and its cards show the result (nobody needs attention).

Prints ONE table (each call on SQLite and on Postgres, then the batch); run with ``pytest -s`` and copy it into the
report. Skipped without DEALGATE_POSTGRES_URL.
"""

from __future__ import annotations

import math
import time

from sqlalchemy import event, func, select

from app.audit import verify_chain
from app.models.agreements import AgreementBatch, AgreementsSettings
from app.models.client import Agreement, Client
from app.services import agreement_batches
from tests.s24_pg import POSTGRES, scratch_postgres
from tests.test_s24_ag1_beb_client import ADMIN, TODAY, env  # noqa: F401  (env: fixture)
from tests.test_s24_ag1_cost import (
    DRY_RUN,
    EXPECTED,
    Cost,
    StatementCounter,
    build_world,
    check_after,
    check_population,
    cost_table,
    measure_all,
    sqlite_factory,
)
from tests.test_s24_ag1_shared_object_pg import Jobs, api_for, count, real

pytestmark = POSTGRES


async def run_the_67_client_batch(engine, factory) -> tuple[list[Cost], dict]:
    """Start the batch through the route, then run its job while counting the job's commits and statements."""
    jobs = Jobs(factory, "deferred")  # the job runs below, so its commits are counted on their own
    facts: dict = {}
    async with api_for(factory, ADMIN, launcher=jobs) as admin:
        dry = (await admin.post("/agreements/batches", json=DRY_RUN)).json()
        facts["will_receive"] = dry["will_receive"]
        with StatementCounter(engine) as start_counter:
            started = time.perf_counter()
            response = await admin.post("/agreements/batches",
                                        json=real("t13-sixty-seven", f"ATTACH {dry['will_receive']}"))
            accepted = time.perf_counter() - started
        facts["start"] = (response.status_code, response.json())
        facts["launched"] = list(jobs.calls)
        (batch_id, _phase), = jobs.calls

        job_counter = StatementCounter(engine)
        commits: list[int] = []
        polls: list[int] = []

        def on_commit(conn):  # noqa: ARG001
            if job_counter.on:
                commits.append(1)

        async def poll_like_the_browser(_batch_id):
            job_counter.on = False  # the browser's poll is not the job's work
            try:
                polls.append((await admin.get("/agreements/batches/AG-0001")).json()["done_count"])
            finally:
                job_counter.on = True

        event.listen(engine.sync_engine, "commit", on_commit)
        try:
            with job_counter:
                job_started = time.perf_counter()
                facts["final"] = await agreement_batches.run_batch(factory, batch_id, on_chunk=poll_like_the_browser)
                job = time.perf_counter() - job_started
        finally:
            event.remove(engine.sync_engine, "commit", on_commit)
        facts["done"] = (await admin.get("/agreements/batches/AG-0001")).json()
    facts.update(polls=polls, commits=len(commits), accepted=accepted, job=job, total=accepted + job)
    async with factory() as s:
        facts["pairs"] = (await s.execute(select(Agreement.client_id, Agreement.kind))).all()
        facts["uploaders"] = set((await s.scalars(select(Agreement.uploaded_by).where(
            Agreement.batch_id == batch_id))).all())
        facts["cutover"] = (await s.get(AgreementsSettings, 1)).cutover_date
        facts["unstamped"] = await count(s, Client, Client.relationship.is_(None))
        facts["batches"] = await count(s, AgreementBatch)
        facts["chain"] = await verify_chain(s)
        facts["batch_rows"] = int(await s.scalar(select(func.count()).select_from(Agreement).where(
            Agreement.batch_id == batch_id)) or 0)
    rows = [
        Cost("batch_start", "POST /agreements/batches (real, 67 clients) -> 202", "Postgres",
             [len(start_counter.seen)], accepted * 1000.0, runs=1),
        Cost("batch_job", f"batch job: 67 clients, {len(polls)} chunk commits + finish", "Postgres",
             [len(job_counter.seen)], job * 1000.0, runs=1),
    ]
    return rows, facts


async def test_t13_postgres_costs_and_a_67_client_batch_in_under_a_minute(env, fk_engine):  # noqa: F811
    lite_factory = sqlite_factory(fk_engine)
    lite_world, _ = await build_world(lite_factory)
    lite, lite_bodies = await measure_all(fk_engine, lite_factory, lite_world, "SQLite")

    async with scratch_postgres() as (engine, factory):
        world, _store = await build_world(factory)
        pg, bodies = await measure_all(engine, factory, world, "Postgres")
        batch_rows, facts = await run_the_67_client_batch(engine, factory)
        later, later_bodies = await measure_all(engine, factory, world, "Postgres", keys=("workspace",))
    after_batch = later["workspace"]
    after_batch.label = "GET /agreements/workspace (after the batch)"

    rows = [cost for key in pg for cost in (lite[key], pg[key])] + [after_batch, *batch_rows]
    print("\nS24-AG1 T13: statements per call and median of 5 runs, 230 clients; the batch runs once\n"
          + cost_table(rows))

    # Both databases: the population is the documented one, and the counts are the snapshot.
    check_population(lite_bodies)
    check_population(bodies)
    check_after(lite, EXPECTED["SQLite"])
    check_after(pg, EXPECTED["Postgres"])

    # The 67-client real batch.
    assert facts["will_receive"] == 67
    status, started = facts["start"]
    assert (status, started["id"], started["status"], started["target_count"]) == (202, "AG-0001", "running", 67)
    assert facts["accepted"] < 10, facts["accepted"]  # the 202 comes back within seconds (B7)
    assert facts["final"] == "done"
    assert facts["polls"] == [25, 50, 67]  # the browser's progress, one step per committed chunk
    assert len(facts["polls"]) == math.ceil(67 / agreement_batches.CHUNK) == 3
    assert facts["commits"] == len(facts["polls"]) + 1  # one commit per chunk of 25, then the finish
    assert facts["total"] < 60, facts["total"]  # directive T13
    done = facts["done"]
    assert (done["status"], done["done_count"], done["target_count"], done["attached_count"],
            done["attached_clients"], done["skipped_count"]) == ("done", 67, 67, 129, 67, 5)
    assert done["attached_count"] + done["skipped_count"] == 67 * 2
    assert len(facts["pairs"]) == len(set(facts["pairs"])) == 18 + 129  # no duplicate (client, kind)
    assert facts["batch_rows"] == 129 and facts["uploaders"] == {ADMIN.id}
    assert (facts["cutover"], facts["unstamped"], facts["batches"]) == (TODAY, 0, 1)
    assert facts["chain"] is True

    # Afterwards: the same cost, and the cards show the result.
    assert after_batch.statements == EXPECTED["Postgres"]["workspace"] and len(set(after_batch.counts)) == 1
    cards = {card["key"]: card["value"] for card in later_bodies["workspace"]["cards"]}
    assert cards == {"clients": 230, "existing": 66, "net_new": 164, "needs_attention": 0,
                     "standard_attached": 67, "client_copies": 11}
    assert later_bodies["workspace"]["cutover"]["set"] is True
    assert later_bodies["workspace"]["cutover"]["date"] == TODAY.isoformat()
