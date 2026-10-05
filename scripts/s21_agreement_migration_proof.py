"""Fresh owned PG database: legacy backfill, downgrade guard and replacement CAS."""
import asyncio
import io
import json
import os
import threading
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from alembic import command
from alembic.config import Config
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from starlette.datastructures import Headers

run = uuid.uuid4().hex
database = f"s21_agreement_{run}"
receipt = Path(f"/tmp/s21-agreement-{run}.json")
state = {"database": database, "run": run, "state": "planned", "shared_database_touched": False}
receipt.write_text(json.dumps(state))
with psycopg.connect("host=127.0.0.1 port=55421 user=s21 dbname=postgres", autocommit=True) as admin:
    admin.execute(sql.SQL("CREATE DATABASE {} OWNER s21").format(sql.Identifier(database)))
    admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(database), sql.Literal(f"owned-s21-agreement:{run}")))
state["state"] = "created"
receipt.write_text(json.dumps(state))
os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID=database)
url = f"postgresql+psycopg://s21@127.0.0.1:55421/{database}"
import app.db
app.db.DATABASE_URL = url
root = Path(__file__).resolve().parents[1]
config = Config(str(root / "api/alembic.ini"))
config.set_main_option("script_location", str(root / "api/alembic"))
prior = "20261003_0062_actual_coverage"
current = "20261003_0063_agreement_versions"
command.upgrade(config, prior)
actor_id, client_id, agreement_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
with psycopg.connect(f"host=127.0.0.1 port=55421 user=s21 dbname={database}") as connection:
    connection.execute('INSERT INTO "user" (id,email,name,groups) VALUES (%s,%s,%s,%s)',
        (actor_id, f"agreement-{run}@example.test", "Synthetic Legal", '["Legal"]'))
    connection.execute("INSERT INTO client (id,name) VALUES (%s,%s)", (client_id, "Synthetic legacy NDA"))
    connection.execute("INSERT INTO agreement (id,client_id,kind,file_key,filename,file_size,uploaded_by) VALUES (%s,%s,'NDA','legacy/nda.pdf','nda.pdf',17,%s)",
        (agreement_id, client_id, actor_id))
command.upgrade(config, current)
with psycopg.connect(f"host=127.0.0.1 port=55421 user=s21 dbname={database}") as connection:
    assert connection.execute("SELECT version_no,file_hash,file_key,filename,file_size,uploaded_by FROM agreement_file_version").fetchone() == (1, None, "legacy/nda.pdf", "nda.pdf", 17, actor_id)
command.downgrade(config, prior)
command.upgrade(config, current)


async def race(expected_version=1, deleting=False):
    from app.auth import AuthUser
    from app.integrations.s3_evidence import StubS3
    from app.routers.agreements import replace_agreement
    engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    entered, release = threading.Event(), threading.Event()
    class BlockingStorage(StubS3):
        def put_object(self, *args):
            entered.set()
            assert release.wait(15), "Coordinator did not release storage boundary"
            return super().put_object(*args)
    storage = BlockingStorage()
    actor = AuthUser(actor_id, f"agreement-{run}@example.test", "Synthetic Legal", ("Legal",))
    async def replace_one():
        async with factory() as session:
            file = UploadFile(io.BytesIO(b"%PDF synthetic replacement"), filename="replacement.pdf",
                headers=Headers({"content-type": "application/pdf"}))
            try:
                result = await replace_agreement(agreement_id=agreement_id, expected_version=expected_version,
                    file=file, user=actor, session=session, s3=storage)
                return result.version_no
            except HTTPException as error:
                await session.rollback()
                assert error.status_code == 409
                return "stale-refused"
    async def delete_one():
        from app.routers.deletion import delete_client_endpoint
        deleter = AuthUser(deleter_id, f"deleter-{run}@example.test", "Synthetic deleter", ("Legal",))
        async with factory() as session:
            result = await delete_client_endpoint(client_id=client_id, reason=None, user=deleter, session=session)
            return result.status
    first = asyncio.create_task(replace_one())
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 10), "First replacement never reached locked storage"
        second = asyncio.create_task(delete_one() if deleting else replace_one())
        waiting = 0
        for _ in range(100):
            async with engine.connect() as observer:
                waiting = (await observer.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%client%'"))).scalar_one()
            if waiting:
                break
            await asyncio.sleep(.02)
        assert waiting, "No real PostgreSQL Client lock wait observed"
        release.set()
        assert await asyncio.wait_for(first, 10) == expected_version + 1
        assert await asyncio.wait_for(second, 10) == ("pending" if deleting else "stale-refused")
        assert len(storage.objects) == 1
        async with engine.connect() as observer:
            assert (await observer.execute(text("SELECT count(*) FROM agreement_file_version"))).scalar_one() == (0 if deleting else 2)
            if deleting:
                assert (await observer.execute(text("SELECT count(*) FROM agreement"))).scalar_one() == 0
                objects = (await observer.execute(text("SELECT objects FROM deletion_job"))).scalar_one()
                assert len(objects) == 3 and len({item["key"] for item in objects}) == 3
                assert (await observer.execute(text("SELECT count(*) FROM audit_event WHERE action='user.groups_synced'"))).scalar_one() >= 1
            else:
                assert (await observer.execute(text("SELECT count(*) FROM audit_event WHERE action='agreement.replaced'"))).scalar_one() == 1
        return ({"parent_delete_race": "passed", "identity_sync": "committed_before_lock", "cleanup_keys": 3}
            if deleting else {"client_lock_wait": "observed", "stale_competitor": 409, "new_storage_writes": 1, "versions": 2})
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await engine.dispose()


result = asyncio.run(race())
try:
    command.downgrade(config, prior)
except RuntimeError as error:
    assert "discard evidence" in str(error)
else:
    raise AssertionError("Populated downgrade discarded document revisions")
deleter_id = uuid.uuid4()
with psycopg.connect(f"host=127.0.0.1 port=55421 user=s21 dbname={database}") as connection:
    connection.execute('INSERT INTO "user" (id,email,name,groups) VALUES (%s,%s,%s,%s)',
        (deleter_id, f"deleter-{run}@example.test", "Synthetic deleter", '[]'))
result.update(asyncio.run(race(expected_version=2, deleting=True)))
state.update(state="passed", migration=current, legacy_hash=None, legacy_roundtrip="passed",
    populated_downgrade="refused", **result)
receipt.write_text(json.dumps(state, indent=2))
print(json.dumps({**state, "receipt": str(receipt)}, indent=2))
