"""Author-only T23 synthetic source seed; publication/import are browser actions."""

import asyncio
import json
import os
from pathlib import Path
import re
import sys
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "user", "client", "opportunity", "sow", "sow_version", "gm_model",
    "approval_package", "task", "audit_event", "project", "forecast_plan",
    "forecast_plan_version", "people_source", "people_import_batch", "workforce_person",
    "demand_publication", "demand_publication_version", "sourcing_rule_set", "sourcing_draft",
)
ZONES = {"US": "America/New_York", "India": "Asia/Kolkata"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def target():
    require(len(sys.argv) == 1, "No alternate target arguments accepted")
    require(os.environ.get("DEALGATE_ENV") == "local", "Explicit local environment required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    require(not any(key == "app" or key.startswith("app.") for key in sys.modules),
            "Run standalone before application imports")
    raw = os.environ.get("S21_PUB_DATABASE_URL")
    require(raw, "Set S21_PUB_DATABASE_URL to the already-migrated private database")
    url = make_url(raw)
    require((url.drivername, url.username, url.host, url.port) ==
            ("postgresql+asyncpg", "s21", "127.0.0.1", 55421)
            and not url.query and not url.password, "Require trust-only local asyncpg target")
    require(re.fullmatch(r"s21_pub_[0-9a-f]{32}", url.database or ""), "Refusing non-private database")
    require(os.environ.get("DEALGATE_TENANT_ID") == url.database, "Tenant must equal database name")
    os.environ.update(POSTGRES_URL=raw, DATABASE_URL=raw, ALLOW_DEV_SEED_ENDPOINT="1",
                      AWS_EC2_METADATA_DISABLED="true", PYTHONDONTWRITEBYTECODE="1")
    os.environ.pop("DEALGATE_TEST_GROUPS", None)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url


def component(*, revised=False):
    from app.gm.calendar import DayHours, StaffingAssignment, WorkCalendar
    from app.gm.commercial import FeeAllocation, FixedFee, HybridPricing, PeriodCost, PricingComponent

    start = date(2026, 12 if revised else 11, 1)
    months = [date(2026, month, 1) for month in ((12,) if revised else (11, 12))]
    months += [date(2027, month, 1) for month in (1, 2, 3, 4)]
    common = dict(version="1", source_id="synthetic-t23-scope", source_version="1",
        workstream_id="implementation", profile_version="1", policy_version="synthetic-reviewed-policy",
        source_evidence=(("Declared synthetic T23 three-US/five-India December half-time scope" if revised
                          else "Declared synthetic T23 two-US/five-India November half-time scope"),),
        service_start=start, service_end=date(2027, 4, 30), currency="USD",
        billing_cadence="monthly", cost_basis=None, costs_confirmed=False, costs=())
    children = []
    for location, quantity in (("US", 3 if revised else 2), ("India", 5)):
        identity = f"t23-{location}"
        calendar = WorkCalendar(f"synthetic-{location}", "1", ZONES[location],
            start, date(2027, 4, 30),
            (DayHours(Decimal("8"), Decimal("8"), Decimal("8")),) * 5
            + (DayHours(Decimal("0"), Decimal("0"), Decimal("0")),) * 2)
        assignment = StaffingAssignment(assignment_id="half-time-team", component_id=identity,
            source_id=common["source_id"], source_version=common["source_version"],
            profile_version="1", policy_version=common["policy_version"], role="Engineer",
            location=location, timezone=ZONES[location], currency="USD", quantity=quantity,
            allocation=Decimal("0.5"), calendar=calendar,
            bill_rate=Decimal("293.17"), cost_rate=Decimal("83.29"),
            rate_version="synthetic-bill-v1", cost_version="synthetic-cost-v1", start=common["service_start"], end=common["service_end"])
        child_terms = common | dict(cost_basis="Declared synthetic monthly team budget", costs_confirmed=True,
            costs=tuple(PeriodCost(f"{identity}-{month.isoformat()}", month, location, Decimal("4317.29"))
                        for month in months))
        pricing = FixedFee(Decimal("187643.53"),
            tuple(FeeAllocation(month, location, Decimal("1")) for month in months),
            "Explicit equal service-month allocation", Decimal("0.01"))
        children.append(PricingComponent(component_id=identity, profile="fixed_assignment",
            timezone=ZONES[location], pricing=pricing, staffing=(assignment,), **child_terms))
    return PricingComponent(component_id="t23-root", profile="hybrid", timezone=ZONES["US"],
        pricing=HybridPricing(tuple(children)), **common)


def roster():
    people = []
    for key, location, allocation in (
        ("us-full", "US", "1"), ("india-half-1", "India", "0.5"),
        ("india-half-2", "India", "0.5"), ("india-half-3", "India", "0.5"),
        ("india-half-4", "India", "0.5"), ("india-quarter", "India", "0.25"),
    ):
        people.append(dict(person_key=key, display_name=f"Synthetic {key}", role="Engineer",
            skills=["python"], level="Senior", location=location, timezone=ZONES[location],
            evidence=[f"Declared synthetic managed roster {key}"], intervals=[dict(kind="gross",
                allocation=allocation, start_date="2026-11-01", end_date="2027-04-30", assignment_key=None)]))
    return dict(source_system="t23-private-half-time", source_as_of="2026-10-02T00:00:00Z",
                basis="gross_with_commitments", people=people)


async def seed(url):
    from app.auth import AuthUser
    from app.gm.demand_source import line_key
    from app.models.user import User
    from app.services.commercial_models import COMPONENT
    from app.services.forecast_plans import PlanInput, save_plan
    from app.services.test_fixtures import create_fixture

    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {
        "application_name": "s21-pub-private-fixture", "statement_timeout": "15000", "lock_timeout": "5000"}})
    email = "t23-half-time@example.test"
    groups = ["SystemAdmin", "HR", "Delivery", "officeapp-e2e"]
    try:
        async with engine.begin() as connection:
            actual = (await connection.execute(text("SELECT current_database(), current_user, "
                "pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()"))).one()
            require(tuple(actual) == (url.database, "s21", "s21"), "Connected database/user/owner mismatch")
            present = set(await connection.run_sync(lambda conn: inspect(conn).get_table_names(schema="public")))
            require(set(TABLES) | {"alembic_version"} <= present, "Lead must migrate required tables first")
            require((await connection.execute(text("SELECT count(*) FROM alembic_version"))).scalar_one() == 1,
                    "Require one recorded Alembic head")
            await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": url.database})
            await connection.execute(text("LOCK TABLE " + ", ".join(f'"{table}"' for table in TABLES)
                                          + " IN SHARE ROW EXCLUSIVE MODE"))
            occupied = {}
            for table in TABLES:
                count = (await connection.execute(text(f'SELECT count(*) FROM "{table}"'))).scalar_one()
                if count:
                    occupied[table] = count
            require(not occupied, "Refusing nonempty target; no writes: " + json.dumps(occupied, sort_keys=True))
            # save_plan commits its service transaction; retain atomic seed via a savepoint.
            async with AsyncSession(bind=connection, expire_on_commit=False,
                                    join_transaction_mode="create_savepoint") as session:
                user = User(id=uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}"), email=email,
                            name="local-test", groups=groups)
                session.add(user)
                await session.flush()
                issued = await create_fixture(session, actor_id=user.id, label="T23 Half-Time Company X",
                                              reviewer_ids=[user.id], hours=4)
                inputs = COMPONENT.dump_python(component(), mode="json")
                title = "T23 Synthetic Company X Half-Time Team"
                body = PlanInput(account_id=issued["client_id"], opportunity_id=issued["opportunity_id"],
                    title=title, idempotency_key=uuid.uuid4(), inputs=inputs, probability="0.70",
                    probability_source="Declared synthetic seventy-percent sales assumption", lifecycle="tentative",
                    assumptions=["Two US and five India half-time roles with explicit synthetic fixed fees and monthly costs"],
                    change_reason="Create synthetic source only for connected part-time capacity proof")
                revised_inputs = COMPONENT.dump_python(component(revised=True), mode="json")
                version = await save_plan(session, actor=AuthUser(id=user.id, email=email, name=user.name,
                    groups=tuple(groups)), body=body)
                for table in ("demand_publication", "people_import_batch", "sourcing_draft", "task"):
                    count = (await session.execute(text(f'SELECT count(*) FROM "{table}"'))).scalar_one()
                    require(count == 0, f"Unexpected seeded business outcome: {table}")
                manifest = dict(database=url.database, tenant=url.database, actor_email=email,
                    actor_id=str(user.id), actor_groups=groups, account_id=str(issued["client_id"]),
                    opportunity_id=str(issued["opportunity_id"]), plan_id=str(version.plan_id),
                    plan_version_id=str(version.id), title=title,
                    fixture_grant={key: str(value) for key, value in issued.items()},
                    original_inputs=inputs, bound_inputs=version.component_inputs, roster=roster(),
                    plan_request=body.model_dump(mode="json"), revised_inputs=revised_inputs,
                    revision_body=body.model_copy(update={"expected_version_id": version.id,
                        "idempotency_key": uuid.uuid4(), "inputs": revised_inputs,
                        "assumptions": ["Three US and five India half-time roles, December through April"],
                        "change_reason": "Synthetic December start and three US half-time roles"}).model_dump(mode="json"),
                    sentinels=["187643.53", "4317.29", "293.17", "83.29"],
                    financial_sentinels={"values": ["187643.53", "4317.29", "293.17", "83.29"],
                        "paths": ["pricing.components[].pricing.total_fee", "pricing.components[].costs[].amount",
                                  "pricing.components[].staffing[].bill_rate", "pricing.components[].staffing[].cost_rate"],
                        "forbidden_fields": ["commercial_inputs", "commercial_snapshot", "cost", "costs",
                            "cost_rate", "hourly_cost", "bill_rate", "hourly_bill_rate", "total_fee", "salary",
                            "known_cost", "unavoidable_cost", "gm"]},
                    revised_expected={"start": "2026-12-01", "end_exclusive": "2027-05-01",
                        "headcount": 8, "required_fte": "4", "matched_fte": "2.5", "gap_fte": "1.5",
                        "us": {"quantity": 3, "matched_quantity": 1, "gap_quantity": 2, "gap_fte": "1",
                               "sourcing_by": "2026-10-17"},
                        "india": {"quantity": 5, "matched_quantity": 4, "gap_quantity": 1, "gap_fte": "0.5",
                                  "sourcing_by": "2026-11-01"}},
                    publication_body=dict(plan_id=str(version.plan_id), expected_source_version_id=str(version.id),
                        expected_publication_version_id=None, request_key=str(uuid.uuid4()),
                        reason="Publish declared half-time staffing with reviewed capability evidence",
                        enrichments={line_key(f"t23-{location}", "half-time-team"):
                            dict(skills=["python"], level="Senior", evidence=[f"Synthetic {location} capability review"])
                            for location in ZONES}),
                    expected=dict(start="2026-11-01", end_exclusive="2027-05-01", headcount=7,
                        months=["2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"],
                        us_person_keys=["us-full"],
                        india_person_keys=["india-half-1", "india-half-2", "india-half-3", "india-half-4"],
                        required_fte="3.5", matched_fte="2.5", gap_fte="1", is_reservation=False,
                        us=dict(quantity=2, matched_quantity=1, gap_quantity=1, required_fte="1",
                                matched_fte="0.5", gap_fte="0.5", matched_person_keys=["us-full"]),
                        india=dict(quantity=5, matched_quantity=4, gap_quantity=1, required_fte="2.5",
                            matched_fte="2", gap_fte="0.5",
                            matched_person_keys=["india-half-1", "india-half-2", "india-half-3", "india-half-4"]),
                        unmatched_person_keys=["india-quarter"], probabilities=["0.70", "0.40"],
                        before=dict(publications=0, imports=0, sourcing_drafts=0)),
                    boundary="Declared synthetic staffing source, not CRM/extraction/provider proof; financial inputs are synthetic disclosure sentinels")
                await session.commit()
        print(json.dumps(manifest, indent=2, sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed(target()))
