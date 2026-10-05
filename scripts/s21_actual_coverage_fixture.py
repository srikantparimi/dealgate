"""Private-clone financial workflow fixture; seeded signature is NOT provider proof."""
import asyncio
from calendar import monthrange
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def target():
    require(len(sys.argv) == 1, "No alternate arguments accepted")
    require(os.environ.get("DEALGATE_ENV") == "local", "Explicit local environment required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    require(not any(key == "app" or key.startswith("app.") for key in sys.modules), "Standalone process required")
    raw = os.environ.get("S21_COVERAGE_DATABASE_URL")
    require(raw, "Set S21_COVERAGE_DATABASE_URL")
    url = make_url(raw)
    require((url.drivername, url.username, url.host, url.port) ==
        ("postgresql+asyncpg", "s21", "127.0.0.1", 55421) and not url.query and not url.password,
        "Require literal trust-only private asyncpg target")
    require(re.fullmatch(r"s21_cov_[0-9a-f]{32}", url.database or ""), "Refusing non-private database")
    require(os.environ.get("DEALGATE_TENANT_ID") == url.database, "Tenant must match private database")
    require(os.environ.get("DEALGATE_REPORTING_CURRENCY") == "USD", "Fixture explicitly requires USD reporting")
    require(os.environ.get("DEALGATE_REPORTING_TIMEZONE"), "Explicit reporting timezone required")
    ZoneInfo(os.environ["DEALGATE_REPORTING_TIMEZONE"])
    os.environ.update(POSTGRES_URL=raw, DATABASE_URL=raw, ALLOW_DEV_SEED_ENDPOINT="1",
                      AWS_EC2_METADATA_DISABLED="true", PYTHONDONTWRITEBYTECODE="1")
    os.environ.pop("DEALGATE_TEST_GROUPS", None)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
    return url


async def seed(url):
    from app.audit import append_audit
    from app.models.actual import FinancialActual, FinancialImportBatch
    from app.models.approval import ApprovalPackage
    from app.models.opportunity import Opportunity
    from app.models.signed_sow import SignedSowUpload
    from app.models.sow import Sow, SowVersion
    from app.models.user import User
    from app.services.commercial_models import save_commercial_model
    from app.services.policy import active_policy
    from app.services.provenance import wrap
    from app.services.test_fixtures import create_fixture

    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {
        "application_name": "s21-coverage-private-fixture", "statement_timeout": "15000", "lock_timeout": "5000"}})
    emails = ("t21-coverage-finance@example.test", "t21-coverage-finance-two@example.test")
    ids = [uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}") for email in emails]
    now = datetime.now(UTC)
    today = now.astimezone(ZoneInfo(os.environ["DEALGATE_REPORTING_TIMEZONE"])).date()
    month, end = today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1])
    title = "T21 Synthetic Certified Actual Coverage"
    try:
        async with engine.begin() as connection:
            target_info = (await connection.execute(text("SELECT current_database(), current_user, "
                "pg_get_userbyid(datdba), shobj_description(oid, 'pg_database') FROM pg_database "
                "WHERE datname=current_database()"))).one()
            require(tuple(target_info) == (url.database, "s21", "s21", f"owned-s21-t21:{url.database.removeprefix('s21_cov_')}"),
                    "Database identity/owner/ownership marker mismatch")
            heads = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            require(heads == ["20261003_0062_actual_coverage"], "Lead must apply the0062 coverage migration")
            await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{url.database}:t21-coverage-fixture"})
            async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                existing = await session.scalar(select(User.id).where((User.id.in_(ids)) | (User.email.in_(emails))).limit(1))
                source = await session.scalar(select(Opportunity.id).where(Opportunity.name == title).limit(1))
                require(existing is None and source is None, "Fixture actor/source already exists; refusing duplicate seed")
                before = [await session.scalar(select(func.count()).select_from(model))
                          for model in (FinancialActual, FinancialImportBatch)]
                owner = User(id=ids[0], email=emails[0], name="local-test", groups=["Finance", "SystemAdmin", "officeapp-e2e"])
                second = User(id=ids[1], email=emails[1], name="T21 Second Finance", groups=["Finance", "officeapp-e2e"])
                session.add_all([owner, second])
                await session.flush()
                issued = await create_fixture(session, actor_id=owner.id, label="T21 Certified Actual Coverage",
                                              reviewer_ids=ids, hours=4)
                deal = await session.get(Opportunity, issued["opportunity_id"])
                deal.name, deal.governance_status = title, "SOWDraft.confirmed"
                sow = Sow(opportunity_id=deal.id, version_counter=1)
                session.add(sow)
                await session.flush()
                declared = "Synthetic confirmed single service month: revenue24000 and delivery cost10000 USD"
                source_hash = hashlib.sha256(declared.encode()).hexdigest()
                version = SowVersion(sow_id=sow.id, version_no=1, uploaded_by=owner.id, uploaded_at=now,
                    file_s3_key="", file_hash=source_hash, extract_status="complete", confirmed_by=owner.id,
                    confirmed_at=now, engagement_type_confirmed="assessment", extracted_fields={
                        "sow_title": wrap(title, provenance="manual", status="confirmed"),
                        "scope_summary": wrap(declared, provenance="manual", status="confirmed"),
                        "price": wrap("24000", provenance="manual", status="confirmed"),
                        "currency": wrap("USD", provenance="manual", status="confirmed")})
                session.add(version)
                await session.flush()
                policy = await active_policy(session)
                inputs = dict(component_id="coverage-service", version="1", source_id=str(sow.id),
                    source_version=str(version.id), workstream_id="single-service-month", profile="fixed_assignment",
                    profile_version="1", policy_version=str(policy.id) if policy.id else "blueprint-defaults-v1",
                    source_evidence=["Declared synthetic confirmed coverage fixture; no real uploaded document"],
                    service_start=month.isoformat(), service_end=end.isoformat(),
                    timezone=os.environ["DEALGATE_REPORTING_TIMEZONE"], currency="USD", billing_cadence="monthly",
                    cost_basis="Explicit synthetic confirmed delivery cost", costs_confirmed=True,
                    costs=[dict(source_id="fixture-team-cost", month=month.isoformat(), location="US", amount="10000")],
                    staffing=[], pricing=dict(total_fee="24000", allocations=[dict(month=month.isoformat(), location="US", weight="1")],
                        allocation_basis="Single confirmed service month", minor_unit="0.01"))
                gm = await save_commercial_model(session, opportunity_id=deal.id, actor_id=owner.id,
                    sow_version_id=version.id, expected_gm_model_id=None, inputs=inputs,
                    change_reason="Declared synthetic signed-source prerequisite for real financial import workflow")
                schedule = gm.commercial_snapshot["schedule"]
                require(len(schedule["rows"]) == 1 and Decimal(schedule["rows"][0]["revenue"]) == Decimal("24000")
                        and Decimal(schedule["rows"][0]["cost"]) == Decimal("10000"), "Computed fixture schedule differs from independent oracle")
                package = ApprovalPackage(opportunity_id=deal.id, sow_version_id=version.id, gm_model_id=gm.id,
                    package_hash=source_hash, status="released", submitted_by=owner.id, released_at=now,
                    policy_version_id=policy.id, routing_policy_version=2)
                session.add(package)
                await session.flush()
                signed = SignedSowUpload(package_id=package.id, file_s3_key="", file_hash=source_hash,
                    uploaded_by=owner.id, uploaded_at=now, verify_status="verified", verified_at=now, released_at=now,
                    verify_reason="Declared synthetic fixture prerequisite; no signature verification executed")
                session.add(signed)
                await append_audit(session, actor_id=owner.id, action="test.actual_coverage_fixture_seeded",
                    entity="approval_package", entity_id=str(package.id), before=None,
                    after={"declared_synthetic": True, "signature_executed": False, "storage_uploaded": False,
                           "reason": "Isolated current-period financial workflow prerequisite"})
                after = [await session.scalar(select(func.count()).select_from(model))
                         for model in (FinancialActual, FinancialImportBatch)]
                require(before == after, "Fixture unexpectedly changed financial actual/import counts")
                await session.commit()
                manifest = dict(database=url.database, tenant=url.database, actor_email=emails[0], second_email=emails[1],
                    actor_id=str(owner.id), second_id=str(second.id), account_id=str(issued["client_id"]),
                    deal_id=str(deal.id), opportunity_id=str(deal.id), sow_id=str(sow.id), sow_version_id=str(version.id),
                    gm_model_id=str(gm.id), gm_id=str(gm.id), package_id=str(package.id), title=title,
                    month=month.isoformat(), through_date=today.isoformat(), source_date=today.isoformat(),
                    cutoff=today.isoformat(), schedule_row=0,
                    timezone=os.environ["DEALGATE_REPORTING_TIMEZONE"], source_schedule=schedule,
                    fixture_grant={key: str(value) for key, value in issued.items()},
                    coverage=dict(sow_version_id=str(version.id), schedule_row=0, fraction_start="0", fraction_end="0.5",
                        through_date=today.isoformat(), basis_evidence="Synthetic Finance confirms half of this exact service scope; not elapsed-day proration"),
                    expected=dict(signed_revenue="24000", signed_cost="10000", recognized_actual="11000.99",
                        delivery_actual="6000", estimated_revenue="23000.99", estimated_cost="11000", profit="12000.99"),
                    fixture_boundary="Seeded released package/signature prerequisite, not extraction/approval/signature/provider proof")
        print(json.dumps(manifest, indent=2, sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed(target()))
