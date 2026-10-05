"""Add exactly50 dismissed owned plans for real source-pagination controls."""
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from s21_five_views_fixture import ROOT, SUPPORTED_REVISION, component, no_owned_worker


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def configuration():
    require(len(sys.argv) == 1 and os.environ.get("DEALGATE_ENV") == "local", "Explicit local invocation required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    source = json.loads(Path(os.environ["S21_VIEWS_COVERAGE_MANIFEST"]).read_text())
    output = Path(os.environ["S21_VIEWS_PAGING_MANIFEST"])
    require(output.parent.resolve() == Path("/tmp").resolve() and not output.exists() and not output.is_symlink(),
            "Fresh exclusive /tmp paging receipt required")
    url = make_url(os.environ["S21_COVERAGE_DATABASE_URL"])
    require((url.drivername, url.username, url.host, url.port) == ("postgresql+asyncpg", "s21", "127.0.0.1", 55421)
            and not url.query and not url.password, "Literal local private target required")
    require(re.fullmatch(r"s21_cov_37eb[0-9a-f]{28}", url.database or ""), "Only authorized37eb clone allowed")
    require(url.database == source["database"] == source["tenant"] == os.environ.get("DEALGATE_TENANT_ID"),
            "Manifest/database/tenant mismatch")
    os.environ.update(POSTGRES_URL=str(url), DATABASE_URL=str(url), PYTHONDONTWRITEBYTECODE="1", AWS_EC2_METADATA_DISABLED="true")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url, source, output


async def seed(url, source, output):
    from app.services.test_fixtures import account_scope

    inputs = component("a")  # Includes full real calculation and literal cost/revenue preflight.
    run_id = str(uuid.uuid4())
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{source['actor_email']}")
    require(str(actor_id) == source["actor_id"], "Actor must match the original fixture identity")
    record = dict(database=url.database, tenant=url.database, actor_email=source["actor_email"],
        run_id=run_id, account_id=source["account_id"], mirror_plan_id=source["plan_id"],
        status="intent", operations=[], plans=[], workers=[], expected_total=51,
        expected_dismissed=50, expected_page1_count=50, expected_page2_count=1)
    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {"application_name": "s21-five-views-paging"}})
    try:
        async with engine.connect() as connection:
            identity = (await connection.execute(text("SELECT current_database(), current_user, pg_get_userbyid(datdba), "
                "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))).one()
            require(tuple(identity) == (url.database, "s21", "s21", f"owned-s21-t21:{url.database.removeprefix('s21_cov_')}"), "Database ownership mismatch")
            heads = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            require(heads == [SUPPORTED_REVISION], "Exact supported schema required")
        async with AsyncSession(engine) as session:
            scope = await account_scope(session, uuid.UUID(source["account_id"]), opportunity_id=uuid.UUID(source["opportunity_id"]))
            require(scope is not None and actor_id in scope, "AccountC is not this actor's valid trusted fixture")
        no_owned_worker()
        with output.open("x") as receipt:
            def checkpoint():
                receipt.seek(0)
                json.dump(record, receipt, sort_keys=True, indent=2)
                receipt.truncate()
                receipt.flush()
                os.fsync(receipt.fileno())
            checkpoint()
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8210", timeout=45, trust_env=False,
                                         headers={"X-Test-User": source["actor_email"]}) as client:
                async def population():
                    first = await client.get("/forecast/plans", params={"account_id": source["account_id"], "size": 200})
                    require(first.status_code == 200, "Owned plan population unavailable")
                    return first.json()

                try:
                    before = await population()
                    require(before["total"] == 1 and len(before["items"]) == 1 and before["items"][0]["id"] == source["plan_id"],
                            "AccountC must contain exactly its existing mirror; refusing duplicate or partial seed")
                    record["mirror_before"] = before["items"][0]
                    checkpoint()
                    for number in range(1, 51):
                        title = f"Fixture-only dismissed page{number:02d} {run_id}"
                        body = dict(account_id=source["account_id"], opportunity_id=source["opportunity_id"], title=title,
                            idempotency_key=str(uuid.uuid5(uuid.UUID(run_id), f"dismissed-page-{number:02d}")),
                            inputs=inputs, probability="0.50", probability_source="Explicit synthetic fixture assumption",
                            assumptions=["Fixture-only dismissed source for actual pagination controls"], lifecycle="dismissed",
                            change_reason="Dedicated accountC paging proof; excludes this source from every scenario")
                        operation = dict(path="/forecast/plans", body=body, status="intent")
                        record["operations"].append(operation)
                        checkpoint()
                        response = await client.post("/forecast/plans", json=body)
                        operation.update(status=response.status_code, response=response.json())
                        checkpoint()
                        require(response.status_code == 201, f"Plan{number} creation failed; preserve receipts")
                        record["plans"].append({**response.json(), "title": title})
                        checkpoint()
                    owned = {plan["id"] for plan in record["plans"]}
                    for attempt in range(1, 5):
                        current = await population()
                        owned_rows = [row for row in current["items"] if row["id"] in owned]
                        require(len(owned_rows) == 50 and current["total"] == 51, "Owned population changed unexpectedly")
                        if all(row["job"] and row["job"]["status"] == "done" for row in owned_rows):
                            break
                        require(all(row["job"] and row["job"]["status"] == "pending" or
                                    row["job"] and row["job"]["status"] == "done" for row in owned_rows),
                                "An owned job failed; do not retry calculation failures")
                        no_owned_worker()
                        worker = await asyncio.create_subprocess_exec(sys.executable, "-m", "worker.forecast_plans", cwd=ROOT,
                            env={**os.environ, "PYTHONPATH": str(ROOT / "api"), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        run = dict(number=attempt, pid=worker.pid, status="running")
                        record["workers"].append(run)
                        checkpoint()
                        try:
                            stdout, stderr = await asyncio.wait_for(worker.communicate(), timeout=120)
                        except asyncio.TimeoutError:
                            worker.terminate()
                            stdout, stderr = await worker.communicate()
                            run.update(status="timed_out", exit_code=worker.returncode, stdout=stdout.decode(), stderr=stderr.decode())
                            checkpoint()
                            raise RuntimeError("Owned child timed out and was collected")
                        run.update(status="finished", exit_code=worker.returncode, stdout=stdout.decode(), stderr=stderr.decode())
                        checkpoint()
                        require(worker.returncode == 0, "Worker failed; preserve results without retry")
                    final = await population()
                    own_final = [row for row in final["items"] if row["id"] in owned]
                    require(len(own_final) == 50 and all(row["lifecycle"] == "dismissed" and row["job"]["status"] == "done"
                                                      for row in own_final), "Owned50 did not finish within bounded drain")
                    mirror = next(row for row in final["items"] if row["id"] == source["plan_id"])
                    require(mirror["version_id"] == record["mirror_before"]["version_id"], "Existing mirror version changed")
                    require(final["total"] == 51, "Final source count must be51")
                    record.update(status="ready_for_pagination_browser", observed_total=final["total"])
                except Exception as error:
                    record.update(status="failed_preserved", error=f"{type(error).__name__}: {error}")
                    checkpoint()
                    raise
                checkpoint()
        print(json.dumps({"manifest": str(output), "status": record["status"]}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed(*configuration()))
