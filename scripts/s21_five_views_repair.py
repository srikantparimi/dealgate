"""Immutable API repair of the two owned five-view plans; preserve original receipts."""
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import sys
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from s21_five_views_fixture import ROOT, SUPPORTED_REVISION, no_owned_worker


def require(value, message):
    if not value:
        raise RuntimeError(message)


def configuration():
    require(len(sys.argv) == 1 and os.environ.get("DEALGATE_ENV") == "local", "Standalone local invocation required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    original = Path(os.environ["S21_VIEWS_MANIFEST"])
    manifest = json.loads(original.read_text())
    output = Path(os.environ["S21_VIEWS_REPAIR_RECEIPT"])
    require(output.parent.resolve() == Path("/tmp").resolve() and not output.exists() and not output.is_symlink(),
            "Fresh exclusive /tmp repair receipt required")
    require(output.resolve() != original.resolve(), "Never replace original manifest")
    url = make_url(os.environ["S21_COVERAGE_DATABASE_URL"])
    require((url.drivername, url.username, url.host, url.port) == ("postgresql+asyncpg", "s21", "127.0.0.1", 55421)
            and not url.query and not url.password, "Literal private local target required")
    require(re.fullmatch(r"s21_cov_37eb[0-9a-f]{28}", url.database or ""), "Only authorized37eb clone allowed")
    require(url.database == manifest["database"] == manifest["tenant"] == os.environ.get("DEALGATE_TENANT_ID"),
            "Manifest/database/tenant mismatch")
    require(manifest["plan_a_id"] == "99924d26-7720-47a4-aec8-563a6a237232" and
            manifest["plan_b_id"] == "119d4c31-e97c-442e-960a-62d0d9620357", "Unexpected plan identities")
    os.environ.update(POSTGRES_URL=str(url), DATABASE_URL=str(url), PYTHONDONTWRITEBYTECODE="1", AWS_EC2_METADATA_DISABLED="true")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url, manifest, output


async def repair(url, manifest, output):
    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {"application_name": "s21-five-views-repair"}})
    record = dict(database=url.database, original_run_id=manifest["run_id"], status="intent", operations=[])
    try:
        async with engine.connect() as connection:
            identity = (await connection.execute(text("SELECT current_database(), current_user, pg_get_userbyid(datdba), "
                "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))).one()
            require(tuple(identity) == (url.database, "s21", "s21", f"owned-s21-t21:{url.database.removeprefix('s21_cov_')}"),
                    "Ownership marker mismatch")
            heads = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            require(heads == [SUPPORTED_REVISION], "Exact supported schema required")
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
                                         headers={"X-Test-User": manifest["actor_email"]}) as client:
                try:
                    for letter in ("a", "b"):
                        plan_id = manifest[f"plan_{letter}_id"]
                        response = await client.get("/forecast/plans", params={"account_id": manifest[f"account_{letter}_id"]})
                        require(response.status_code == 200, "Cannot inspect owned plan")
                        current = next(row for row in response.json()["items"] if row["id"] == plan_id)
                        require(current["version_id"] == manifest[f"plan_{letter}_version_id"],
                                "Source version changed; review preserved receipts instead of overwriting")
                        creations = [item["body"] for item in manifest["operations"] if item["path"] == "/forecast/plans"
                                     and item["body"]["title"] == manifest[f"plan_{letter}_title"]]
                        require(len(creations) == 1, "Original plan request receipt missing/ambiguous")
                        body = copy.deepcopy(creations[0])
                        body["expected_version_id"] = current["version_id"]
                        body["idempotency_key"] = str(uuid.uuid5(uuid.UUID(manifest["run_id"]), f"staffing-cost-repair-v1:{letter}"))
                        body["change_reason"] = "Explicit hourly staffing cost1; existing monthly100/40 is separate overhead"
                        require(len(body["inputs"]["staffing"]) == 1, "Unexpected original staffing scope")
                        body["inputs"]["staffing"][0].update(cost_rate="1", cost_version="synthetic-hourly-cost-v1")
                        body["inputs"]["cost_basis"] = "Explicit monthly overhead plus separately confirmed hourly staffing cost"
                        from app.gm.commercial import calculate_component
                        from app.services.commercial_models import parse_component
                        calculated = calculate_component(parse_component(body["inputs"]))
                        require(calculated.status == "ok" and not calculated.missing,
                                "Repaired immutable source economics remain incomplete")
                        path = f"/forecast/plans/{plan_id}/versions"
                        operation = dict(path=path, body=body, status="intent")
                        record["operations"].append(operation)
                        checkpoint()
                        revised = await client.post(path, json=body)
                        operation.update(http_status=revised.status_code, response=revised.json(), status="response")
                        checkpoint()
                        require(revised.status_code == 201, f"Immutable revision refused: {revised.text}")
                        record[f"plan_{letter}_version_id"] = revised.json()["version_id"]
                        checkpoint()
                    no_owned_worker()
                    worker = await asyncio.create_subprocess_exec(sys.executable, "-m", "worker.forecast_plans", cwd=ROOT,
                        env={**os.environ, "PYTHONPATH": str(ROOT / "api"), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    record["worker"] = {"pid": worker.pid, "status": "running"}
                    checkpoint()
                    try:
                        stdout, stderr = await asyncio.wait_for(worker.communicate(), timeout=120)
                    except asyncio.TimeoutError:
                        worker.terminate()
                        stdout, stderr = await worker.communicate()
                        record["worker"].update(status="timed_out", stdout=stdout.decode(), stderr=stderr.decode(), exit_code=worker.returncode)
                        checkpoint()
                        raise RuntimeError("Owned worker timeout; child collected")
                    record["worker"].update(status="finished", stdout=stdout.decode(), stderr=stderr.decode(), exit_code=worker.returncode)
                    checkpoint()
                    require(worker.returncode == 0, "Forecast worker failed")
                    check = await client.get("/forecast/outlook", params={"as_of": manifest["as_of"], "future_quarters": 2})
                    require(check.status_code == 200, "Outlook unavailable")
                    from decimal import Decimal
                    require(Decimal(check.json()["future"]["revenue"]) == Decimal("360"), "Literal future360 oracle failed")
                    owned_ids = {manifest["plan_a_id"], manifest["plan_b_id"]}
                    require(not any(row.get("source_id") in owned_ids for row in check.json()["excluded"]), "Owned source remains excluded")
                    record.update(status="repaired", expected_future_revenue="360", observed_future_revenue=check.json()["future"]["revenue"])
                except Exception as error:
                    record.update(status="failed_preserved", error=f"{type(error).__name__}: {error}")
                    checkpoint()
                    raise
                checkpoint()
        print(json.dumps({"receipt": str(output), "status": record["status"]}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(repair(*configuration()))
