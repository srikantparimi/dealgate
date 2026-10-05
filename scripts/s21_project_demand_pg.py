"""Retained staffing and sourcing through real PostgreSQL FK deletion semantics."""
import asyncio
import json
import os
from urllib.parse import urlparse

from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests import test_s21_project_demand as cases


async def main():
    url = os.environ["DEALGATE_POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port == 55421 and parsed.path == "/s21_schema"
    engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    checks = []
    try:
        for case in (cases.test_project_publication_replay_and_cost_free_source,
            cases.test_detached_project_keeps_publication_and_stable_demand_identity,
            cases.test_actual_sow_and_client_deletion_preserves_project_sourcing_history):
            with MonkeyPatch.context() as patch:
                async with engine.connect() as connection:
                    transaction = await connection.begin()
                    async with AsyncSession(bind=connection, expire_on_commit=False,
                        join_transaction_mode="create_savepoint") as session:
                        canonical = await cases.canonical.__wrapped__(session, patch)
                        await case(session, canonical)
                        head = await session.scalar(text("SELECT version_num FROM alembic_version"))
                    await transaction.rollback()
                    checks.append(case.__name__)
        print(json.dumps({"migration": head, "passed": len(checks), "checks": checks,
            "fixture_writes": "outer transaction rolled back", "shared_database_touched": False}))
    finally:
        await engine.dispose()


asyncio.run(main())
