"""0055 migration and real PostgreSQL scan-lock proof in owned scratch DB only."""
import asyncio
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import app.db
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.opportunity import Opportunity
from app.services.sync_status import (
    ScanConflict, acquire_scan, checkpoint_scan, complete_scan, fail_scan,
)

url = os.environ["DEALGATE_POSTGRES_URL"]
parsed = urlparse(url)
assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path == "/s21_schema"
assert url.startswith("postgresql+psycopg://")
root = Path(__file__).resolve().parents[1]
config = Config(str(root / "api/alembic.ini"))
config.set_main_option("script_location", str(root / "api/alembic"))
app.db.DATABASE_URL = url
engine = create_engine(url)
source = f"s21-scan-{uuid.uuid4().hex}"
deal_id = uuid.uuid4()


def loss_refused(message):
    try:
        command.downgrade(config, "20261002_0054_source_facts")
    except RuntimeError as error:
        assert message in str(error), error
    else:
        raise AssertionError("Downgrade discarded scan evidence")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261002_0055_scan_state"


async def lease_proof():
    async_engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    context = {"schema_version": 1, "tenant": "synthetic", "environment": "local",
        "portal_id": "fixture", "properties": ["dealname"], "mapping_version": 1}
    try:
        async with factory() as first, factory() as second:
            lease = await acquire_scan(first, source=source, context=context)
            async def contender():
                try:
                    await acquire_scan(second, source=source, context=context)
                except ScanConflict:
                    await second.rollback()
                    return "refused"
                raise AssertionError("Concurrent acquisition stole an active lease")
            pending = asyncio.create_task(contender())
            # Verify a real database lock wait, not just a timing assumption.
            for _ in range(100):
                async with async_engine.connect() as observer:
                    waiting = (await observer.execute(text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                        "AND pid<>pg_backend_pid() AND wait_event_type='Lock' "
                        "AND query LIKE '%sync_status%'"))).scalar_one()
                if waiting:
                    break
                await asyncio.sleep(0.02)
            assert waiting, "Contender did not enter a PostgreSQL lock wait"
            await first.commit()
            assert await asyncio.wait_for(pending, timeout=5) == "refused"
        async with factory() as session:
            deal = await session.get(Opportunity, deal_id)
            deal.name = "must rollback with page"
            deal.hubspot_seen_generation = lease.generation
            await checkpoint_scan(session, lease, expected_cursor=None, next_cursor="page-2")
            await session.rollback()
        async with factory() as session:
            deal = await session.get(Opportunity, deal_id)
            assert deal.name == "Synthetic preserved deal" and deal.hubspot_seen_generation is None
            deal.hubspot_seen_generation = lease.generation
            await checkpoint_scan(session, lease, expected_cursor=None, next_cursor="page-2")
            await session.commit()
        async with factory() as session:
            await session.execute(text("UPDATE sync_status SET scan_lease_expires_at=clock_timestamp()-interval '1 second' WHERE source=:source"), {"source": source})
            await session.commit()
        async with factory() as session:
            resumed = await acquire_scan(session, source=source, context=context)
            await session.commit()
            assert resumed.generation == lease.generation and resumed.cursor == "page-2"
            assert resumed.token != lease.token
            for operation in (lambda: complete_scan(session, lease),
                lambda: fail_scan(session, lease, error="stale-owner")):
                try:
                    await operation()
                except ScanConflict:
                    await session.rollback()
                else:
                    raise AssertionError("Superseded owner changed scan state")
            await checkpoint_scan(session, resumed, expected_cursor="page-2", next_cursor=None)
            await complete_scan(session, resumed)
            await session.commit()
            row = (await session.execute(text("SELECT scan_phase,scan_completed_at,reconciled_at,last_success_at,scan_lease_token FROM sync_status WHERE source=:source"), {"source": source})).one()
            assert row[0] == "completed" and row[1] == row[2] == row[3] and row[4] is None
    finally:
        await async_engine.dispose()


try:
    command.downgrade(config, "20261002_0054_source_facts")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sync_status(source,scan_generation) VALUES (:source,7)"), {"source": source})
        conn.execute(text("INSERT INTO opportunity(id,source,governance_status,name) VALUES (:id,'manual','Intake','Synthetic preserved deal')"), {"id": deal_id})
    command.upgrade(config, "20261002_0055_scan_state")
    with engine.begin() as conn:
        row = conn.execute(text("SELECT scan_phase,scan_failure_count,scan_context,scan_lease_token,scan_lease_expires_at FROM sync_status WHERE source=:source"), {"source": source}).one()
        assert tuple(row) == ("idle", 0, None, None, None)
    command.downgrade(config, "20261002_0054_source_facts")
    command.upgrade(config, "20261002_0055_scan_state")
    with engine.begin() as conn:
        conn.execute(text("UPDATE sync_status SET scan_generation=2147483648 WHERE source=:source"), {"source": source})
    loss_refused("Cannot discard scan recovery evidence")
    with engine.begin() as conn:
        conn.execute(text("UPDATE sync_status SET scan_generation=7 WHERE source=:source"), {"source": source})
        conn.execute(text("UPDATE opportunity SET hubspot_seen_generation=7 WHERE id=:id"), {"id": deal_id})
    loss_refused("Cannot discard observed scan generation")
    with engine.begin() as conn:
        conn.execute(text("UPDATE opportunity SET hubspot_seen_generation=NULL WHERE id=:id"), {"id": deal_id})
    asyncio.run(lease_proof())
    loss_refused("Cannot discard scan recovery evidence")
    print(json.dumps({"migration": "0055", "legacy_defaults": "passed", "empty_roundtrip": "passed",
        "loss_refusals": 3, "pg_lock_wait": "observed", "concurrent_acquire": "refused",
        "page_rollback": "atomic", "resume": "same_generation_and_cursor_new_token",
        "stale_completion_and_failure": "refused", "shared_database_touched": False}))
finally:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_status WHERE source=:source"), {"source": source})
        conn.execute(text("DELETE FROM opportunity WHERE id=:id"), {"id": deal_id})
    engine.dispose()
