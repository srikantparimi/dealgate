"""Real local HTTP -> PostgreSQL -> separate worker process -> HTTP proof.

Independent Company X constants, not calculator-derived expectations. Local
identity is explicit; this does not stand in for Cognito or staging acceptance.
"""

import asyncio
import json
import os
import sys
import uuid
from decimal import Decimal
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

url = urlparse(os.environ["POSTGRES_URL"])
if url.hostname not in {"127.0.0.1", "localhost"} or url.path != "/s21_journey":
    raise RuntimeError("Dedicated local s21_journey database required")
os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID="s21-lead",
                  DEALGATE_REPORTING_TIMEZONE="America/Los_Angeles", DEALGATE_REPORTING_CURRENCY="USD")

from app.db import session_factory
from app.models.forecast import ForecastJob, ForecastPlanVersion, ForecastSchedule


async def worker():
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "worker.forecast_plans",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=os.environ.copy())
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    data = json.loads(stdout.decode().splitlines()[-1])
    print(json.dumps(data), flush=True)
    return data


async def main():
    run = uuid.uuid4().hex
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8210", timeout=60,
                                headers={"X-Test-User": "s21-browser@example.test"}) as client:
        async def request(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            assert response.is_success, f"{method} {path}: {response.status_code} {response.text}"
            return response.json()

        fixture = await request("POST", "/dev/test-fixtures", json={"label": f"Company X forecast {run}", "reviewer_ids": []})
        account = fixture["client_id"]
        print(json.dumps({"run": run, "fixture": fixture}), flush=True)
        months = ["2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"]
        component = {
            "component_id": "implementation", "version": "1", "source_id": "assessment-findings",
            "source_version": run, "workstream_id": "delivery", "profile": "fixed_assignment",
            "profile_version": "1", "policy_version": "server-bound",
            "source_evidence": ["Synthetic Company X findings, scenario A"],
            "service_start": months[0], "service_end": "2027-04-30", "timezone": "America/New_York",
            "currency": "USD", "billing_cadence": "quarterly", "cost_basis": "Explicit planning assumption",
            "costs_confirmed": True, "staffing": [],
            "costs": [{"source_id": f"team-{month}", "month": month, "location": "India", "amount": "35000"} for month in months],
            "pricing": {"total_fee": "420000", "allocations": [{"month": month, "location": "India", "weight": "1"} for month in months],
                        "allocation_basis": "Six equal service months", "minor_unit": "0.01"},
        }
        body = {"account_id": account, "opportunity_id": fixture["opportunity_id"],
                "title": "Company X implementation", "idempotency_key": str(uuid.uuid4()), "inputs": component,
                "probability": "0.70", "probability_source": "Reviewed assessment assumption, not extraction confidence",
                "assumptions": ["Six months starting November; dates and pricing are potential, not contracted"],
                "change_reason": "Assessment findings support explicit synthetic implementation assumptions"}
        created = await request("POST", "/forecast/plans", json=body)
        replay = await request("POST", "/forecast/plans", json=body)
        assert replay == created
        params = {"account_id": account, "as_of": "2026-10-01T12:00:00Z"}
        pending = await request("GET", "/forecast/outlook", params=params)
        assert pending["pending_sources"] == [created["version_id"]] and pending["stale"] is True
        await worker()
        first = await request("GET", "/forecast/outlook", params=params)
        assert first["scope_label"] == "Selected total"
        assert Decimal(first["current_quarter"]["revenue"]) == Decimal("98000")
        assert Decimal(first["future"]["revenue"]) == Decimal("196000")
        assert Decimal(first["future"]["cost"]) == Decimal("98000")
        assert Decimal(first["future"]["gm"]) == Decimal("0.5")
        assert not first["pending_sources"] and not first["excluded"]
        fifteen = await request("GET", "/forecast/outlook", params={**params, "future_quarters": 4})
        assert len(fifteen["months"]) == 15
        await worker()
        again = await request("GET", "/forecast/outlook", params=params)
        assert again["future"] == first["future"] and again["source_watermark"] == first["source_watermark"]
        body.update(expected_version_id=created["version_id"], probability="0.50", change_reason="Reviewed likelihood changed")
        updated = await request("POST", f"/forecast/plans/{created['id']}/versions", json=body)
        stale = await client.post(f"/forecast/plans/{created['id']}/versions", json=body)
        assert stale.status_code == 409
        await worker()
        final = await request("GET", "/forecast/outlook", params=params)
        assert Decimal(final["future"]["revenue"]) == Decimal("140000")
        assert Decimal(final["future"]["cost"]) == Decimal("70000")
        assert final["source_watermark"] != first["source_watermark"]
        if os.environ.get("S21_FINANCIAL") == "1":
            from app.models.actual import FinancialActual
            financial = {"source_system": f"synthetic-finance-{run}", "idempotency_key": str(uuid.uuid4()), "rows": [
                {"account_id": account, "source_id": measure, "revision": 1,
                 "period_month": "2026-10-01", "measure": measure, "amount": amount, "currency": "USD",
                 "source_date": "2026-10-01", "reason": "Independent synthetic finance ledger"}
                for measure, amount in [("recognized_revenue", "12000.01"), ("billed", "15000"),
                                        ("cash_collected", "8000"), ("delivery_cost", "6000")]]}
            imported = await request("POST", "/actuals/financial-import", json=financial)
            assert (await request("POST", "/actuals/financial-import", json=financial))["id"] == imported["id"]
            actual_view = await request("GET", "/forecast/outlook", params=params)
            assert actual_view["future"] == final["future"]
            assert {r["measure"]: Decimal(r["amount"]) for r in actual_view["financial_actuals"]["totals"]} == {
                "recognized_revenue": Decimal("12000.01"), "billed": Decimal("15000"),
                "cash_collected": Decimal("8000"), "delivery_cost": Decimal("6000")}
            financial["idempotency_key"] = str(uuid.uuid4())
            financial["rows"] = [{**financial["rows"][0], "revision": 2, "expected_previous_revision": 1,
                                  "amount": "11000.99", "reason": "Synthetic Finance correction"}]
            await request("POST", "/actuals/financial-import", json=financial)
            current = await request("GET", "/actuals/financial-records", params={"account_id": account})
            history = await request("GET", "/actuals/financial-records", params={"account_id": account, "history": True})
            assert current["total"] == 4 and history["total"] == 5
            corrected = await request("GET", "/forecast/outlook", params=params)
            assert corrected["future"] == final["future"]
            assert next(r["amount"] for r in corrected["financial_actuals"]["totals"] if r["measure"] == "recognized_revenue") == "11000.99"
            async with session_factory() as ledger_session:
                facts = list((await ledger_session.scalars(select(FinancialActual).where(
                    FinancialActual.source_system == financial["source_system"],
                    FinancialActual.source_id == "recognized_revenue").order_by(FinancialActual.revision))).all())
                assert [fact.amount for fact in facts] == [Decimal("12000.01"), Decimal("11000.99")]
            print(json.dumps({"financial_import": "passed", "bases": 4, "retained_revisions": 5,
                              "forecast_unchanged": True, "account": account}), flush=True)
        async with session_factory() as session:
            versions = list((await session.scalars(select(ForecastPlanVersion).where(ForecastPlanVersion.plan_id == uuid.UUID(created["id"])))).all())
            assert len(versions) == 2
            ids = [version.id for version in versions]
            schedules = list((await session.scalars(select(ForecastSchedule).where(ForecastSchedule.plan_version_id.in_(ids)))).all())
            jobs = list((await session.scalars(select(ForecastJob).where(ForecastJob.plan_version_id.in_(ids)))).all())
            assert len(schedules) == len(jobs) == 2
            assert {job.status for job in jobs} == {"done"}
        print(json.dumps({"journey": "persisted-planning-passed", "plan": created["id"], "latest_version": updated["version_id"],
                          "independent_expected_future": "196000", "revised_expected_future": "140000",
                          "versions": 2, "schedules": 2, "staging_verified": False}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
