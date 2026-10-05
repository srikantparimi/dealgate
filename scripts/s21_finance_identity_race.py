"""Private PG proof: token group sync must finish during a blocked financial import."""
import asyncio
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


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def configuration():
    require(len(sys.argv) == 1, "No alternate endpoint arguments accepted")
    require(os.environ.get("DEALGATE_ENV") == "local", "Explicit local environment required")
    require(not any(key.startswith("PG") for key in os.environ), "Remove PG* overrides")
    require(not any(key == "app" or key.startswith("app.") for key in sys.modules), "Standalone process required")
    manifest_path = os.environ.get("S21_COV_MANIFEST")
    require(manifest_path, "Set S21_COV_MANIFEST to the existing guarded fixture manifest")
    manifest = json.loads(Path(manifest_path).read_text())
    raw = os.environ.get("S21_COVERAGE_DATABASE_URL")
    require(raw, "Set S21_COVERAGE_DATABASE_URL")
    url = make_url(raw)
    require((url.drivername, url.username, url.host, url.port) ==
            ("postgresql+asyncpg", "s21", "127.0.0.1", 55421) and not url.query and not url.password,
            "Require exact trust-only local asyncpg target")
    require(re.fullmatch(r"s21_cov_[0-9a-f]{32}", url.database or ""), "Refusing non-private database")
    require(manifest["database"] == manifest["tenant"] == url.database == os.environ.get("DEALGATE_TENANT_ID"),
            "Manifest/database/tenant mismatch")
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{manifest['actor_email']}")
    require(str(actor_id) == manifest["actor_id"], "Manifest actor is not the local authenticated identity")
    for key in ("account_id", "gm_model_id"):
        uuid.UUID(manifest[key])
    os.environ.update(POSTGRES_URL=raw, DATABASE_URL=raw, AWS_EC2_METADATA_DISABLED="true",
                      PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
    return url, manifest, actor_id


async def observe_client_wait(engine, blocker_pid):
    deadline = asyncio.get_running_loop().time() + 12
    while asyncio.get_running_loop().time() < deadline:
        # Fresh transaction avoids pg_stat_activity snapshots hiding a new waiter.
        async with engine.connect() as connection:
            waiters = (await connection.execute(text("""
                SELECT pid, wait_event_type, query
                FROM pg_stat_activity
                WHERE datname=current_database() AND pid<>pg_backend_pid()
                  AND :blocker=ANY(pg_blocking_pids(pid))
                  AND wait_event_type='Lock'
                  AND query ILIKE '%client%' AND query ILIKE '%FOR UPDATE%'
            """), {"blocker": blocker_pid})).mappings().all()
        if waiters:
            require(len(waiters) == 1, "Ambiguous client-lock waiter; another workflow is active")
            return dict(waiters[0])
        await asyncio.sleep(0.05)
    raise AssertionError("The real HTTP import did not reach the owned client's FOR UPDATE lock")


async def prove(url, manifest, actor_id):
    from app.auth import AuthUser
    from app.services.user_provisioning import ensure_user

    engine = create_async_engine(url, connect_args={"timeout": 5, "server_settings": {
        "application_name": "s21-finance-identity-race", "statement_timeout": "15000"}})
    run_id = str(uuid.uuid4())
    task = None
    response = None
    failure = None
    observation = None
    groups = ["Finance", "officeapp-e2e"]
    try:
        async with engine.connect() as blocker:
            identity = (await blocker.execute(text("SELECT current_database(), current_user, "
                "pg_get_userbyid(datdba), shobj_description(oid, 'pg_database') FROM pg_database "
                "WHERE datname=current_database()"))).one()
            require(tuple(identity) == (url.database, "s21", "s21", f"owned-s21-t21:{url.database.removeprefix('s21_cov_')}"),
                    "Connected database owner/comment mismatch")
            user = (await blocker.execute(text('SELECT email, name, groups FROM "user" WHERE id=:id'),
                                         {"id": actor_id})).mappings().one()
            require(user["email"] == manifest["actor_email"], "Fixture user mismatch")
            require(user["name"] and "@" in user["email"], "Known non-placeholder identity required")
            owned = (await blocker.execute(text("SELECT gm.id FROM gm_model gm JOIN opportunity o "
                "ON o.id=gm.opportunity_id WHERE gm.id=:gm AND o.client_id=:account"),
                {"gm": uuid.UUID(manifest["gm_model_id"]), "account": uuid.UUID(manifest["account_id"])})).scalar_one_or_none()
            require(owned is not None, "Fixture GM/account source mismatch")
            blocker_pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await blocker.execute(text("SELECT id FROM client WHERE id=:account FOR UPDATE"),
                                  {"account": uuid.UUID(manifest["account_id"])})
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8210", timeout=45,
                                         trust_env=False, follow_redirects=False) as client:
                body = dict(source_system=f"identity-race-{run_id}", idempotency_key=run_id,
                    rows=[dict(account_id=manifest["account_id"], gm_model_id=manifest["gm_model_id"],
                        source_id=f"uncovered-{run_id}", revision=1, expected_previous_revision=0,
                        period_month=manifest["month"], measure="recognized_revenue", amount="1", currency="USD",
                        source_date=manifest["cutoff"], reason="Private same-identity transaction lock regression")])
                task = asyncio.create_task(client.post("/actuals/financial-import", json=body,
                    headers={"X-Test-User": manifest["actor_email"]}))
                try:
                    observation = await observe_client_wait(engine, blocker_pid)
                    async with engine.connect() as check:
                        current = (await check.execute(text('SELECT groups FROM "user" WHERE id=:id'),
                                                       {"id": actor_id})).scalar_one()
                    require(set(current) == {"SystemAdmin", "Finance", "officeapp-e2e"},
                            "API token must first sync Admin+Finance; mismatched groups would make the race vacuous")

                    async def sync_other_token():
                        async with AsyncSession(engine, expire_on_commit=False) as session:
                            await session.execute(text("SET LOCAL statement_timeout='4000ms'"))
                            await ensure_user(session, AuthUser(id=actor_id, email=manifest["actor_email"],
                                name=user["name"], groups=tuple(groups)))
                            await session.commit()

                    await asyncio.wait_for(sync_other_token(), timeout=6)
                    require(not task.done(), "Import must remain blocked until identity sync commits")
                    async with engine.connect() as check:
                        synced = (await check.execute(text('SELECT groups FROM "user" WHERE id=:id'),
                                                      {"id": actor_id})).scalar_one()
                    require(set(synced) == set(groups), "Independent authorized token sync did not commit")
                except Exception as error:
                    failure = f"{type(error).__name__}: {error}"
                finally:
                    # Release only our transaction, even on red; always collect the HTTP task.
                    await blocker.rollback()
                    try:
                        response = await task
                    except Exception as error:
                        failure = f"{failure or ''}; HTTP collection: {type(error).__name__}: {error}"
                report = dict(run_id=run_id, database=url.database, actor_id=str(actor_id),
                    second_token_groups=groups, observed_waiter=observation,
                    http_status=response.status_code if response is not None else None,
                    response=response.json() if response is not None and response.headers.get("content-type", "").startswith("application/json")
                    else response.text if response is not None else None,
                    passed=failure is None and response is not None and response.status_code == 201,
                    failure=failure, preserved=True,
                    boundary="Real local HTTP import plus real ensure_user in independent PG session; local auth, no Cognito token verification")
                print(json.dumps(report, indent=2, default=str), flush=True)
                require(report["passed"], "Identity sync failed to complete while the financial account lock was held")
    finally:
        if task is not None and not task.done():
            # Unexpected outer exceptions still collect the bounded HTTP request.
            await asyncio.gather(task, return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(prove(*configuration()))
