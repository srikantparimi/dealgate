"""Independent Company X demand oracles through actual persisted services.

These private SQLite boundaries cover plans plus managed supply, not sourcing,
retained projects, live connectors, PostgreSQL locking, or whole T22/T23 acceptance.
"""

import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth import AuthUser
from app.db.base import Base
from app.gm.calendar import DayHours, StaffingAssignment, WorkCalendar
from app.gm.commercial import HybridPricing, PricingComponent
from app.gm.demand_source import line_key
from app.models.client import Client
from app.models.people_demand import DemandLine, DemandPublicationVersion
from app.models.user import User
from app.services.commercial_models import COMPONENT
from app.services.forecast_plans import PlanInput, save_plan
from app.services.people_allocation import demand_allocation
from app.services.people_demand import PublishDemandInput, demand_sources, publish_plan_demand
from app.services.people_planning import WorkforceImportInput, availability, import_workforce


D = Decimal
NOV_APR = ["2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"]
DEC_MAY = ["2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01", "2027-05-01"]
ZONES = {"US": "America/Los_Angeles", "India": "Asia/Kolkata"}


@pytest.fixture(autouse=True)
def isolated_scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "independent-company-x-demand")
    monkeypatch.setenv("DEALGATE_REPORTING_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("DEALGATE_REPORTING_CURRENCY", "USD")


@pytest_asyncio.fixture
async def engine():
    database = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(database.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        await database.dispose()


def company_component(*, us=2, india=5, start=date(2026, 11, 1), end=date(2027, 4, 30)):
    common = dict(version="1", source_id="company-x-approved-scope", source_version="1",
        workstream_id="implementation", profile_version="1", policy_version="explicit-policy-v1",
        source_evidence=("Company X reviewed staffing scope, sections US and India",),
        service_start=start, service_end=end, currency="USD", billing_cadence="monthly",
        cost_basis=None, costs_confirmed=False, costs=())
    children = []
    for location, quantity in (("US", us), ("India", india)):
        identity = f"company-x-{location}"
        timezone = ZONES[location]
        calendar = WorkCalendar(f"approved-{location}", "1", timezone,
            date(2026, 10, 1), date(2027, 5, 31),
            (DayHours(D("8"), D("8"), D("8")),) * 5
            + (DayHours(D("0"), D("0"), D("0")),) * 2)
        assignment = StaffingAssignment(assignment_id="implementation-team",
            source_id=common["source_id"], source_version=common["source_version"],
            component_id=identity, profile_version="1", policy_version=common["policy_version"],
            role="Engineer", location=location, timezone=timezone, currency="USD",
            quantity=quantity, allocation=D("1"), calendar=calendar,
            bill_rate=None, cost_rate=None, rate_version=None, cost_version=None,
            start=start, end=end)
        children.append(PricingComponent(component_id=identity, profile="fixed_assignment",
            timezone=timezone, pricing=None, staffing=(assignment,), **common))
    return PricingComponent(component_id="company-x-root", profile="hybrid",
        timezone=ZONES["US"], pricing=HybridPricing(tuple(children)), **common)


async def owner_and_account(session, name="Company X"):
    owner = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test",
        name=f"{name} planner", groups=["Delivery"])
    account = Client(id=uuid.uuid4(), name=name)
    session.add_all([owner, account])
    await session.commit()
    return AuthUser(id=owner.id, email=owner.email, name=owner.name, groups=("Delivery",)), account


def plan_request(account, **changes):
    return PlanInput(account_id=account.id, title=f"{account.name} implementation",
        idempotency_key=uuid.uuid4(), inputs=COMPONENT.dump_python(company_component(**changes), mode="json"),
        probability="0.70", probability_source="Reviewed Company X sales assumption",
        lifecycle="tentative", assumptions=["Reviewed location quantities and dates in source staffing"],
        change_reason="Independently specified Company X staffing scope")


async def publish(session, actor, version, previous=None, enrichments=None):
    if enrichments is None and previous is None:
        enrichments = {line_key(f"company-x-{location}", "implementation-team"):
            {"skills": ["python"], "level": "Senior",
             "evidence": [f"Approved {location} role and skill review"]} for location in ZONES}
    return await publish_plan_demand(session, actor=actor, body=PublishDemandInput(
        plan_id=version.plan_id, expected_source_version_id=version.id,
        expected_publication_version_id=previous["version_id"] if previous else None,
        request_key=str(uuid.uuid4()), reason="Delivery publishes reviewed staffing",
        enrichments=enrichments or {}))


def roster(*, us=2, india=5, assignments=None, commitment_end="2027-05-31"):
    result = []
    for location, quantity in (("US", us), ("India", india)):
        for index in range(quantity):
            intervals = [dict(kind="gross", allocation="1", start_date="2026-10-01", end_date="2027-05-31")]
            if assignments is not None:
                intervals.append(dict(kind="committed", allocation="1", start_date="2026-11-01",
                    end_date=commitment_end, assignment_key=assignments[location]))
            result.append(dict(person_key=f"{location}-{index}", display_name=f"Reviewed {location} person {index}",
                role="Engineer", skills=["python"], level="Senior", location=location,
                timezone=ZONES[location], evidence=["Independently reviewed managed workforce snapshot"],
                intervals=intervals))
    return result


async def import_roster(session, actor, people, previous=None):
    return await import_workforce(session, actor=replace(actor, groups=("HR",)), body=WorkforceImportInput(
        source_system="qa-reviewed-workforce", request_key=str(uuid.uuid4()),
        expected_previous_batch_id=previous["id"] if previous else None,
        source_as_of="2026-10-01T00:00:00Z", reason="Approved complete capacity snapshot",
        basis="gross_with_commitments", people=people))


async def allocation(session, actor, account=None):
    return await demand_allocation(session, actor=replace(actor, groups=("HR",)),
        account_id=account.id if account else None)


def assert_months(result, months, *, headcount, fte, gap):
    assert result["complete"] is True
    assert result["missing"] == [] and result["pending_sources"] == []
    assert result["is_reservation"] is False
    assert result["policy_status"] == "proposal"
    assert result["freshness_status"] == "measured_not_live"
    assert [(row["month"], row["peak_headcount"], D(row["peak_fte"]), D(row["gap_fte"]))
        for row in result["months"]] == [(month, headcount, D(fte), D(gap)) for month in months]


@pytest.mark.parametrize("revised_probability", ["0.20", "1.00", "0.00", None])
async def test_company_x_probability_revisions_keep_two_us_five_india(session, revised_probability):
    actor, account = await owner_and_account(session)
    await import_roster(session, actor, [])
    request = plan_request(account)
    first = await save_plan(session, actor=actor, body=request)
    published = await publish(session, actor, first)
    before = await allocation(session, actor)
    assert_months(before, NOV_APR, headcount=7, fte="7", gap="7")
    for interval in before["intervals"]:
        assert {row["location"]: row["quantity"] for row in interval["demands"]} == {"US": 2, "India": 5}
        assert all(D(row["probability"]) == D("0.70") for row in interval["demands"])

    second = await save_plan(session, actor=actor, plan_id=first.plan_id,
        body=request.model_copy(update={"expected_version_id": first.id, "probability": revised_probability}))
    stale = await demand_sources(session, actor=actor)
    assert stale["items"][0]["state"] == "stale" and stale["items"][0]["lines"] == []
    pending = await allocation(session, actor)
    assert pending["complete"] is False and pending["months"] == []
    assert pending["pending_sources"] == [str(first.plan_id)]
    await publish(session, actor, second, previous=published)
    after = await allocation(session, actor)
    assert_months(after, NOV_APR, headcount=7, fte="7", gap="7")
    assert after["source_watermark"] != before["source_watermark"]
    for interval in after["intervals"]:
        assert {row["location"]: row["quantity"] for row in interval["demands"]} == {"US": 2, "India": 5}
        for row in interval["demands"]:
            assert row["probability"] is None if revised_probability is None else D(row["probability"]) == D(revised_probability)


async def test_company_x_date_and_headcount_revision_replaces_current_not_history(session):
    actor, account = await owner_and_account(session)
    await import_roster(session, actor, [])
    request = plan_request(account)
    original = await save_plan(session, actor=actor, body=request)
    old_publication = await publish(session, actor, original)
    replacement = company_component(us=3, start=date(2026, 12, 1), end=date(2027, 5, 31))
    revised = await save_plan(session, actor=actor, plan_id=original.plan_id,
        body=request.model_copy(update={"expected_version_id": original.id,
            "inputs": COMPONENT.dump_python(replacement, mode="json")}))
    pending = await allocation(session, actor)
    assert pending["months"] == [] and pending["complete"] is False
    current_publication = await publish(session, actor, revised, previous=old_publication)
    current = await allocation(session, actor)
    assert_months(current, DEC_MAY, headcount=8, fte="8", gap="8")
    assert current["intervals"][0]["start"] == "2026-12-01"
    assert current["intervals"][-1]["end_exclusive"] == "2027-06-01"
    for publication, expected, start, end in (
        (old_publication, {"US": 2, "India": 5}, date(2026, 11, 1), date(2027, 4, 30)),
        (current_publication, {"US": 3, "India": 5}, date(2026, 12, 1), date(2027, 5, 31)),
    ):
        rows = (await session.scalars(select(DemandLine).where(
            DemandLine.version_id == uuid.UUID(publication["version_id"])))).all()
        assert {row.location: row.quantity for row in rows} == expected
        assert all(row.start_date == start and row.end_date == end for row in rows)
        assert all(row.skills == ["python"] and row.level == "Senior" and row.evidence for row in rows)
    old = await session.get(DemandPublicationVersion, uuid.UUID(old_publication["version_id"]))
    assert old.source_version == str(original.id)
    assert current_publication["revision"] == 2


async def test_company_x_global_competitor_consumes_capacity_before_account_or_sales_filter(session):
    actor, account = await owner_and_account(session)
    await import_roster(session, actor, roster(us=1, india=4))
    own = await save_plan(session, actor=actor, body=plan_request(account))
    await publish(session, actor, own)
    competitor, other_account = await owner_and_account(session, "Earlier confidential account")
    earlier = await save_plan(session, actor=competitor,
        body=plan_request(other_account, us=1, india=1, start=date(2026, 10, 15)))
    await publish(session, competitor, earlier)

    scoped = await allocation(session, actor, account)
    assert scoped["scope_label"] == "Selected account demand"
    assert_months(scoped, NOV_APR, headcount=7, fte="7", gap="4")
    for interval in scoped["intervals"]:
        assert {row["location"]: (D(row["matched_fte"]), D(row["gap_fte"]))
            for row in interval["demands"]} == {"US": (D("0"), D("2")), "India": (D("3"), D("2"))}
    sales = await demand_allocation(session, actor=replace(actor, groups=("Sales",)))
    assert_months(sales, NOV_APR, headcount=7, fte="7", gap="4")
    assert sales["sources"] == []
    assert "Earlier confidential" not in str(sales)
    assert str(earlier.plan_id) not in str(sales)
    assert all("matches" not in row for interval in sales["intervals"] for row in interval["demands"])


async def test_company_x_retained_people_reuse_own_commitments_and_only_growth_is_incremental(session):
    actor, account = await owner_and_account(session)
    first_batch = await import_roster(session, actor, roster())
    request = plan_request(account)
    source = await save_plan(session, actor=actor, body=request)
    first_publication = await publish(session, actor, source)
    current = (await demand_sources(session, actor=replace(actor, groups=("HR",))))["items"][0]
    assignments = {line["location"]: line["demand_key"] for line in current["lines"]}
    await import_roster(session, actor, roster(assignments=assignments), previous=first_batch)
    supply = await availability(session, actor=replace(actor, groups=("HR",)))
    retained = {location: sorted(person["person_id"] for person in supply["people"]
        if person["location"] == location) for location in ZONES}
    assert {location: len(people) for location, people in retained.items()} == {"US": 2, "India": 5}
    enrichments = {line_key(f"company-x-{location}", "implementation-team"):
        {"retained_person_ids": people, "evidence": ["Delivery confirms same-source continuity"]}
        for location, people in retained.items()}
    continuity_publication = await publish(session, actor, source,
        previous=first_publication, enrichments=enrichments)
    kept = await allocation(session, actor)
    assert_months(kept, NOV_APR, headcount=7, fte="7", gap="0")
    for interval in kept["intervals"]:
        assert sum(row["retained_quantity"] for row in interval["demands"]) == 7
        assert sum(row["incremental_quantity"] for row in interval["demands"]) == 0
        assert sum(len(row["matches"]) for row in interval["demands"]) == 7
        assert all(match["continuity"] for row in interval["demands"] for match in row["matches"])
        assert interval["overcommitted_person_ids"] == []

    revised = await save_plan(session, actor=actor, plan_id=source.plan_id,
        body=request.model_copy(update={"expected_version_id": source.id,
            "inputs": COMPONENT.dump_python(company_component(us=3), mode="json")}))
    await publish(session, actor, revised, previous=continuity_publication)
    grown = await allocation(session, actor)
    assert_months(grown, NOV_APR, headcount=8, fte="8", gap="1")
    for interval in grown["intervals"]:
        assert sum(row["retained_quantity"] for row in interval["demands"]) == 7
        assert sum(row["incremental_quantity"] for row in interval["demands"]) == 1
        assert sum(D(row["matched_fte"]) for row in interval["demands"]) == D("7")


async def test_company_x_foreign_commitments_roll_off_on_inclusive_boundary(session):
    actor, account = await owner_and_account(session)
    await import_roster(session, actor, roster(assignments={"US": "other-US", "India": "other-India"},
        commitment_end="2026-11-15"))
    version = await save_plan(session, actor=actor, body=plan_request(account))
    await publish(session, actor, version)
    result = await allocation(session, actor)
    november = [interval for interval in result["intervals"] if interval["start"].startswith("2026-11")]
    assert [(item["start"], item["end_exclusive"],
        sum(D(row["matched_fte"]) for row in item["demands"]),
        sum(D(row["gap_fte"]) for row in item["demands"])) for item in november] == [
            ("2026-11-01", "2026-11-16", D("0"), D("7")),
            ("2026-11-16", "2026-12-01", D("7"), D("0"))]
    assert result["months"][0] == {"month": "2026-11-01", "peak_headcount": 7,
        "peak_fte": "7", "gap_fte": "7"}
    assert all(D(month["gap_fte"]) == D("0") for month in result["months"][1:])
