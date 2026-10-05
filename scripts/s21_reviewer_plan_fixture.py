"""Declared T05 draft in an empty private database; never seed approval outcomes."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "user", "client", "opportunity", "sow", "sow_version", "gm_model",
    "resource_line", "approval_package", "approval_assignment", "approval",
    "approval_group", "task", "notification", "audit_event", "project", "forecast_plan",
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def target():
    require(len(sys.argv) == 1, "No alternate target arguments accepted")
    require(os.environ.get("DEALGATE_ENV") == "local", "Explicit local environment required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    require(not any(key == "app" or key.startswith("app.") for key in sys.modules),
            "Run standalone before application imports")
    raw = os.environ.get("S21_REVIEW_DATABASE_URL")
    require(raw, "Set S21_REVIEW_DATABASE_URL to the migrated private database")
    url = make_url(raw)
    require((url.drivername, url.username, url.host, url.port) ==
            ("postgresql+asyncpg", "s21", "127.0.0.1", 55421)
            and not url.query and not url.password,
            "Require trust-only asyncpg s21 at literal127.0.0.1:55421 without URL options")
    require(re.fullmatch(r"s21_review_[0-9a-f]{32}", url.database or ""),
            "Refusing non-private database name")
    require(os.environ.get("DEALGATE_TENANT_ID") == url.database,
            "Tenant must exactly equal private database name")
    os.environ.update(POSTGRES_URL=raw, DATABASE_URL=raw, ALLOW_DEV_SEED_ENDPOINT="1",
                      PYTHONDONTWRITEBYTECODE="1", AWS_EC2_METADATA_DISABLED="true")
    os.environ.pop("DEALGATE_TEST_GROUPS", None)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url


async def seed(url):
    from app.models.approval import ApprovalPackage
    from app.models.approval_routing import ApprovalAssignment
    from app.models.opportunity import Opportunity
    from app.models.sow import Sow, SowVersion
    from app.models.task import Task
    from app.models.user import User
    from app.services.approval_routing import save_group
    from app.services.delivery_model import GmModelPayload, ResourceLinePayload, create_gm_model_version
    from app.services.provenance import wrap
    from app.services.test_fixtures import create_fixture
    from sqlalchemy import func, select

    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {
        "application_name": "s21-review-private-fixture", "statement_timeout": "15000",
        "lock_timeout": "5000"}})
    roles = {
        "owner": ["SystemAdmin", "Sales"], "delivery": ["Delivery"],
        "delivery_alternate": ["Delivery", "HR"], "hr": ["HR"], "sales": ["Sales"],
        "finance": ["Finance"], "legal": ["Legal"], "nonmember": ["Sales"],
    }
    functions = ("delivery", "hr", "sales", "finance", "legal")
    people = {}
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            actual = (await connection.execute(text("SELECT current_database(), current_user, "
                "pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()"))).one()
            require(tuple(actual) == (url.database, "s21", "s21"), "Database/user/owner identity mismatch")
            present = set(await connection.run_sync(lambda conn: inspect(conn).get_table_names(schema="public")))
            require(set(TABLES) | {"alembic_version"} <= present, "Lead must migrate all required tables first")
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
            require(not occupied, "Refusing nonempty business/group tables; no writes: " + json.dumps(occupied, sort_keys=True))
            # Service commits release savepoints, never the guarded outer seed
            # transaction. Any failure rolls back the entire newly issued fixture.
            async with AsyncSession(bind=connection, expire_on_commit=False,
                                    join_transaction_mode="create_savepoint") as session:
                for role, groups in roles.items():
                    email = f"t05-{role}@example.test"
                    person = User(id=uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}"),
                        email=email, name=f"T05 {role.replace('_', ' ').title()}",
                        groups=[*groups, "officeapp-e2e"])
                    session.add(person)
                    people[role] = person
                await session.flush()
                issued = await create_fixture(session, actor_id=people["owner"].id,
                    label="Reviewer planning only", reviewer_ids=[u.id for u in people.values()], hours=4)
                deal = await session.get(Opportunity, issued["opportunity_id"])
                deal.governance_status = "SOWDraft.confirmed"
                deal.name = "T05 Synthetic Reviewer Planning"
                sow = Sow(opportunity_id=deal.id, version_counter=1)
                session.add(sow)
                await session.flush()
                declared = "T05 synthetic confirmed draft: 100 US hours at USD240 billed and USD100 cost per hour."
                version = SowVersion(sow_id=sow.id, uploaded_by=people["owner"].id,
                    file_s3_key="", file_hash=hashlib.sha256(declared.encode()).hexdigest(),
                    version_no=1, uploaded_at=now, extract_status="complete",
                    confirmed_by=people["owner"].id, confirmed_at=now,
                    engagement_type_confirmed="tm", extracted_fields={
                        "sow_title": wrap("T05 Synthetic Reviewer Planning", provenance="manual", status="confirmed"),
                        "scope_summary": wrap(declared, provenance="manual", status="confirmed"),
                        "price": wrap("24000.00", provenance="manual", status="confirmed"),
                        "currency": wrap("USD", provenance="manual", status="confirmed"),
                    })
                session.add(version)
                await session.flush()
                gm = await create_gm_model_version(session, actor_id=people["owner"].id,
                    opportunity_id=deal.id, commit=False,
                    payload=GmModelPayload(engagement_type="tm", sow_version_id=version.id,
                        delivery_pattern="us_only", contingency_pct=Decimal("0"), warranty_days=0,
                        resource_lines=[ResourceLinePayload(role="Engineer", seniority="senior", location="US",
                            person_name="Synthetic Engineer", allocation_pct=Decimal("1"),
                            start_date=date(2026, 10, 1), end_date=date(2026, 10, 31),
                            hours_billable=Decimal("100"), hourly_bill_rate=Decimal("240"),
                            hourly_cost=Decimal("100"), validated_by=people["hr"].id)], cost_lines=[]))
                roster = {}
                for function in functions:
                    eligible = [people[function].id]
                    if function in {"delivery", "hr"}:
                        eligible.append(people["delivery_alternate"].id)
                    await save_group(session, actor_id=people["owner"].id, function=function,
                        member_ids=[str(value) for value in eligible], backup_ids=[],
                        default_approver_id=str(people[function].id))
                    roster[function] = {"default_id": str(people[function].id),
                                        "eligible_ids": [str(value) for value in eligible]}
                for model in (ApprovalPackage, ApprovalAssignment, Task):
                    require(await session.scalar(select(func.count()).select_from(model)) == 0,
                            f"Unexpected precreated outcome in {model.__tablename__}")
                await session.commit()
                manifest = {"database": url.database, "tenant": url.database,
                    "boundary": "declared synthetic confirmed source; no upload, extraction, S3 or approval outcome proof",
                    "actor_email": people["owner"].email, "actor_id": str(people["owner"].id),
                    "unauthorized_email": people["nonmember"].email,
                    "unauthorized_id": str(people["nonmember"].id),
                    "opportunity_id": str(deal.id), "name": deal.name, "title": deal.name,
                    "reviewer_ids": {function: str(people[function].id) for function in functions},
                    "delivery_alternative_id": str(people["delivery_alternate"].id),
                    "fixture_grant": {key: str(value) for key, value in issued.items()},
                    "actors": {role: {"id": str(person.id), "email": person.email, "name": person.name,
                                      "groups": person.groups} for role, person in people.items()},
                    "deal_id": str(deal.id), "sow_id": str(sow.id), "sow_version_id": str(version.id),
                    "gm_model_id": str(gm.id), "sow_version": 1, "gm_version": 1,
                    "approvals_path": f"/sows/{deal.id}/approvals", "roster": roster,
                    "invalid_reviewer_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url.database}:not-a-user")),
                    "expected": {"revenue_usd": "24000.00", "cost_usd": "10000.00",
                        "profit_usd": "14000.00", "requires_ceo": False,
                        "before": {"packages": 0, "assignments": 0, "tasks": 0},
                        "after_submit": {"packages": 1, "assignments": 5, "tasks": 3,
                            "status": "pending_delivery_hr",
                            "task_owners": [str(people[key].id) for key in ("delivery_alternate", "hr", "sales")],
                            "assignments": {fn: str(people["delivery_alternate" if fn == "delivery" else fn].id)
                                            for fn in functions}},
                        "invalid_selection_status": 422, "unauthorized_submitter_status": 403}}
        print(json.dumps(manifest, indent=2, sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed(target()))
