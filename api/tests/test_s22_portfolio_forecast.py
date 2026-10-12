"""S22 P1 — the integration must agree with the engine, to the cent.

These tests drive the real router over HTTP (ASGI transport) against the
SQLite test schema. The calendar is seeded from
docs/reference/forecast-goldens.json exactly as the engine's golden test
seeds it, so a disagreement here is an integration defect, never an engine
one (directive S22 §1).
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.client import Client
from app.models.engagement import (
    Allocation,
    CalendarLocation,
    CostRateCard,
    ForecastPolicy,
    ForecastRun,
    Holiday,
)
from app.models.user import User
from app.routers.engagements import router

GOLDENS = json.load(open(Path(__file__).resolve().parents[2] / "docs/reference/forecast-goldens.json"))
TYPE = {
    "Fixed cost": "fixed_cost",
    "Assessment": "assessment",
    "MSP": "msp",
    "Time & materials": "time_and_materials",
    "Staff augmentation": "staff_augmentation",
}
EMP = {"W-2 / Employee": "w2_employee", "1099 / Contractor": "contractor_1099"}
CLIENT_A = next(s for s in GOLDENS["scenarios"] if s["name"].startswith("STAFF AUG — Client A"))


def close(a, b, tol="0.01") -> bool:
    return abs(D(str(a)) - D(str(b))) <= D(tol)


async def seed_calendar(session) -> None:
    """The goldens' calendar, written the way migration 0065 writes the workbook's Settings tab."""

    session.add(ForecastPolicy(id=uuid.uuid4(), hours_per_day=D(str(GOLDENS["hours_per_day"])),
                               project_floor_pct=D(str(GOLDENS["project_floor"]))))
    locations: dict[str, CalendarLocation] = {}
    for name, floor in GOLDENS["resource_floor"].items():
        loc = CalendarLocation(
            id=uuid.uuid4(), name=name,
            burden_pct_w2=D(str(GOLDENS["burden"][f"{name}|W-2 / Employee"])),
            burden_pct_1099=D(str(GOLDENS["burden"][f"{name}|1099 / Contractor"])),
            resource_floor_pct=D(str(floor)),
        )
        session.add(loc)
        locations[name] = loc
    await session.flush()
    for name, days in GOLDENS["holidays"].items():
        for day in days:
            session.add(Holiday(id=uuid.uuid4(), location_id=locations[name].id, day=date.fromisoformat(day)))
    for key, cost in GOLDENS["rate_card_mid"].items():
        loc, emp = key.split("|")
        session.add(CostRateCard(id=uuid.uuid4(), seniority="Mid", location_id=locations[loc].id,
                                 employment_type=EMP[emp], cost_per_hour=D(str(cost))))
    await session.commit()


async def actor_for(session, groups: tuple[str, ...]) -> AuthUser:
    actor = AuthUser(uuid.uuid4(), f"{uuid.uuid4()}@example.test", "Synthetic", groups)
    session.add(User(id=actor.id, email=actor.email, name=actor.name, groups=list(groups)))
    await session.commit()
    return actor


def app_for(session, actor: AuthUser) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: actor

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    return app


def client_for(session, actor: AuthUser) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(session, actor)), base_url="http://test")


async def seed_client(session, name: str) -> Client:
    row = Client(id=uuid.uuid4(), name=name, hubspot_company_id=None)
    session.add(row)
    await session.commit()
    return row


async def post(client: httpx.AsyncClient, path: str, body: dict, expect: int = 201) -> dict:
    response = await client.post(path, json=body)
    assert response.status_code == expect, f"POST {path}: {response.status_code} {response.text}"
    return response.json() if response.content else {}


async def seed_client_a(client: httpx.AsyncClient, client_row: Client) -> tuple[dict, list[dict]]:
    """The Client A golden scenario: engagement, five resources, five allocations, two costs — via the API."""

    sc = CLIENT_A
    eng = await post(client, "/engagements", {
        "client_id": str(client_row.id), "name": "Portal & data platform staffing", "type": TYPE[sc["engagement_type"]],
        "start": sc["start"], "end": sc["end"], "total_price": sc["total_price"], "monthly_fee": sc["monthly_fee"],
        "additional_costs_flag": sc["additional_costs_flag"] == "Y", "same_dates_for_all": sc["same_dates_for_all"],
    })
    allocations = []
    for i, r in enumerate(sc["allocations"]):
        res = await post(client, "/resources", {"name": f"{r['role']} {i + 1}", "location": r["location"],
                                                 "employment_type": EMP[r["employment_type"]], "seniority": "Mid"})
        allocations.append(await post(client, f"/engagements/{eng['id']}/allocations", {
            "resource_id": res["id"], "role": r["role"], "assignment": r["assignment"], "utilization": r["utilization"],
            "bill_rate": r["bill_rate"], "cost_per_hour": r["cost_per_hour"], "start": r["start"], "end": r["end"],
            "hours_override": r["hours_override"],
        }))
    for c in sc["additional_costs"]:
        await post(client, f"/engagements/{eng['id']}/costs", {
            "description": "cost", "amount": c["amount"],
            "frequency": "monthly" if c["frequency"] == "Monthly" else "one_time", "billed_to_client": c["billed_to_client"] == "Y",
        })
    return eng, allocations


# ----------------------------------------------------------------------------- goldens through the API


async def test_client_a_golden_through_the_api(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client A")
    async with client_for(session, actor) as client:
        eng, allocations = await seed_client_a(client, client_row)
        response = await client.get(f"/engagements/{eng['id']}/forecast")
        assert response.status_code == 200, response.text
        f = response.json()
        e = CLIENT_A["expected"]
        assert f["status"] == e["status"] and f["monthly_required"] == e["monthly_required"] and f["missing"] == []
        assert close(f["duration_months"], e["duration_months"], "0.000001")
        for key in ("hours",):
            assert close(f["totals"][key], e[key], "0.001")
        for key in ("labour_cost", "burden_cost", "additional_costs", "pass_through_revenue", "total_revenue", "total_cost"):
            assert close(f["totals"][key], e[key]), (key, f["totals"][key], e[key])
        assert close(f["totals"]["gm_pct"], e["gm_pct"], "0.000001")
        # month-by-assignment rows, to the cent
        for row in CLIENT_A["expected_monthly_by_assignment"]:
            got = f["by_assignment"][row["assignment"]][row["month"]]
            assert got["people"] == row["people"], row
            assert close(got["hours"], row["hours"], "0.001")
            assert close(got["revenue"], row["revenue"]) and close(got["loaded_cost"], row["loaded_cost"])
        # per-allocation totals reconcile to the goldens through the Allocation schema
        rows = (await client.get(f"/engagements/{eng['id']}/allocations")).json()
        assert len(rows) == 5
        for created, expected in zip(allocations, CLIENT_A["allocations"]):
            row = next(r for r in rows if r["id"] == created["id"])
            assert row["totals"]["working_days"] == expected["expected"]["working_days"]
            assert close(row["totals"]["hours"], expected["expected"]["hours"], "0.001")
            assert close(row["totals"]["revenue"], expected["expected"]["revenue"])
            assert close(row["totals"]["loaded_cost"], D(str(expected["expected"]["labour_cost"])) + D(str(expected["expected"]["burden_cost"])))
        # location check matches the contract example
        assert f["location_check"]["US"]["ok"] is False and f["location_check"]["India"]["ok"] is True
        # India loaded cost = Σ(labour + burden) of the two India rows in the goldens = 21945.60 + 15966.72.
        # (The OpenAPI example says 37912.56 — a typo in the example; the engine is the truth.)
        assert close(f["location_check"]["US"]["revenue"], "255460.00") and close(f["location_check"]["India"]["loaded_cost"], "37912.32")
        # months reconcile to totals
        assert close(sum(D(m["total_revenue"]) for m in f["months"]), f["totals"]["total_revenue"])
        assert close(sum(D(m["total_cost"]) for m in f["months"]), f["totals"]["total_cost"])
        assert all(am["resource_name"] for am in f["allocation_months"])


async def test_forecast_run_is_cached_by_input_hash_and_invalidated_by_change(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client A")
    async with client_for(session, actor) as client:
        eng, allocations = await seed_client_a(client, client_row)
        first = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        second = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        assert first == second
        runs = await session.scalar(select(func.count()).select_from(ForecastRun))
        # list_allocations during seeding already computed + stored the run for the final state once;
        # the two GETs above must not add more rows for the same inputs.
        distinct = await session.scalar(select(func.count(func.distinct(ForecastRun.input_hash))))
        assert runs == distinct
        hashes_before = runs
        # a changed allocation (future row, in-place edit) → new hash → new run
        future = next(a for a in allocations if a["start"] == "2027-01-04")
        patched = await client.patch(f"/allocations/{future['id']}", json={"utilization": "0.5"})
        assert patched.status_code == 200, patched.text
        changed = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        assert changed["totals"]["hours"] != first["totals"]["hours"]
        assert await session.scalar(select(func.count(func.distinct(ForecastRun.input_hash)))) == hashes_before + 1
        # a settings change invalidates too
        settings = (await client.get("/settings/forecast")).json()
        settings["locations"][0]["burden_pct_w2"] = 0.40
        async with client_for(session, await actor_for(session, ("Finance",))) as finance:
            saved = await finance.put("/settings/forecast", json=settings)
            assert saved.status_code == 200, saved.text
        after_settings = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        assert after_settings["totals"]["burden_cost"] != changed["totals"]["burden_cost"]


# ----------------------------------------------------------------------------- validation + permissions


async def test_validation_messages_are_the_engines_strings(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client V")
    async with client_for(session, actor) as client:
        rejected = await client.post("/engagements", json={
            "client_id": str(client_row.id), "name": "No price", "type": "fixed_cost", "start": "2026-11-02",
            "end": "2026-12-31", "additional_costs_flag": False, "same_dates_for_all": True,
        })
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["missing"] == ["total_price required for fixed cost / assessment"]
        eng = await post(client, "/engagements", {
            "client_id": str(client_row.id), "name": "Hourly", "type": "time_and_materials", "start": "2026-11-02",
            "end": "2026-12-31", "additional_costs_flag": False, "same_dates_for_all": True,
        })
        res = await post(client, "/resources", {"name": "Developer", "location": "US", "employment_type": "w2_employee", "seniority": "Mid"})
        no_rate = await client.post(f"/engagements/{eng['id']}/allocations", json={"resource_id": res["id"], "utilization": 1})
        assert no_rate.status_code == 422
        assert no_rate.json()["detail"]["missing"] == ["Developer: bill rate required for hourly engagement types"]
        # rate card pre-fill: cost_per_hour omitted → the Mid × US × W-2 card (80) is what the engine uses
        ok = await post(client, f"/engagements/{eng['id']}/allocations", {"resource_id": res["id"], "utilization": 1, "bill_rate": 150})
        assert ok["cost_per_hour"] is None and ok["cost_per_hour_effective"] == "80.00"
        bad_util = await client.post(f"/engagements/{eng['id']}/allocations", json={"resource_id": res["id"], "utilization": 1.5, "bill_rate": 150})
        assert bad_util.json()["detail"]["missing"] == ["Developer: utilization must be 0–1"]


@pytest.mark.parametrize("role,write,read,settings_put", [
    ("SystemAdmin", 201, 200, 200), ("Finance", 201, 200, 200), ("Delivery", 201, 200, 403),
    ("Sales", 201, 200, 403), ("HR", 403, 200, 403), ("Legal", 403, 403, 403), ("Marketing", 403, 403, 403),
])
async def test_permissions_per_endpoint(session, role, write, read, settings_put):
    await seed_calendar(session)
    client_row = await seed_client(session, "Client P")
    body = {"client_id": str(client_row.id), "name": "Perm", "type": "msp", "start": "2026-11-01", "end": "2027-04-30",
            "monthly_fee": "42000", "additional_costs_flag": False, "same_dates_for_all": True}
    async with client_for(session, await actor_for(session, (role,))) as client:
        assert (await client.post("/engagements", json=body)).status_code == write
        assert (await client.get("/engagements")).status_code == read
        assert (await client.get("/portfolio/forecast?month=2026-11")).status_code == read
        assert (await client.get("/resources")).status_code == read
        settings = await client.get("/settings/forecast")
        assert settings.status_code == (200 if role in {"SystemAdmin", "Finance", "Delivery", "HR", "CEO"} else 403)
        if settings.status_code == 200:
            assert (await client.put("/settings/forecast", json=settings.json())).status_code == settings_put


async def test_sales_never_sees_an_individuals_cost(session):
    await seed_calendar(session)
    client_row = await seed_client(session, "Client A")
    async with client_for(session, await actor_for(session, ("Delivery",))) as delivery:
        eng, _ = await seed_client_a(delivery, client_row)
    async with client_for(session, await actor_for(session, ("Sales",))) as sales:
        rows = (await sales.get(f"/engagements/{eng['id']}/allocations")).json()
        assert rows and all("cost_per_hour" not in r and "loaded_cost" not in r["totals"] for r in rows)
        f = (await sales.get(f"/engagements/{eng['id']}/forecast")).json()
        assert f["totals"]["total_cost"] and all("loaded_cost" not in am for am in f["allocation_months"])
        assert f["status"] == "PASS"


# ----------------------------------------------------------------------------- ledger semantics


async def test_close_rehire_delete_and_supersede(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", "2027-01-15T12:00:00Z")
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client A")
    async with client_for(session, actor) as client:
        eng, allocations = await seed_client_a(client, client_row)
        tester = next(a for a in allocations if a["role"] == "Tester")  # 2026-12-01 → 2027-03-31
        # leaver: default end = last day of the current month
        closed = await client.post(f"/allocations/{tester['id']}/close", json={})
        assert closed.status_code == 200 and closed.json()["end"] == "2027-01-31"
        # re-hire: new row from the day after the old end, same rates
        rehired = await client.post(f"/allocations/{tester['id']}/rehire", json={})
        assert rehired.status_code == 201
        new_row = rehired.json()
        assert new_row["start"] == "2027-02-01" and new_row["bill_rate"] == "95.00" and new_row["id"] != tester["id"]
        rows = (await client.get(f"/engagements/{eng['id']}/allocations")).json()
        assert len(rows) == 6
        # the gap: the first tester row has no February hours, the re-hire has none in January
        f = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        jan = [am for am in f["allocation_months"] if am["allocation_id"] == tester["id"] and am["month"] == "2027-02"]
        assert jan == []
        # started row cannot be deleted
        assert (await client.delete(f"/allocations/{tester['id']}")).status_code == 409
        # a never-started row can
        assert (await client.delete(f"/allocations/{new_row['id']}")).status_code == 204
        # rate change on a started row supersedes it: old row ends yesterday, new row from today
        developer = next(a for a in allocations if a["role"] == "Developer" and a["location"] == "US")
        superseded = await client.patch(f"/allocations/{developer['id']}", json={"bill_rate": "150"})
        assert superseded.status_code == 200, superseded.text
        successor = superseded.json()
        assert successor["id"] != developer["id"] and successor["start"] == "2027-01-15" and successor["bill_rate"] == "150.00"
        old = await session.get(Allocation, uuid.UUID(developer["id"]))
        assert str(old.superseded_by) == successor["id"] and old.end == date(2027, 1, 14)
        current = (await client.get(f"/engagements/{eng['id']}/allocations")).json()
        assert developer["id"] not in {r["id"] for r in current} and successor["id"] in {r["id"] for r in current}
        # history is kept: January revenue mixes 135 (to the 14th) and 150 (from the 15th)
        f2 = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        jan_rows = [am for am in f2["allocation_months"] if am["month"] == "2027-01" and am["allocation_id"] in {developer["id"], successor["id"]}]
        assert len(jan_rows) == 2


async def test_engagement_list_filters_and_status(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", "2026-12-01T12:00:00Z")
    await seed_calendar(session)
    actor = await actor_for(session, ("Finance",))
    a = await seed_client(session, "Client A")
    b = await seed_client(session, "Client B")
    async with client_for(session, actor) as client:
        for client_row, name, start, end in ((a, "Active", "2026-11-01", "2027-04-30"), (b, "Future", "2027-02-01", "2027-06-30"), (b, "Past", "2026-01-01", "2026-06-30")):
            await post(client, "/engagements", {"client_id": str(client_row.id), "name": name, "type": "msp", "start": start,
                                                 "end": end, "monthly_fee": "1000", "additional_costs_flag": False, "same_dates_for_all": True})
        everything = (await client.get("/engagements")).json()
        assert everything["total"] == 3 and {e["status"] for e in everything["items"]} == {"active", "draft", "ended"}
        drafts = (await client.get("/engagements?status=draft")).json()
        assert drafts["total"] == 1 and drafts["items"][0]["name"] == "Future"
        by_client = (await client.get(f"/engagements?client_id={b.id}&page_size=25")).json()
        assert by_client["total"] == 2 and all(e["client_name"] == "Client B" for e in by_client["items"])
        detail = (await client.get(f"/engagements/{everything['items'][0]['id']}")).json()
        assert detail["client_name"] and detail["duration_months"] > 0


# ----------------------------------------------------------------------------- importer (P1-6)

WORKBOOK_HEADERS = [
    "Role *", "Seniority *", "Location *", "Employment type *  (W-2 or 1099 — sets the burden %)",
    "Assignment / project  (optional — group resources; Staff augmentation)", "Utilization %",
    "Hours  (auto — use Hours override to change)", "Bill rate  (what we CHARGE the client per hour — T&M / Staff aug only)",
    "Our cost / hour *  (what the person COSTS us, before burden — pre-filled from the Settings rate card; overwrite if known)",
    "Start  (B14 = Y: project start for everyone, greyed. B14 = N: pre-filled, change if the person joins later)",
    "End  (B14 = Y: project end for everyone. B14 = N: pre-filled, change if they leave earlier)",
    "Working days", "Hours override (optional)",
]


async def test_import_workbook_staffing_csv(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Delivery",))
    client_row = await seed_client(session, "Client A")
    sc = CLIENT_A
    buf = io.StringIO()
    writer = csv.writer(buf)  # Excel quotes headers that contain commas; so does csv.writer
    writer.writerow(WORKBOOK_HEADERS)
    for r in sc["allocations"]:
        writer.writerow([
            r["role"], "Mid", r["location"], r["employment_type"], r["assignment"], f"{r['utilization'] * 100:.0f}%", "",
            str(r["bill_rate"]), str(r["cost_per_hour"]), r["start"], r["end"], "", "",
        ])
    writer.writerow([""] * 13)  # a blank row (no Role) is ignored, as in the workbook
    csv_text = buf.getvalue()
    async with client_for(session, actor) as client:
        eng = await post(client, "/engagements", {
            "client_id": str(client_row.id), "name": "Imported", "type": "staff_augmentation", "start": sc["start"], "end": sc["end"],
            "additional_costs_flag": False, "same_dates_for_all": False,
        })
        response = await client.post("/allocations/import", data={"engagement_id": eng["id"]},
                                     files={"file": ("staffing.csv", csv_text.encode("utf-8"), "text/csv")})
        assert response.status_code == 201, response.text
        assert response.json()["created"] == 5
        rows = (await client.get(f"/engagements/{eng['id']}/allocations")).json()
        assert sorted(r["role"] for r in rows) == sorted(r["role"] for r in sc["allocations"])
        f = (await client.get(f"/engagements/{eng['id']}/forecast")).json()
        # no additional costs on this engagement → labour + burden only; hours and revenue match the golden
        assert close(f["totals"]["hours"], sc["expected"]["hours"], "0.001")
        assert close(f["totals"]["total_revenue"], D(str(sc["expected"]["total_revenue"])) - D(str(sc["expected"]["pass_through_revenue"])))
        bad = await client.post("/allocations/import", data={"engagement_id": eng["id"]},
                                files={"file": ("bad.csv", b"Role,Location,Employment type\nDev,Mars,W-2 / Employee\n", "text/csv")})
        assert bad.status_code == 422 and "unknown location 'Mars'" in bad.json()["detail"]["missing"][0]


# ----------------------------------------------------------------------------- portfolio (P3-6 reconciliation + CSV)


async def test_portfolio_month_reconciles_three_ways_and_exports_csv(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Finance",))
    a = await seed_client(session, "Client A")
    b = await seed_client(session, "Client B")
    async with client_for(session, actor) as client:
        eng_a, _ = await seed_client_a(client, a)
        eng_b = await post(client, "/engagements", {"client_id": str(b.id), "name": "Integration team", "type": "time_and_materials",
                                                   "start": "2026-10-01", "end": "2027-03-31", "additional_costs_flag": False, "same_dates_for_all": True})
        for name, loc, emp, bill, cost in (("Engineer US", "US", "w2_employee", 175, 95), ("Engineer IN", "India", "w2_employee", 60, 22)):
            res = await post(client, "/resources", {"name": name, "location": loc, "employment_type": emp, "seniority": "Senior"})
            await post(client, f"/engagements/{eng_b['id']}/allocations", {"resource_id": res["id"], "role": "Engineer", "assignment": "Integrations",
                                                                          "utilization": 1, "bill_rate": bill, "cost_per_hour": cost})
        bench_res = await post(client, "/resources", {"name": "Priya N.", "location": "India", "employment_type": "w2_employee", "seniority": "Mid"})
        month = "2027-01"
        view = (await client.get(f"/portfolio/forecast?month={month}")).json()
        assert {r["engagement_id"] for r in view["rows"]} == {eng_a["id"], eng_b["id"]}
        fa = (await client.get(f"/engagements/{eng_a['id']}/forecast")).json()
        fb = (await client.get(f"/engagements/{eng_b['id']}/forecast")).json()
        month_a = next(m for m in fa["months"] if m["month"] == month)
        month_b = next(m for m in fb["months"] if m["month"] == month)
        # 1) portfolio total == Σ engagement month lines
        assert close(view["totals"]["revenue"], D(month_a["total_revenue"]) + D(month_b["total_revenue"]))
        assert close(view["totals"]["cost"], D(month_a["total_cost"]) + D(month_b["total_cost"]))
        assert view["totals"]["people"] == month_a["people"] + month_b["people"]
        # 2) Σ engagement month lines == Σ allocation-month rows (hourly revenue; cost = loaded + additional)
        alloc_rev = sum(D(am["revenue"]) for f in (fa, fb) for am in f["allocation_months"] if am["month"] == month)
        alloc_cost = sum(D(am["loaded_cost"]) for f in (fa, fb) for am in f["allocation_months"] if am["month"] == month)
        assert close(alloc_rev + D(month_a["pass_through_revenue"]) + D(month_b["pass_through_revenue"]), view["totals"]["revenue"])
        assert close(alloc_cost + D(month_a["additional_costs"]) + D(month_b["additional_costs"]), view["totals"]["cost"])
        # cards equal the lists they open
        assert view["cards"]["below_floor"] == sum(1 for r in view["rows"] if r["status"] == "BELOW FLOOR")
        assert view["cards"]["rolloffs_60d"] == len(view["rolloffs"]) and view["cards"]["bench"] == len(view["bench_list"])
        assert any(b["resource"] == "Priya N." for b in view["bench_list"]) and bench_res["id"] in {b["resource_id"] for b in view["bench_list"]}
        assert all("resource" in r and "client" in r for r in view["rolloffs"])
        # Architect (Data platform) ends 2027-02-26 with no later row → a roll-off within 60 days of Jan 1
        assert any(r["role"] == "Architect" for r in view["rolloffs"])
        # filters narrow the rows and the totals follow
        only_b = (await client.get(f"/portfolio/forecast?month={month}&client_id={b.id}")).json()
        assert [r["engagement_id"] for r in only_b["rows"]] == [eng_b["id"]] and close(only_b["totals"]["revenue"], month_b["total_revenue"])
        csv_text = (await client.get(f"/portfolio/forecast.csv?month={month}")).text
        assert csv_text.splitlines()[0].startswith("Client,Engagement,Type") and f"Portfolio · {month}" in csv_text
        assert view["totals"]["revenue"] in csv_text


async def test_create_client_and_options(session):
    await seed_calendar(session)
    actor = await actor_for(session, ("Sales",))
    async with client_for(session, actor) as client:
        created = await post(client, "/clients", {"name": "Brand New Co"})
        assert created["source"] == "manual"
        again = await post(client, "/clients", {"name": "brand new co"})
        assert again["id"] == created["id"]
        options = (await client.get("/clients/forecast-options")).json()
        assert {"id": created["id"], "name": "Brand New Co", "source": "manual"} in options
