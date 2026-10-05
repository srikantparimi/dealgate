"""Persist the accepted preview in an empty, ownership-marked local database."""
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
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def configuration():
    require(len(sys.argv) == 1 and os.environ.get("DEALGATE_ENV") == "local", "Explicit local invocation required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG overrides")
    url = make_url(os.environ["S21_PREVIEW_DATABASE_URL"])
    require((url.drivername, url.username, url.host, url.port) == ("postgresql+asyncpg", "s21", "127.0.0.1", 55421)
            and not url.password and not url.query, "Exact owned local target required")
    require(re.fullmatch(r"s21_preview_[0-9a-f]{32}", url.database or ""), "New preview database required")
    require(os.environ.get("DEALGATE_TENANT_ID") == url.database, "Explicit matching tenant required")
    output = Path(os.environ["S21_PREVIEW_MANIFEST"])
    require(output.parent.resolve() == Path("/tmp").resolve() and not output.exists() and not output.is_symlink(),
            "Fresh exclusive /tmp receipt required; inspect partial operations before recovery")
    os.environ.update(POSTGRES_URL=str(url), DATABASE_URL=str(url), AWS_EC2_METADATA_DISABLED="true", PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url, output


async def seed(url, output):
    from s21_preview_confirmed_inputs import confirmed_records
    from s21_preview_inputs import AS_OF, EXPECTED
    from app.models.approval import ApprovalPackage
    from app.models.client import Client
    from app.models.direct_cost_settings import DirectCostSettings
    from app.models.opportunity import Opportunity
    from app.models.sow import Sow, SowVersion
    from app.models.user import User
    from app.services.policy import active_policy
    from app.services.project_lifecycle import create_or_link
    from app.services.provenance import wrap
    from app.services.test_fixtures import account_scope

    items = confirmed_records(location="US", timezone="America/New_York")
    run_id = uuid.UUID(url.database.removeprefix("s21_preview_"))
    actor = f"t19-preview-{run_id.hex[:8]}@example.test"
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{actor}")
    record = dict(database=url.database, tenant=url.database, run_id=str(run_id), actor_email=actor,
        actor_id=str(actor_id), as_of=AS_OF, expected=EXPECTED, accounts={}, sources=[], operations=[], status="intent",
        boundary="Signed source states explicitly seeded; real commercial API saves and plan workers, not approval/signature proof")
    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {"application_name": "s21-preview-fixture"}})
    try:
        async with engine.connect() as connection:
            identity = (await connection.execute(text("SELECT current_database(),current_user,pg_get_userbyid(datdba),"
                "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))).one()
            require(tuple(identity) == (url.database, "s21", "s21", f"owned-s21-preview:{run_id}"), "Database ownership mismatch")
            require((await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
                    == ["20261003_0062_actual_coverage"], "Exact supported schema required")
        async with AsyncSession(engine) as session:
            require(await session.scalar(select(func.count()).select_from(Client)) == 0, "Database must have zero clients before preview seeding")
        with output.open("x") as receipt:
            def checkpoint():
                receipt.seek(0)
                json.dump(record, receipt, sort_keys=True, indent=2)
                receipt.truncate()
                receipt.flush()
                os.fsync(receipt.fileno())
            checkpoint()
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8210", timeout=45, trust_env=False,
                                         headers={"X-Test-User": actor}) as api:
                async def request(method, path, body=None, expected=200):
                    operation = dict(method=method, path=path, body=body, status="intent")
                    record["operations"].append(operation)
                    checkpoint()
                    response = await api.request(method, path, json=body)
                    operation.update(status=response.status_code, response=response.json())
                    checkpoint()
                    require(response.status_code == expected, f"{method} {path} returned{response.status_code}; preserve receipt")
                    return response.json()
                try:
                    probe = f"probe-{run_id.hex[:24]}"
                    async with AsyncSession(engine) as session:
                        require(await session.get(DirectCostSettings, "direct_cost_categories") is None,
                                "Fresh database must not contain category settings")
                        # The API must read our nonce before it receives any write request.
                        session.add(User(id=actor_id, email=actor, name=actor, groups=["SystemAdmin", "Finance", "officeapp-e2e"]))
                        await session.flush()
                        session.add(DirectCostSettings(key="direct_cost_categories", categories=[probe], updated_by=actor_id))
                        await session.commit()
                    try:
                        binding = await request("GET", "/settings/direct-cost-categories")
                        require(binding == {"categories": [probe]}, "API is not bound to the owned database")
                    finally:
                        async with AsyncSession(engine) as session:
                            row = await session.get(DirectCostSettings, "direct_cost_categories", with_for_update=True)
                            require(row is not None and row.categories == [probe], "Binding probe changed; inspect before recovery")
                            await session.delete(row)
                            await session.commit()
                    population = await request("GET", "/forecast/plans?size=1")
                    require(population["total"] == 0, "API must expose the empty owned population")
                    for item in items:
                        source = dict(key=item["id"], title=item["title"], client=item["client"],
                            lifecycle=item["lifecycle"], inputs=copy.deepcopy(item["inputs"]), status="intent")
                        record["sources"].append(source)
                        checkpoint()
                        if item["lifecycle"] == "signed":
                            grant = await request("POST", "/dev/test-fixtures", dict(label=item["client"], reviewer_ids=[str(actor_id)], hours=8), 201)
                            account_id, deal_id = uuid.UUID(grant["client_id"]), uuid.UUID(grant["opportunity_id"])
                            sow_id, version_id = (uuid.uuid5(run_id, f"{item['id']}:{suffix}") for suffix in ("sow", "version"))
                            source.update(account_id=str(account_id), opportunity_id=str(deal_id), sow_id=str(sow_id), sow_version_id=str(version_id))
                            record["accounts"][item["client"]] = dict(id=str(account_id), opportunity_id=str(deal_id))
                            checkpoint()
                            async with engine.begin() as connection:
                                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                                    scope = await account_scope(session, account_id, opportunity_id=deal_id)
                                    require(scope is not None and actor_id in scope, "Fresh trusted fixture grant required")
                                    account, deal = await session.get(Client, account_id), await session.get(Opportunity, deal_id)
                                    account.name, deal.name = item["client"], item["title"]
                                    session.add(Sow(id=sow_id, opportunity_id=deal_id, version_counter=1))
                                    await session.flush()
                                    now = datetime.now(UTC)
                                    session.add(SowVersion(id=version_id, sow_id=sow_id, version_no=1, uploaded_by=actor_id,
                                        file_s3_key="", file_hash=hashlib.sha256(item["id"].encode()).hexdigest(), extract_status="complete",
                                        confirmed_by=actor_id, confirmed_at=now,
                                        extracted_fields={"sow_title": wrap(item["title"], provenance="manual", status="confirmed"),
                                            "scope_summary": wrap(item["evidence"], provenance="manual", status="confirmed"),
                                            "price": wrap(str(sum(map(Decimal, item["revenue"]))), provenance="manual", status="confirmed"),
                                            "currency": wrap("USD", provenance="manual", status="confirmed")}))
                                    policy = await active_policy(session)
                                    for row in [source["inputs"], *source["inputs"]["staffing"]]:
                                        row.update(source_id=str(sow_id), source_version=str(version_id),
                                            policy_version=str(policy.id) if policy.id else "blueprint-defaults-v1")
                                    await session.commit()
                            source["status"] = "confirmed_sow_prerequisite"
                            checkpoint()
                            model = (await request("POST", f"/delivery-model/{deal_id}/commercial/versions",
                                dict(sow_version_id=str(version_id), expected_gm_model_id=None, inputs=source["inputs"],
                                    change_reason="Explicit synthetic accepted-preview financial fixture, not extraction or HR approval"), 201))["gm_model"]
                            require(model["commercial_snapshot"]["schedule"]["status"] == "ok", "Signed fixture calculation incomplete")
                            source["gm_model_id"] = model["id"]
                            reloaded = (await request("GET", f"/delivery-model/{deal_id}"))["gm_model"]
                            require(reloaded["id"] == model["id"] and reloaded["commercial_inputs"] == model["commercial_inputs"], "Saved inputs did not survive real API reload")
                            package_id = uuid.uuid5(run_id, f"{item['id']}:package")
                            source["package_id"] = str(package_id)
                            checkpoint()
                            async with engine.begin() as connection:
                                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                                    package = ApprovalPackage(id=package_id, opportunity_id=deal_id, sow_version_id=version_id,
                                        gm_model_id=uuid.UUID(model["id"]), package_hash=hashlib.sha256(item["id"].encode()).hexdigest(),
                                        status="released", submitted_by=actor_id, released_at=datetime.now(UTC))
                                    session.add(package)
                                    await session.flush()
                                    project, created = await create_or_link(session, actor_id=actor_id, package=package)
                                    require(created, "Owned new source must create a new project")
                                    await session.commit()
                                    source["project_id"] = str(project.id)
                            source["status"] = "signed_prerequisite_ready"
                        else:
                            account = record["accounts"][item["client"]]
                            source.update(account_id=account["id"], opportunity_id=account["opportunity_id"])
                            checkpoint()
                            plan = await request("POST", "/forecast/plans", dict(account_id=account["id"], opportunity_id=account["opportunity_id"],
                                title=item["title"], inputs=source["inputs"], probability=item["probability"],
                                probability_source=item["probability_source"], lifecycle=item["lifecycle"],
                                assumptions=list(item.get("assumptions", ())) + item["fixture_assumptions"],
                                idempotency_key=str(uuid.uuid5(run_id, item["id"])), change_reason="Accepted preview synthetic planning source"), 201)
                            source.update(plan_id=plan["id"], plan_version_id=plan["version_id"], status="pending_worker")
                        checkpoint()
                    record["status"] = "ready_for_separate_worker"
                except Exception as error:
                    record.update(status="failed_preserved", error=f"{type(error).__name__}: {error}")
                    checkpoint()
                    raise
                checkpoint()
        print(json.dumps({"manifest": str(output), "status": record["status"], "database": url.database}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed(*configuration()))
