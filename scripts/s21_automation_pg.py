"""Actual worker and mid-write process-crash proof in an owned private database."""
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from s21_coverage_concurrency_pg import admin_identity, database_identity, require

ROOT = Path(__file__).resolve().parents[1]


async def launch():
    return await asyncio.create_subprocess_exec(sys.executable, "-m", "worker.sourcing_automation",
        cwd=ROOT, env=os.environ.copy(), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)


async def finish(process):
    try:
        output, errors = await asyncio.wait_for(process.communicate(), 60)
        require(process.returncode == 0, f"Worker exited {process.returncode}: {errors.decode()[-2000:]}")
        result = json.loads(output.decode().strip().splitlines()[-1])
        require(result == {"worker": "sourcing_automation", "handled": 1}, f"Unexpected worker result: {result}")
        return result
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()


async def proof(url, name):
    from app.audit import verify_chain
    from app.db import engine as application_engine
    from app.models.automation import AutomationJob
    from app.models.people_demand import DemandPublicationVersion
    from app.models.people_sourcing import SourcingDraftVersion
    from app.services.forecast_plans import save_plan
    from tests.test_s21_automation_jobs import enabled

    engine = create_async_engine(url, pool_size=3, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    process = None
    try:
        async with sessions() as session:
            identity = (await session.execute(text("SELECT current_database(), current_user"))).one()
            require(tuple(identity) == (name, "s21"), "Wrong worker proof database")
            actor, request, source, _, _ = await enabled(session)
            source_id, source_version = source.plan_id, source.id
        initial = await finish(await launch())
        async with sessions() as session:
            first = await session.scalar(select(SourcingDraftVersion))
            require(first.snapshot["complete"] is True, "Initial sourcing incomplete")
            november = [row for row in first.snapshot["rows"] if row["start"] == "2026-11-01"]
            require({row["location"]: (row["quantity"], row["sourcing_by"]) for row in november}
                == {"US": (2, "2026-09-17"), "India": (5, "2026-10-02")}, "Independent sourcing dates/headcount mismatch")
            await save_plan(session, actor=actor, plan_id=source_id, body=request.model_copy(update={
                "expected_version_id": source_version, "probability": "0.40"}))

        # Block an actual INSERT after the worker has written publication and draft.
        # This trigger exists only in the newly generated disposable database.
        lock_key = uuid.uuid4().int % (2 ** 62)
        async with sessions() as holder, sessions() as observer:
            await holder.execute(text(f"CREATE FUNCTION s21_pause_draft() RETURNS trigger LANGUAGE plpgsql AS $$ "
                f"BEGIN PERFORM pg_advisory_xact_lock({lock_key}); RETURN NEW; END $$"))
            await holder.execute(text("CREATE TRIGGER s21_pause_draft AFTER INSERT ON sourcing_draft_version "
                "FOR EACH ROW EXECUTE FUNCTION s21_pause_draft()"))
            await holder.commit()
            blocker = await holder.scalar(text("SELECT pg_backend_pid()"))
            await holder.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
            process = await launch()
            deadline = asyncio.get_running_loop().time() + 30
            observed = None
            while asyncio.get_running_loop().time() < deadline:
                require(process.returncode is None, "Worker exited before crash boundary")
                row = (await observer.execute(text("""
                    SELECT a.pid, a.wait_event_type, a.query, pg_blocking_pids(a.pid) AS blockers,
                        EXISTS(SELECT 1 FROM pg_locks l WHERE l.pid=a.pid AND NOT l.granted
                            AND l.locktype='advisory') AS waiting
                    FROM pg_stat_activity a WHERE a.datname=:database AND a.application_name=:name
                """), {"database": name, "name": f"sourcing_automation:{process.pid}"})).mappings().one_or_none()
                await observer.rollback()
                if row and row["waiting"] and row["wait_event_type"] == "Lock" and blocker in row["blockers"]:
                    require("INSERT INTO sourcing_draft_version" in row["query"], "Wrong crash boundary statement")
                    observed = {"worker_os_pid": process.pid, "blocked_backend": row["pid"], "blocker": blocker}
                    break
                await asyncio.sleep(0.05)
            require(observed is not None, "Actual mid-draft lock was not observed")
            process.terminate()
            await asyncio.wait_for(process.communicate(), 15)
            require(process.returncode == -15, "Expected the owned worker SIGTERM")
            await holder.rollback()
            await holder.execute(text("DROP TRIGGER s21_pause_draft ON sourcing_draft_version"))
            await holder.execute(text("DROP FUNCTION s21_pause_draft()"))
            await holder.commit()
        async with sessions() as session:
            require(await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 1,
                "Killed worker committed a partial draft")
            require(await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 1,
                "Killed worker committed a partial publication")
            pending = await session.scalar(select(AutomationJob).where(AutomationJob.status == "pending"))
            require(pending is not None and pending.attempts == 0, "Crash did not roll back job claim")
        recovered = await finish(await launch())
        async with sessions() as session:
            rows = (await session.scalars(select(SourcingDraftVersion).order_by(SourcingDraftVersion.revision))).all()
            require([row.revision for row in rows] == [1, 2], "Duplicate or missing draft after recovery")
            require([row.snapshot["probability"] for row in rows] == ["0.70", "0.40"], "Probability history changed")
            require(all(sum(line["quantity"] for line in row.snapshot["rows"] if line["start"] == "2026-11-01") == 7
                for row in rows), "Probability weighted headcount")
            require(await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 2,
                "Duplicate publication after recovery")
            require(await verify_chain(session), "Audit chain invalid after crash/recovery")
        return {"initial_worker": initial, "crash_before_release": observed, "recovered_worker": recovered,
            "publications": 2, "draft_revisions": [1, 2], "headcount": 7, "audit_chain": "valid"}
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.communicate()
        await engine.dispose()
        await application_engine.dispose()


def main():
    require(len(sys.argv) == 1, "No supplied database names or arguments")
    require(not any(key == "app" or key.startswith("app.") for key in sys.modules), "Run standalone before app imports")
    raw = os.environ.get("S21_AUTOMATION_ADMIN_URL")
    require(raw is not None, "Set S21_AUTOMATION_ADMIN_URL explicitly")
    admin_url = make_url(raw)
    require((admin_url.drivername, admin_url.username, admin_url.host, admin_url.port, admin_url.database)
        == ("postgresql+psycopg", "s21", "127.0.0.1", 55421, "postgres") and not admin_url.query,
        "Only owned local s21 PostgreSQL administrative connection is permitted")
    for key in list(os.environ):
        if key.startswith("PG"):
            os.environ.pop(key)
    name, marker = "s21_automation_" + uuid.uuid4().hex, "owned-s21-automation:" + uuid.uuid4().hex
    url = admin_url.set(drivername="postgresql+asyncpg", database=name)
    dsn = url.render_as_string(hide_password=False)
    os.environ.update(POSTGRES_URL=dsn, DATABASE_URL=dsn, DEALGATE_POSTGRES_URL=dsn,
        DEALGATE_ENV="local", DEALGATE_TENANT_ID="independent-company-x-demand",
        DEALGATE_REPORTING_TIMEZONE="America/Los_Angeles", DEALGATE_REPORTING_CURRENCY="USD",
        PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=os.pathsep.join((str(ROOT / "api"), str(ROOT))))
    sys.path[:0] = [str(ROOT / "api"), str(ROOT)]
    with psycopg.connect(admin_url.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True, connect_timeout=5, options="-c statement_timeout=15000 -c lock_timeout=5000") as admin:
        admin_identity(admin)
        created, identity = False, None
        try:
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER s21 TEMPLATE template0").format(sql.Identifier(name)))
            created = True
            admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(marker)))
            identity = database_identity(admin, name)
            require(identity and identity[1:] == ("s21", marker), "Private ownership check failed")
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "api",
                env=os.environ.copy(), check=True, timeout=300)
            evidence = asyncio.run(asyncio.wait_for(proof(url, name), 180))
        finally:
            if created:
                admin_identity(admin)
                require(re.fullmatch(r"s21_automation_[0-9a-f]{32}", name) and identity is not None
                    and database_identity(admin, name) == identity, "Cleanup ownership mismatch; leave private DB intact")
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
                require(database_identity(admin, name) is None, "Cleanup not confirmed")
                print(json.dumps({"private_database": name, "cleanup": "confirmed"}), flush=True)
    print(json.dumps({"result": "PASS", **evidence}, indent=2))


if __name__ == "__main__":
    main()
