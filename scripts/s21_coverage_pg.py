"""Execute staffing replacement oracles on guarded, migrated PostgreSQL only."""
import asyncio
import json
import os
from urllib.parse import urlparse

from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests import test_s21_coverage_service as cases
from tests import test_s21_coverage_independent as qa


async def main():
    url = os.environ["DEALGATE_POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port == 55421 and parsed.path == "/s21_schema"
    engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    checks = []
    try:
        for case in (cases.test_coverage_reduces_real_global_demand_and_clear_appends,
            cases.test_republication_stales_mapping_and_never_silently_rebinds,
            cases.test_sow_deletion_retains_mapping_but_plan_deletion_cascades,
            qa.test_archived_project_mapping_history_remains_available_to_authorized_reviewer,
            qa.test_empty_revision_can_clear_archived_project_mapping_and_restore_completeness):
            with MonkeyPatch.context() as patch:
                async with engine.connect() as connection:
                    transaction = await connection.begin()
                    async with AsyncSession(bind=connection, expire_on_commit=False,
                        join_transaction_mode="create_savepoint") as session:
                        canonical = await cases.canonical.__wrapped__(session, patch)
                        if case.__module__ == qa.__name__:
                            sources = await qa.sources.__wrapped__(session, canonical)
                            await case(session, sources)
                        else:
                            pair = await cases.pair.__wrapped__(session, canonical)
                            if case == cases.test_sow_deletion_retains_mapping_but_plan_deletion_cascades:
                                await case(session, pair, canonical)
                            else:
                                await case(session, pair)
                        head = await session.scalar(text("SELECT version_num FROM alembic_version"))
                    await transaction.rollback()
                    checks.append(case.__name__)
        print(json.dumps({"migration": head, "passed": len(checks), "checks": checks,
            "fixture_writes": "outer transaction rolled back", "shared_database_touched": False}))
    finally:
        await engine.dispose()


asyncio.run(main())
