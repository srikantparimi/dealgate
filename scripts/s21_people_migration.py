"""Owned scratch PostgreSQL proof: 0056 rollback guard, exact imports and CAS."""
import asyncio
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import app.db
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import AuthUser
from app.models.people_planning import PeopleSource
from app.models.user import User
from app.services.people_planning import WorkforceImportInput, import_workforce, availability

url = os.environ["DEALGATE_POSTGRES_URL"]
parsed = urlparse(url)
assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.path == "/s21_schema"
assert url.startswith("postgresql+psycopg://")
os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID="s21-people-pg-proof")
root = Path(__file__).resolve().parents[1]
config = Config(str(root / "api/alembic.ini"))
config.set_main_option("script_location", str(root / "api/alembic"))
app.db.DATABASE_URL = url


async def proof():
    engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    actor = AuthUser(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Synthetic HR", groups=("HR",))
    body = WorkforceImportInput(source_system=f"synthetic-{uuid.uuid4()}", request_key=str(uuid.uuid4()),
        expected_previous_batch_id=None, source_as_of="2026-10-01T00:00:00Z", reason="Real PostgreSQL exact managed supply proof",
        basis="gross_with_commitments", people=[dict(person_key="synthetic-person", display_name="Synthetic person",
            role="Engineer", skills=["python"], level="senior", location="US", timezone="America/Los_Angeles",
            evidence=["Synthetic managed roster, no real people"], intervals=[dict(kind="gross",
                start_date="2026-11-01", end_date="2026-11-30", allocation="0.1234567890123456789012345678")])])
    try:
        async with factory() as session:
            session.add(User(id=actor.id, email=actor.email, name=actor.name, groups=list(actor.groups)))
            await session.commit()
            first = await import_workforce(session, actor=actor, body=body)
            assert await import_workforce(session, actor=actor, body=body) == first
            view = await availability(session, actor=actor)
            assert view["people"][0]["intervals"][0]["allocation"] == "0.1234567890123456789012345678"
        async with factory() as first_session, factory() as contender_session:
            source = await first_session.scalar(select(PeopleSource).where(
                PeopleSource.source_system == body.source_system).with_for_update())
            assert source is not None
            second = body.model_copy(update={"request_key": str(uuid.uuid4()), "expected_previous_batch_id": uuid.UUID(first["id"]),
                "reason": "First concurrent HR revision"})
            competing = second.model_copy(update={"request_key": str(uuid.uuid4()), "reason": "Competing stale HR revision"})
            async def contend():
                try:
                    await import_workforce(contender_session, actor=actor, body=competing)
                except HTTPException as error:
                    await contender_session.rollback()
                    assert error.status_code == 409
                    return "stale-refused"
                raise AssertionError("Concurrent import overwrote the newer source snapshot")
            pending = asyncio.create_task(contend())
            waiting = 0
            for _ in range(100):
                async with engine.connect() as observer:
                    waiting = (await observer.execute(text("SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                        "AND wait_event_type='Lock' AND query LIKE '%people_source%'"))).scalar_one()
                if waiting:
                    break
                await asyncio.sleep(0.02)
            assert waiting, "Expected actual PostgreSQL source-row lock wait"
            result = await import_workforce(first_session, actor=actor, body=second)
            assert result["revision"] == 2
            assert await asyncio.wait_for(pending, timeout=10) == "stale-refused"
        async with factory() as session:
            batch_count = (await session.execute(text("SELECT count(*) FROM people_import_batch WHERE source_id=:id"), {"id": source.id})).scalar_one()
            audit_count = (await session.execute(text("SELECT count(*) FROM audit_event WHERE entity='people_source' AND entity_id=:id"), {"id": str(source.id)})).scalar_one()
            assert batch_count == audit_count == 2
        return {"exact_decimal": "preserved", "replay": "same_batch", "pg_lock_wait": "observed",
            "concurrent_stale_revision": "refused", "immutable_batches": 2, "audits": 2}
    finally:
        await engine.dispose()


command.downgrade(config, "20261002_0055_scan_state")
command.upgrade(config, "head")
results = asyncio.run(proof())
try:
    command.downgrade(config, "20261002_0055_scan_state")
except RuntimeError as error:
    assert "Cannot discard managed workforce" in str(error)
else:
    raise AssertionError("Downgrade discarded workforce source history")
print(json.dumps({"migration": "0056", "empty_roundtrip": "passed", "populated_downgrade": "refused",
    **results, "shared_database_touched": False}))
