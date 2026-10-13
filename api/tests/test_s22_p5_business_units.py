"""S22 P5 — business units, the forecast-model master, actuals (directive §P5 items 2–4, 9).

Drives the real router over HTTP against the SQLite test schema, like test_s22_portfolio_forecast.
The model fixture is the synthetic workbook test_forecast_model_import builds (same layouts as the
real model, invented people and clients); the real model never enters the repo.
"""

from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models.engagement import Engagement
from tests.forecast.test_forecast_model_import import build_fixture
from tests.test_s22_portfolio_forecast import (
    actor_for,
    client_for,
    close,
    post,
    seed_calendar,
    seed_client,
    seed_client_a,
)

MODEL = Path(__file__).parent / "forecast" / "fixtures" / "forecast_model_synthetic.xlsx"


def model_bytes() -> bytes:
    if not MODEL.exists():
        build_fixture(MODEL)
    return MODEL.read_bytes()


async def upload_model(client, *, dry_run: bool, as_of: str = "2026-02", expect: int = 200) -> dict:
    response = await client.post(
        "/engagements/import-forecast-model",
        files={"file": ("model.xlsx", model_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dry_run": "true" if dry_run else "false", "as_of": as_of},
    )
    assert response.status_code == expect, response.text
    return response.json()


async def test_model_import_dry_run_reports_three_business_units_and_creates_nothing(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("SystemAdmin",))
    async with client_for(session, actor) as client:
        report = await upload_model(client, dry_run=True)
        assert report["dry_run"] is True and report["created"] is None
        assert [b["business_unit"] for b in report["by_business_unit"]] == ["ST21", "IT Avalon", "Retro Rabbit"]
        st21 = next(b for b in report["by_business_unit"] if b["business_unit"] == "ST21")
        assert st21["clients"] == 2 and st21["engagements"] == 2 and st21["people"] == 5
        avalon = next(b for b in report["by_business_unit"] if b["business_unit"] == "IT Avalon")
        assert avalon["engagements"] == 3 and avalon["closed"] == 1            # Gamma VMS + PO, Delta (closed)
        assert {t["tab"] for t in report["tabs"]} == {"Alpha", "Beta", "Gamma Health-VMS", "Delta Closed"}
        assert "## By business unit" in report["report_markdown"] and "## Calendar" in report["report_markdown"]
        assert "India - Pune" in report["report_markdown"] and "South Africa" in report["report_markdown"]
        assert (await client.get("/engagements")).json()["total"] == 0
        assert await session.scalar(select(func.count()).select_from(Engagement)) == 0


async def test_model_import_load_creates_the_ledger_and_the_portfolio_groups_reconcile(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("SystemAdmin",))
    async with client_for(session, actor) as client:
        loaded = await upload_model(client, dry_run=False)
        created = loaded["created"]
        assert created["clients"] == 4 and created["engagements"] == 5 and created["allocations"] >= 8 and created["actual_rows"] > 0
        # locations the Settings page lacked now exist with their WorkingDays holidays
        settings = (await client.get("/settings/forecast")).json()
        names = {loc["name"] for loc in settings["locations"]}
        assert {"India - Pune", "India - Chennai", "South Africa"} <= names
        assert len(settings["holidays"]["India - Pune"]) == 4 and len(settings["holidays"]["South Africa"]) == 1
        # closed engagements are kept, flagged, and off the portfolio
        listed = (await client.get("/engagements?page_size=50")).json()["items"]
        delta = next(e for e in listed if e["name"].startswith("Delta Closed"))
        assert delta["closed"] is True and delta["business_unit"] == "IT Avalon"
        gamma = [e for e in listed if e["name"].startswith("Gamma Health-VMS")]
        assert len(gamma) == 2 and all(e["business_unit"] == "IT Avalon" and e["sales_owner"] == "Kim" and e["delivery_owner"] == "Lee" for e in gamma)
        # imported people have no cost: INCOMPLETE until the rate card covers them; actuals arrived with the sheet
        alpha = next(e for e in listed if e["name"].startswith("Alpha"))
        f = (await client.get(f"/engagements/{alpha['id']}/forecast")).json()
        assert f["status"] == "INCOMPLETE" and any("cost per hour unknown" in m for m in f["missing"])
        assert f["actuals"]["months_with_actuals"] == 3
        sep = next(m for m in f["months"] if m["month"] == "2025-09")
        assert sep["actual_revenue"] is not None and close(sep["billing_loss"], D(sep["revenue"]) - D(sep["actual_revenue"]))
        assert close(f["actuals"]["billing_loss"], D(f["actuals"]["forecast_in_actual_months"]) - D(f["actuals"]["actual_revenue"]))
        rows = (await client.get(f"/engagements/{alpha['id']}/allocations")).json()
        assert {r["person"] for r in rows} == {"Person A1", "Person A2", "Person A3"} and all(r["rate_basis"] == "monthly" for r in rows)
        assert all(r["cost_per_hour"] is None for r in rows)

        # item 9: BU subtotals == Σ their rows; grand total == Σ subtotals; billing-loss count == rows with actuals
        month = "2026-01"
        view = (await client.get(f"/portfolio/forecast?month={month}")).json()
        assert delta["id"] not in {r["engagement_id"] for r in view["rows"]}
        assert [g["business_unit"] for g in view["groups"]] == ["ST21", "IT Avalon"]
        for g in view["groups"]:
            mine = [r for r in view["rows"] if r["business_unit"] == g["business_unit"]]
            assert g["engagements"] == len(mine) and g["people"] == sum(r["people"] for r in mine)
            assert close(g["revenue"], sum(D(r["revenue_month"]) for r in mine))
            assert close(g["cost"], sum(D(r["cost_month"]) for r in mine))
        assert close(view["totals"]["revenue"], sum(D(g["revenue"]) for g in view["groups"]))
        assert close(view["totals"]["cost"], sum(D(g["cost"]) for g in view["groups"]))
        assert view["totals"]["people"] == sum(g["people"] for g in view["groups"])
        with_actuals = 0
        for r in view["rows"]:
            fr = (await client.get(f"/engagements/{r['engagement_id']}/forecast")).json()
            with_actuals += 1 if fr["actuals"]["months_with_actuals"] else 0
            assert r["sales_owner"] and r["delivery_owner"]
        assert view["cards"]["billing_loss"]["engagements"] == with_actuals > 0
        assert close(view["cards"]["billing_loss"]["amount"], D(view["cards"]["billing_loss"]["forecast"]) - D(view["cards"]["billing_loss"]["billed"]))
        # one BU tab: its rows and one subtotal only
        tab = (await client.get(f"/portfolio/forecast?month={month}&business_unit=IT%20Avalon")).json()
        assert {r["business_unit"] for r in tab["rows"]} == {"IT Avalon"} and [g["business_unit"] for g in tab["groups"]] == ["IT Avalon"]
        assert close(tab["totals"]["revenue"], tab["groups"][0]["revenue"])
        csv_text = (await client.get(f"/portfolio/forecast.csv?month={month}")).text
        assert "ST21 subtotal" in csv_text and "IT Avalon subtotal" in csv_text and f"All business units · {month}" in csv_text

        # re-importing the same file is idempotent
        again = await upload_model(client, dry_run=False)
        assert again["created"]["engagements"] == 0 and again["created"]["allocations"] == 0 and again["created"]["clients"] == 0
        assert (await client.get("/engagements?page_size=50")).json()["total"] == 5
        assert len((await client.get(f"/engagements/{alpha['id']}/allocations")).json()) == 3


async def test_put_actuals_recomputes_the_forecast_and_the_billing_loss_card(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client A")
    async with client_for(session, actor) as client:
        eng, allocations = await seed_client_a(client, client_row)
        before = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        assert before["actuals"]["months_with_actuals"] == 0 and all(m["actual_revenue"] is None for m in before["months"])
        first_month = before["months"][0]["month"]
        response = await client.put(
            f"/allocations/{allocations[0]['id']}/actuals",
            json=[{"month": first_month, "hours": 150, "revenue": "20000.00"}],
        )
        assert response.status_code == 200, response.text
        f = response.json()
        assert f["actuals"]["months_with_actuals"] == 1
        line = next(m for m in f["months"] if m["month"] == first_month)
        assert close(line["actual_revenue"], "20000.00") and close(line["actual_hours"], 150)
        assert close(line["billing_loss"], D(line["revenue"]) - D("20000.00"))
        assert close(f["actuals"]["billing_loss"], D(line["revenue"]) - D("20000.00"))
        # the plan numbers are untouched by actuals
        assert f["totals"] == before["totals"]
        view = (await client.get(f"/portfolio/forecast?month={first_month}")).json()
        assert view["cards"]["billing_loss"]["engagements"] == 1 and close(view["cards"]["billing_loss"]["amount"], f["actuals"]["billing_loss"])
        # months not in the body are removed
        cleared = (await client.put(f"/allocations/{allocations[0]['id']}/actuals", json=[])).json()
        assert cleared["actuals"]["months_with_actuals"] == 0
        bad = await client.put(f"/allocations/{allocations[0]['id']}/actuals", json=[{"month": "2026-13"}])
        assert bad.status_code == 422


async def test_business_unit_owners_closed_rate_basis_and_msp_on_monthly_rates(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client C")
    async with client_for(session, actor) as client:
        eng = await post(client, "/engagements", {
            "client_id": str(client_row.id), "name": "O365 support — CR #01", "type": "msp", "start": "2026-07-01", "end": "2027-06-30",
            "additional_costs_flag": False, "same_dates_for_all": True, "business_unit": "IT Avalon", "sales_owner": "Janice Krpan",
            "delivery_owner": "Srikanth Parimi",
        })
        assert eng["business_unit"] == "IT Avalon" and eng["sales_owner"] == "Janice Krpan" and eng["closed"] is False
        await post(client, "/engagements", {
            "client_id": str(client_row.id), "name": "bad", "type": "msp", "start": "2026-07-01", "end": "2026-12-31",
            "additional_costs_flag": False, "same_dates_for_all": True, "business_unit": "Nope", "monthly_fee": 1,
        }, expect=422)
        res = await post(client, "/resources", {"name": "Person 1", "location": "India", "employment_type": "w2_employee", "seniority": "Mid"})
        row = await post(client, f"/engagements/{eng['id']}/allocations", {
            "resource_id": res["id"], "role": "Developer", "utilization": 1, "bill_rate": 5151, "rate_basis": "monthly", "person": "Person 1",
        })
        assert row["rate_basis"] == "monthly" and row["person"] == "Person 1"
        assert D(row["totals"]["revenue"]) > 0 and row["totals"]["row_gm_pct"] is not None      # MSP without a fee bills the people's rates
        f = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        assert not any("monthly_fee" in m for m in f["missing"]) and f["status"] in ("PASS", "BELOW FLOOR")
        jul = next(m for m in f["months"] if m["month"] == "2026-07")
        assert close(jul["revenue"], "5151.00")                                                   # a monthly rate is calendar-independent
        patched = await client.patch(f"/allocations/{row['id']}", json={"rate_basis": "weekly"})
        assert patched.status_code == 422
        closed = (await client.patch(f"/engagements/{eng['id']}", json={"closed": True, "business_unit": "Retro Rabbit"})).json()
        assert closed["closed"] is True and closed["business_unit"] == "Retro Rabbit"
        view = (await client.get("/portfolio/forecast?month=2026-07")).json()
        assert eng["id"] not in {r["engagement_id"] for r in view["rows"]} and view["groups"] == []
        listed = (await client.get("/engagements")).json()["items"]
        assert next(e for e in listed if e["id"] == eng["id"])["closed"] is True


@pytest.mark.parametrize("role, can_write", [("Presales", False), ("HR", False), ("Delivery", True), ("Finance", True)])
async def test_permissions_on_the_new_endpoints(session, role, can_write):
    await seed_calendar(session)
    writer = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client A")
    async with client_for(session, writer) as client:
        eng, allocations = await seed_client_a(client, client_row)
    actor = await actor_for(session, (role,))
    async with client_for(session, actor) as client:
        put = await client.put(f"/allocations/{allocations[0]['id']}/actuals", json=[])
        imp = await client.post("/engagements/import-forecast-model", files={"file": ("m.xlsx", model_bytes())}, data={"dry_run": "true"})
        assert (put.status_code == 200) is can_write and (imp.status_code == 200) is can_write, (role, put.status_code, imp.status_code)


async def test_model_import_rejects_a_workbook_that_is_not_the_master(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    sheet = (Path(__file__).resolve().parents[2] / "docs/reference/DealGate_Cost_Margin_SAMPLE_StaffAug.xlsx").read_bytes()
    async with client_for(session, actor) as client:
        response = await client.post("/engagements/import-forecast-model", files={"file": ("sheet.xlsx", sheet)}, data={"dry_run": "true"})
        assert response.status_code == 422 and "Not a forecast model master" in response.text
        response = await client.post("/engagements/import-forecast-model", files={"file": ("x.xlsx", b"not a workbook")}, data={"dry_run": "true"})
        assert response.status_code == 422
