"""Lead-run, private-database proof of real coverage locks and rejected races.

Requires S21_COVERAGE_ADMIN_URL=postgresql+psycopg://s21@127.0.0.1:55421/postgres.
Never accepts an existing target database or a database name to delete.
"""
import asyncio
import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


ROOT = Path(__file__).resolve().parents[1]
AUDIT_ACTION = "people.staffing_coverage_revised"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def admin_identity(connection):
    identity = connection.execute(
        "SELECT current_database(), current_user, session_user").fetchone()
    require(identity == ("postgres", "s21", "s21"), "Unexpected administrative identity")


def database_identity(connection, name):
    return connection.execute("""
        SELECT oid, pg_get_userbyid(datdba), shobj_description(oid, 'pg_database')
        FROM pg_database WHERE datname = %s
    """, (name,)).fetchone()


async def identify(session, database, label):
    await session.execute(text("SELECT set_config('application_name', :name, false)"), {"name": label})
    row = (await session.execute(text(
        "SELECT current_database(), current_user, session_user, pg_backend_pid()"))).one()
    require(tuple(row[:3]) == (database, "s21", "s21"), "Unexpected proof connection target")
    return row[3]


async def observe_lock(observer, *, database, blocked_pid, blocker_pid, label, table, task):
    deadline = asyncio.get_running_loop().time() + 20
    while asyncio.get_running_loop().time() < deadline:
        require(not task.done(), "Contender completed before its source-row lock was observed")
        row = (await observer.execute(text("""
            SELECT a.application_name, a.wait_event_type, a.wait_event,
                   pg_blocking_pids(a.pid) AS blockers, a.query,
                   ARRAY(SELECT locktype FROM pg_locks WHERE pid = a.pid AND NOT granted) AS waiting
            FROM pg_stat_activity a WHERE a.pid = :pid AND a.datname = :database
        """), {"pid": blocked_pid, "database": database})).mappings().one_or_none()
        # End the observer transaction so the next pg_stat_activity sample is fresh.
        await observer.rollback()
        if (row and row["application_name"] == label and row["wait_event_type"] == "Lock"
                and blocker_pid in row["blockers"] and row["waiting"]
                and table in row["query"] and "FOR UPDATE" in row["query"]):
            evidence = dict(blocked_pid=blocked_pid, blocker_pid=blocker_pid,
                application_name=label, wait_event=row["wait_event"],
                ungranted_lock_types=list(row["waiting"]), source_table=table)
            print(json.dumps({"observed_before_release": evidence}), flush=True)
            return evidence
        await asyncio.sleep(0.05)
    raise AssertionError(f"No exact contender/blocker source lock observed within 20s: {label}")


async def race(sessions, database, *, actor, source_model, source_id, winner_body,
               loser_body, expected_status, name):
    from fastapi import HTTPException
    from app.services.people_coverage import save_coverage

    async with sessions() as winner, sessions() as loser, sessions() as observer:
        winner_pid = await identify(winner, database, name + "-winner")
        loser_label = name + "-contender"
        loser_pid = await identify(loser, database, loser_label)
        observer_pid = await identify(observer, database, name + "-observer")
        require(len({winner_pid, loser_pid, observer_pid}) == 3, "Race needs three separate backends")
        require(await winner.scalar(select(source_model).where(source_model.id == source_id)
            .with_for_update()) is not None, "Missing source row to lock")

        async def contender():
            try:
                return 201, await save_coverage(loser, actor=actor, body=loser_body)
            except HTTPException as error:
                await loser.rollback()
                return error.status_code, error.detail

        task = asyncio.create_task(contender())
        try:
            wait = await observe_lock(observer, database=database, blocked_pid=loser_pid,
                blocker_pid=winner_pid, label=loser_label, table=source_model.__tablename__, task=task)
            accepted = await asyncio.wait_for(save_coverage(winner, actor=actor, body=winner_body), 20)
            status, detail = await asyncio.wait_for(task, 20)
            require(status == expected_status, f"{name}: expected {expected_status}, got {status}: {detail}")
            if expected_status == 422:
                require("overlap" in detail, "Cross-root rejection must identify overlapping reuse")
            else:
                require("coverage changed" in detail, "CAS rejection must identify stale coverage")
            return accepted, dict(name=name, accepted=1, rejected=1, rejection_status=status, lock=wait)
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await winner.rollback()
            await loser.rollback()


async def history(sessions, *, root_id, requests, latest, absent_request):
    from app.audit import verify_chain
    from app.models.audit import AuditEvent
    from app.models.people_coverage import DemandCoverageRoot, DemandCoverageVersion

    async with sessions() as session:
        roots = list((await session.scalars(select(DemandCoverageRoot))).all())
        versions = list((await session.scalars(select(DemandCoverageVersion)
            .order_by(DemandCoverageVersion.revision))).all())
        audits = list((await session.scalars(select(AuditEvent)
            .where(AuditEvent.action == AUDIT_ACTION).order_by(AuditEvent.ts, AuditEvent.id))).all())
        count = len(requests)
        require(len(roots) == 1 and str(roots[0].id) == root_id, "Duplicate or unexpected coverage root")
        require([v.revision for v in versions] == list(range(1, count + 1)), "Lost or duplicate revision")
        require(all(str(v.root_id) == root_id for v in versions), "Unexpected cross-root version")
        require([v.request_key for v in versions] == requests, "Rejected request persisted or history mutated")
        require(len({v.id for v in versions}) == count, "Duplicate version identity")
        require(str(versions[-1].id) == latest["version_id"], "Latest persisted version is not winner")
        require(versions[-1].mappings == latest["mappings"], "Persisted mapping differs from winner")
        require(len(audits) == count, "Accepted version and audit counts differ")
        require([a.correlation_id for a in audits] == requests, "Missing, duplicate or rejected audit")
        require(all(a.entity == "demand_coverage" and a.entity_id == root_id for a in audits),
            "Audit linked to incorrect root")
        require([a.after["version_id"] for a in audits] == [str(v.id) for v in versions],
            "Audits do not identify immutable versions")
        require([a.after["revision"] for a in audits] == list(range(1, count + 1)), "Incorrect audit revisions")
        require(await session.scalar(select(AuditEvent.id).where(
            AuditEvent.correlation_id == absent_request)) is None, "Rejected writer left an audit")
        require(await verify_chain(session), "Audit hash chain failed")
        return dict(roots=1, versions=count, audits=count, revisions=[v.revision for v in versions])


async def proof(private_url, database):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pytest import MonkeyPatch
    from app.db import engine as application_engine
    from app.models.forecast import ForecastPlan, ForecastPlanVersion
    from app.models.people_demand import DemandPublication
    from app.models.project import Project
    from app.services.forecast_plans import save_plan
    from app.services.people_coverage import save_coverage
    from app.services.people_demand import publish_plan_demand
    from tests import test_s21_coverage_service as fixtures
    from tests.test_s21_demand_publication import publication
    from tests.test_s21_forecast_plans import body

    engine = create_async_engine(private_url, pool_size=4, max_overflow=0,
        connect_args={"server_settings": {"statement_timeout": "30000", "lock_timeout": "30000"}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        with MonkeyPatch.context() as environment:
            environment.setenv("DEALGATE_REPORTING_TIMEZONE", "America/Los_Angeles")
            environment.setenv("DEALGATE_REPORTING_CURRENCY", "USD")
            async with sessions() as seed:
                await identify(seed, database, "s21-coverage-seed")
                migrated = list((await seed.scalars(text("SELECT version_num FROM alembic_version"))).all())
                config = Config(str(ROOT / "api/alembic.ini"))
                config.set_main_option("script_location", str(ROOT / "api/alembic"))
                heads = ScriptDirectory.from_config(config).get_heads()
                require(len(heads) == 1 and migrated == heads, "Private schema is not the actual Alembic head")
                canonical = await fixtures.canonical.__wrapped__(seed, environment)
                pair = await fixtures.pair.__wrapped__(seed, canonical)
                actor, _, project_publication, plan_version, enrichment = pair
                project_id = (await seed.get(DemandPublication,
                    uuid.UUID(project_publication["publication_id"]))).project_id
                second_plan = body(canonical[1].client_id)
                second_plan.inputs = (await seed.get(ForecastPlanVersion, plan_version.id)).component_inputs
                second_version = await save_plan(seed, actor=actor, body=second_plan)
                second_publication = await publish_plan_demand(seed, actor=actor,
                    body=publication(second_version, enrichments=enrichment))
                other = (actor, second_publication, project_publication, second_version, enrichment)
                initial_body = fixtures.coverage(pair)
                initial = await save_coverage(seed, actor=actor, body=initial_body)

            def one_slot(which, expected):
                request = fixtures.coverage(which, expected_mapping_version_id=expected)
                mapping = request.model_dump(mode="json")["mappings"][0]
                mapping.update(plan_slots=[0], project_slots=[0])
                return fixtures.coverage(which, expected_mapping_version_id=expected, mappings=[mapping])

            first_body = one_slot(pair, initial["version_id"])
            stale_body = one_slot(pair, initial["version_id"])
            first, cas = await race(sessions, database, actor=actor, source_model=ForecastPlan,
                source_id=plan_version.plan_id, winner_body=first_body, loser_body=stale_body,
                expected_status=409, name="s21-coverage-cas")
            requests = [initial_body.request_key, first_body.request_key]
            cas["history"] = await history(sessions, root_id=initial["id"], requests=requests,
                latest=first, absent_request=stale_body.request_key)
            require(first["revision"] == 2, "CAS winner must append exactly revision 2")

            async with sessions() as session:
                clear_body = fixtures.coverage(pair, expected_mapping_version_id=first["version_id"], mappings=[])
                cleared = await save_coverage(session, actor=actor, body=clear_body)
            require(cleared["revision"] == 3 and cleared["mappings"] == [], "Explicit clear must append revision 3")
            winner_body = one_slot(pair, cleared["version_id"])
            overlap_body = one_slot(other, None)
            final, overlap = await race(sessions, database, actor=actor, source_model=Project,
                source_id=project_id, winner_body=winner_body, loser_body=overlap_body,
                expected_status=422, name="s21-coverage-crossroot")
            requests += [clear_body.request_key, winner_body.request_key]
            overlap["history"] = await history(sessions, root_id=initial["id"], requests=requests,
                latest=final, absent_request=overlap_body.request_key)
            require(final["revision"] == 4, "Cross-root winner must append exactly revision 4")
            require(len(final["mappings"]) == 1 and final["mappings"][0]["plan_slots"] == [0]
                and final["mappings"][0]["project_slots"] == [0], "Final coverage must consume one slot once")
            return dict(migration_head=migrated[0], scenarios=[cas, overlap])
    finally:
        await engine.dispose()
        await application_engine.dispose()


def main():
    require(len(sys.argv) == 1, "No arguments or externally supplied target/drop names accepted")
    require(not any(name == "app" or name.startswith("app.") for name in sys.modules),
        "Run as a standalone process before importing application configuration")
    raw = os.environ.get("S21_COVERAGE_ADMIN_URL")
    require(raw is not None, "Set the explicit S21_COVERAGE_ADMIN_URL administrative DSN")
    admin_url = make_url(raw)
    require((admin_url.drivername, admin_url.username, admin_url.host, admin_url.port, admin_url.database)
        == ("postgresql+psycopg", "s21", "127.0.0.1", 55421, "postgres") and not admin_url.query,
        "Refusing: require psycopg, s21, literal 127.0.0.1:55421/postgres and no URL query options")
    # libpq environment overrides (notably PGHOSTADDR/PGSERVICE/PGOPTIONS) must not redirect the DSN.
    for key in list(os.environ):
        if key.startswith("PG"):
            os.environ.pop(key)
    name = "s21_coverage_lock_" + uuid.uuid4().hex
    marker = "owned-by-s21-coverage-proof:" + uuid.uuid4().hex
    private_url = admin_url.set(drivername="postgresql+asyncpg", database=name)
    private_dsn = private_url.render_as_string(hide_password=False)
    os.environ.update(POSTGRES_URL=private_dsn, DATABASE_URL=private_dsn,
        DEALGATE_POSTGRES_URL=private_dsn, PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=os.pathsep.join((str(ROOT / "api"), str(ROOT))))
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT / "api"), str(ROOT)]
    print(json.dumps({"private_database": name, "state": "creating"}), flush=True)
    with psycopg.connect(admin_url.set(drivername="postgresql").render_as_string(hide_password=False),
            autocommit=True, connect_timeout=5, application_name="s21-coverage-admin",
            options="-c statement_timeout=15000 -c lock_timeout=5000") as admin:
        admin_identity(admin)
        created, identity = False, None
        try:
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(name), sql.Identifier("s21")))
            created = True
            admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(marker)))
            identity = database_identity(admin, name)
            require(identity and identity[1:] == ("s21", marker), "Private database ownership verification failed")
            subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
                cwd=ROOT / "api", env=os.environ.copy(), check=True, timeout=300)
            evidence = asyncio.run(asyncio.wait_for(proof(private_url, name), timeout=180))
            evidence["source_revision"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        finally:
            if created:
                admin_identity(admin)
                require(re.fullmatch(r"s21_coverage_lock_[0-9a-f]{32}", name) is not None
                    and identity is not None and database_identity(admin, name) == identity,
                    f"Cleanup refused: ownership/OID/marker changed; private database left intact: {name}")
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
                require(database_identity(admin, name) is None, "Private database cleanup not confirmed")
                print(json.dumps({"private_database": name, "cleanup": "confirmed"}), flush=True)
    print(json.dumps({"result": "PASS", "private_database": name, **evidence}, indent=2), flush=True)


if __name__ == "__main__":
    main()
