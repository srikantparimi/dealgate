"""Guarded local API fixtures and a separate real Forecast worker; no cloud calls."""
import asyncio
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_REVISION = "20261003_0062_actual_coverage"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def configuration():
    require(len(sys.argv) == 1 and os.environ.get("DEALGATE_ENV") == "local", "Standalone explicit local invocation required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    source = json.loads(Path(os.environ["S21_COV_MANIFEST"]).read_text())
    output = Path(os.environ["S21_VIEWS_MANIFEST"])
    require(output.parent.resolve() == Path("/tmp").resolve() and not output.exists() and not output.is_symlink(),
            "A new exclusive /tmp manifest path is required; never overwrite receipts")
    raw = os.environ["S21_COVERAGE_DATABASE_URL"]
    url = make_url(raw)
    require((url.drivername, url.username, url.host, url.port) == ("postgresql+asyncpg", "s21", "127.0.0.1", 55421)
            and not url.query and not url.password, "Require literal local trust-only target")
    require(re.fullmatch(r"s21_cov_37eb[0-9a-f]{28}", url.database or ""), "Only the authorized37eb private clone is allowed")
    require(source["database"] == source["tenant"] == url.database == os.environ.get("DEALGATE_TENANT_ID"),
            "Manifest/database/tenant mismatch")
    require(os.environ.get("DEALGATE_REPORTING_CURRENCY") == "USD", "Explicit USD reporting required")
    require(os.environ.get("DEALGATE_REPORTING_TIMEZONE"), "Explicit reporting timezone required")
    actor = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{source['actor_email']}")
    require(str(actor) == source["actor_id"], "Actor identity mismatch")
    require(source["month"] == "2026-10-01", "Oracle requires the existing October signed fixture")
    os.environ.update(POSTGRES_URL=raw, DATABASE_URL=raw, AWS_EC2_METADATA_DISABLED="true", PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url, source, output


def component(letter):
    from app.gm.calendar import DayHours, StaffingAssignment, WorkCalendar
    from app.gm.commercial import FeeAllocation, FixedFee, PeriodCost, PricingComponent, calculate_component
    from app.services.commercial_models import COMPONENT
    months = [date(2027, month, 1) for month in ((1, 2, 3) if letter == "a" else (4, 5, 6))]
    start, end = months[0], date(2027, 3, 31) if letter == "a" else date(2027, 6, 30)
    identity, zone = f"five-views-{letter}", "America/New_York"
    calendar = WorkCalendar(identity, "1", zone, start, end,
        (DayHours(Decimal(8), Decimal(8), Decimal(8)),) * 5 + (DayHours(Decimal(0), Decimal(0), Decimal(0)),) * 2)
    staffing = StaffingAssignment("engineer", identity, "1", identity, "1", "synthetic-policy", "Engineer",
        "US", zone, "USD", 1, Decimal(1), calendar, None, Decimal("1"), None,
        "synthetic-hourly-cost-v1", start, end)
    value = PricingComponent(component_id=identity, version="1", source_id=identity, source_version="1",
        workstream_id=identity, profile="fixed_assignment", profile_version="1", policy_version="synthetic-policy",
        source_evidence=["Declared synthetic fixed-fee staffing source"], service_start=start, service_end=end,
        timezone=zone, currency="USD", billing_cadence="monthly",
        cost_basis="Explicit monthly overhead plus separately confirmed hourly staffing cost",
        costs_confirmed=True, costs=tuple(PeriodCost(f"{identity}-{month}", month, "US", Decimal("100" if letter == "a" else "40"))
                                         for month in months), staffing=(staffing,),
        pricing=FixedFee(Decimal("600" if letter == "a" else "240"),
            tuple(FeeAllocation(month, "US", Decimal(1)) for month in months), "Equal three-month service allocation", Decimal("0.01")))
    calculated = calculate_component(value)
    expected_costs = [Decimal(value) for value in (("268", "260", "284") if letter == "a" else ("216", "208", "216"))]
    require(calculated.status == "ok" and not calculated.missing, "Fixture economics are incomplete")
    require([row.cost for row in calculated.rows] == expected_costs, "Calendar staffing plus overhead differs from literal oracle")
    require(sum(row.revenue for row in calculated.rows) == Decimal("600" if letter == "a" else "240"), "Fixture revenue differs from literal oracle")
    return COMPONENT.dump_python(value, mode="json")


def no_owned_worker():
    listing = subprocess.run(["ps", "-axo", "pid=,command="], check=True, capture_output=True, text=True).stdout
    for line in listing.splitlines():
        if "-m worker.forecast_plans" not in line:
            continue
        pid = line.strip().split(maxsplit=1)[0]
        cwd = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True)
        require(f"n{ROOT}" not in cwd.stdout.splitlines(), f"Owned Forecast worker {pid} is already running")


async def seed(url, source, output):
    components = {letter: component(letter) for letter in ("a", "b")}
    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {"application_name": "s21-five-views-fixture"}})
    run_id = str(uuid.uuid4())
    manifest = dict(database=url.database, tenant=url.database, actor_email=source["actor_email"], run_id=run_id,
        gm_model_id=source["gm_model_id"], sow_version_id=source["sow_version_id"],
        as_of="2026-10-15T12:00:00Z", status="authoritative_intent", operations=[],
        expected=dict(current_month_signed="24000", current_quarter_signed="24000", next_quarter_expected="300",
            future_expected="360", future_upside="840", future_committed="0", account_a_future_expected="300"))
    try:
        async with engine.connect() as connection:
            identity = (await connection.execute(text("SELECT current_database(), current_user, pg_get_userbyid(datdba), "
                "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))).one()
            require(tuple(identity) == (url.database, "s21", "s21", f"owned-s21-t21:{url.database.removeprefix('s21_cov_')}"), "Owned database marker mismatch")
            head = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            require(head == [SUPPORTED_REVISION], f"Require exact migration {SUPPORTED_REVISION}")
            account_name = (await connection.execute(text("SELECT c.name FROM client c JOIN opportunity o ON o.client_id=c.id "
                "JOIN gm_model gm ON gm.opportunity_id=o.id WHERE c.id=:account AND o.id=:deal AND gm.id=:gm"),
                {"account": uuid.UUID(source["account_id"]), "deal": uuid.UUID(source["opportunity_id"]), "gm": uuid.UUID(source["gm_model_id"])})).scalar_one()
            manifest.update(account_a_id=source["account_id"], account_a_name=account_name, deal_a_id=source["opportunity_id"])
        no_owned_worker()
        # Exclusive creation precedes the first mutation; each intent/result is fsynced.
        with output.open("x") as receipt:
            def checkpoint():
                receipt.seek(0)
                json.dump(manifest, receipt, indent=2, sort_keys=True)
                receipt.truncate()
                receipt.flush()
                os.fsync(receipt.fileno())

            checkpoint()
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8210", timeout=45, trust_env=False,
                                         headers={"X-Test-User": source["actor_email"]}) as client:
                async def post(path, body):
                    operation = dict(path=path, body=body, status="intent")
                    manifest["operations"].append(operation)
                    checkpoint()
                    response = await client.post(path, json=body)
                    operation.update(http_status=response.status_code, response=response.json(), status="response")
                    checkpoint()
                    require(response.status_code == 201, f"{path}: {response.status_code} {response.text}")
                    return response.json()

                try:
                    preflight = await client.get("/forecast/outlook", params={
                        "account_id": source["account_id"], "as_of": manifest["as_of"], "future_quarters": 2})
                    require(preflight.status_code == 200 and any(row.get("source_id") == source["gm_model_id"]
                        for row in preflight.json().get("rows", [])),
                        "API does not expose the authorized private signed fixture; no mutations issued")
                    for label in ("b", "empty"):
                        issued = await post("/dev/test-fixtures", dict(label=f"Five views {label} {run_id}",
                            reviewer_ids=[source["actor_id"]], hours=4))
                        async with engine.connect() as connection:
                            name = (await connection.execute(text("SELECT name FROM client WHERE id=:id"),
                                                             {"id": uuid.UUID(issued["client_id"])})).scalar_one()
                        if label == "b":
                            manifest.update(account_b_id=issued["client_id"], account_b_name=name, deal_b_id=issued["opportunity_id"])
                        else:
                            manifest.update(empty_account_id=issued["client_id"], empty_account_name=name)
                        checkpoint()
                    for letter, probability in (("a", "0.50"), ("b", "0.25")):
                        title = f"Five views {letter.upper()} {run_id}"
                        plan = await post("/forecast/plans", dict(account_id=manifest[f"account_{letter}_id"],
                            opportunity_id=manifest[f"deal_{letter}_id"], title=title,
                            idempotency_key=str(uuid.uuid5(uuid.UUID(run_id), f"plan-{letter}")), inputs=components[letter],
                            probability=probability, probability_source="Explicit synthetic sales assumption",
                            assumptions=["Equal three-month service allocation; one US full-time engineer"],
                            lifecycle="tentative", change_reason="Dedicated five-view forecast fixture"))
                        manifest.update({f"plan_{letter}_id": plan["id"], f"plan_{letter}_title": title,
                                         f"plan_{letter}_version_id": plan["version_id"]})
                        checkpoint()
                    no_owned_worker()
                    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "worker.forecast_plans", cwd=ROOT,
                        env={**os.environ, "PYTHONPATH": str(ROOT / "api"), "PYTHONDONTWRITEBYTECODE": "1",
                             "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    manifest["worker"] = {"pid": process.pid, "status": "running"}
                    checkpoint()
                    try:
                        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
                    except asyncio.TimeoutError:
                        process.terminate()
                        stdout, stderr = await process.communicate()
                        manifest["worker"].update(status="timed_out", exit_code=process.returncode,
                            stdout=stdout.decode(), stderr=stderr.decode())
                        checkpoint()
                        raise RuntimeError("Owned Forecast worker exceeded120 seconds and was collected")
                    manifest["worker"].update(status="finished", exit_code=process.returncode,
                        stdout=stdout.decode(), stderr=stderr.decode())
                    checkpoint()
                    require(process.returncode == 0, "Forecast worker failed; preserve receipts for review")
                    for letter in ("a", "b"):
                        response = await client.get("/forecast/plans", params={"account_id": manifest[f"account_{letter}_id"]})
                        require(response.status_code == 200, "Cannot verify worker persistence")
                        plan = next(row for row in response.json()["items"] if row["id"] == manifest[f"plan_{letter}_id"])
                        require(plan["job"]["status"] == "done", "Owned plan calculation has not completed")
                    manifest["status"] = "ready_for_browser"
                except Exception as error:
                    manifest.update(status="failed_preserved", error=f"{type(error).__name__}: {error}")
                    checkpoint()
                    raise
                checkpoint()
        print(json.dumps({"manifest": str(output), "run_id": run_id, "status": manifest["status"]}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed(*configuration()))
