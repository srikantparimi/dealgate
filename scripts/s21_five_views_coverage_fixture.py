"""Isolated coverage-control prerequisites, explicitly not signature workflow proof."""
import asyncio
import copy
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
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

from s21_five_views_fixture import ROOT, SUPPORTED_REVISION, component


def require(value, message):
    if not value:
        raise RuntimeError(message)


def coverage_component():
    from app.gm.commercial import calculate_component
    from app.services.commercial_models import parse_component
    inputs = component("a")
    engineer = copy.deepcopy(inputs["staffing"][0])
    engineer.update(assignment_id="engineer", role="Engineer", quantity=2)
    analyst = copy.deepcopy(engineer)
    analyst.update(assignment_id="analyst", role="Analyst")
    inputs["staffing"] = [engineer, analyst]
    result = calculate_component(parse_component(inputs))
    require(result.status == "ok" and not result.missing, "Coverage source must calculate completely")
    require([row.cost for row in result.rows] == [Decimal("772"), Decimal("740"), Decimal("836")],
            "Four staffed people plus100 overhead must match literal calendar costs")
    require(sum(row.revenue for row in result.rows) == Decimal("600"), "Literal600 revenue must remain")
    return inputs


def configuration():
    require(len(sys.argv) == 1 and os.environ.get("DEALGATE_ENV") == "local", "Standalone local invocation required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    manifest = json.loads(Path(os.environ["S21_VIEWS_MANIFEST"]).read_text())
    output = Path(os.environ["S21_VIEWS_COVERAGE_MANIFEST"])
    require(output.parent.resolve() == Path("/tmp").resolve() and not output.exists() and not output.is_symlink(),
            "Fresh exclusive /tmp receipt required")
    raw = os.environ["S21_COVERAGE_DATABASE_URL"]
    url = make_url(raw)
    require((url.drivername, url.username, url.host, url.port) == ("postgresql+asyncpg", "s21", "127.0.0.1", 55421)
            and not url.query and not url.password, "Exact local private target required")
    require(re.fullmatch(r"s21_cov_37eb[0-9a-f]{28}", url.database or ""), "Only authorized37eb clone allowed")
    require(url.database == manifest["database"] == manifest["tenant"] == os.environ.get("DEALGATE_TENANT_ID"),
            "Manifest/database/tenant mismatch")
    os.environ.update(POSTGRES_URL=raw, DATABASE_URL=raw, PYTHONDONTWRITEBYTECODE="1", AWS_EC2_METADATA_DISABLED="true")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url, manifest, output


async def seed(url, original, output):
    from app.models.approval import ApprovalPackage
    from app.models.client import Client
    from app.models.opportunity import Opportunity
    from app.models.sow import Sow, SowVersion
    from app.services.commercial_models import save_commercial_model
    from app.services.policy import active_policy
    from app.services.project_lifecycle import create_or_link
    from app.services.provenance import wrap
    from app.services.test_fixtures import account_scope

    inputs = coverage_component()  # All calculation checks precede API/DB writes.
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{original['actor_email']}")
    run_id, now = str(uuid.uuid4()), datetime.now(UTC)
    record = dict(database=url.database, tenant=url.database, actor_email=original["actor_email"], actor_id=str(actor_id),
        run_id=run_id, status="intent", operations=[], start="2027-01-01", end="2027-03-31",
        fixture_boundary="Explicitly seeded released package; no extraction/signature/release proof",
        expected=dict(project_heads=4, plan_heads=4, combined_heads_before_coverage=8,
                      roles={"Engineer": 2, "Analyst": 2}, revenue="600", monthly_costs=["772", "740", "836"]))
    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {"application_name": "s21-coverage-controls-fixture"}})
    try:
        async with engine.connect() as connection:
            identity = (await connection.execute(text("SELECT current_database(), current_user, pg_get_userbyid(datdba), "
                "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))).one()
            require(tuple(identity) == (url.database, "s21", "s21", f"owned-s21-t21:{url.database.removeprefix('s21_cov_')}"), "Ownership marker mismatch")
            heads = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            require(heads == [SUPPORTED_REVISION], "Exact supported schema required")
        with output.open("x") as receipt:
            def checkpoint():
                receipt.seek(0)
                json.dump(record, receipt, sort_keys=True, indent=2)
                receipt.truncate()
                receipt.flush()
                os.fsync(receipt.fileno())
            checkpoint()
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8210", timeout=45, trust_env=False,
                                         headers={"X-Test-User": original["actor_email"]}) as client:
                try:
                    preflight = await client.get("/forecast/plans", params={"account_id": original["account_a_id"]})
                    require(preflight.status_code == 200 and any(row["id"] == original["plan_a_id"]
                        for row in preflight.json()["items"]), "API private fixture scope mismatch")
                    body = dict(label=f"Coverage controls C {run_id}", reviewer_ids=[str(actor_id)], hours=4)
                    record["operations"].append(dict(path="/dev/test-fixtures", body=body, status="intent"))
                    checkpoint()
                    issued = await client.post("/dev/test-fixtures", json=body)
                    record["operations"][-1].update(status=issued.status_code, response=issued.json())
                    checkpoint()
                    require(issued.status_code == 201, "Fixture issuance failed; preserve receipt")
                    grant = issued.json()
                    deal_id, account_id = uuid.UUID(grant["opportunity_id"]), uuid.UUID(grant["client_id"])
                    record.update(account_id=str(account_id), deal_id=str(deal_id), opportunity_id=str(deal_id))
                    checkpoint()
                    async with engine.begin() as connection:
                        async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                            deal = await session.get(Opportunity, deal_id)
                            account = await session.get(Client, account_id)
                            scope = await account_scope(session, account_id, opportunity_id=deal_id)
                            require(deal is not None and deal.owner_id == actor_id and scope is not None and actor_id in scope,
                                    "New source must belong to freshly issued trusted fixture")
                            sow = Sow(opportunity_id=deal_id, version_counter=1)
                            session.add(sow)
                            await session.flush()
                            title = f"Coverage controls C {run_id}"
                            digest = hashlib.sha256(title.encode()).hexdigest()
                            version = SowVersion(sow_id=sow.id, version_no=1, uploaded_by=actor_id, file_s3_key="",
                                file_hash=digest, extract_status="complete", confirmed_by=actor_id, confirmed_at=now,
                                engagement_type_confirmed="assessment", extracted_fields={
                                    "sow_title": wrap(title, provenance="manual", status="confirmed"),
                                    "scope_summary": wrap("Synthetic two Engineers/two Analysts January-March", provenance="manual", status="confirmed"),
                                    "price": wrap("600", provenance="manual", status="confirmed"),
                                    "currency": wrap("USD", provenance="manual", status="confirmed")})
                            session.add(version)
                            await session.flush()
                            policy = await active_policy(session)
                            bound = copy.deepcopy(inputs)
                            for item in [bound, *bound["staffing"]]:
                                item.update(source_id=str(sow.id), source_version=str(version.id),
                                            policy_version=str(policy.id) if policy.id else "blueprint-defaults-v1")
                            gm = await save_commercial_model(session, opportunity_id=deal_id, actor_id=actor_id,
                                sow_version_id=version.id, expected_gm_model_id=None, inputs=bound,
                                change_reason="Synthetic released source prerequisite for real staffing coverage controls")
                            package = ApprovalPackage(opportunity_id=deal_id, sow_version_id=version.id, gm_model_id=gm.id,
                                package_hash=digest, status="released", submitted_by=actor_id, released_at=now)
                            session.add(package)
                            await session.flush()
                            project, created = await create_or_link(session, actor_id=actor_id, package=package)
                            require(created, "New fixture must not reuse another project")
                            await session.commit()
                            seeded = dict(account_name=account.name, deal_title=deal.name,
                                project_id=str(project.id), project_title=project.title, sow_id=str(sow.id),
                                sow_version_id=str(version.id), gm_model_id=str(gm.id), package_id=str(package.id))
                    record.update(seeded)
                    checkpoint()
                    plan_body = dict(account_id=str(account_id), opportunity_id=str(deal_id), title=f"Mirror {title}",
                        idempotency_key=str(uuid.uuid5(uuid.UUID(run_id), "coverage-mirror-plan")), inputs=inputs,
                        probability="0.5", probability_source="Synthetic explicit assumption", lifecycle="tentative",
                        assumptions=["Mirror two Engineers/two Analysts January-March for explicit coverage mapping"],
                        change_reason="Create separate forecast proposal for coverage control proof")
                    record["operations"].append(dict(path="/forecast/plans", body=plan_body, status="intent"))
                    checkpoint()
                    planned = await client.post("/forecast/plans", json=plan_body)
                    record["operations"][-1].update(status=planned.status_code, response=planned.json())
                    checkpoint()
                    require(planned.status_code == 201, "Plan creation failed; preserve immutable seeded project")
                    record.update(plan_id=planned.json()["id"], plan_version_id=planned.json()["version_id"],
                        plan_title=plan_body["title"], status="ready_for_publication", forecast_worker="pending_lead",
                        capability_enrichment={"Engineer": {"skills": ["python"], "level": "Senior"},
                                               "Analyst": {"skills": ["analysis"], "level": "Senior"}})
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
