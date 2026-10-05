"""Execute BU membership oracles against the lead-owned migrated PostgreSQL DB."""

import asyncio
import json
import os
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import test_s21_crm_bu_readers as cases


async def main():
    url = os.environ["DEALGATE_POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.path == "/s21_schema"
    engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    checks = []
    try:
        for object_type in ("deal", "company"):
            for case in (cases.test_rows_filters_facets_and_three_pages_share_observed_population,
                         cases.test_missing_means_observed_empty_not_stale_unknown_or_unfetched,
                         cases.test_facets_do_not_leak_nonmatching_or_unauthorized_companies):
                async with factory() as session:
                    # Seeded IDs are deterministic; each oracle rolls back its entire fixture.
                    await case(session, object_type)
                    await session.rollback()
                    checks.append(f"{case.__name__}:{object_type}")
        for state in ("unknown", "absent", "ambiguous", "unavailable"):
            async with factory() as session:
                await cases.test_unavailable_mapping_never_displays_or_classifies_old_values(session, state)
                await session.rollback()
                checks.append(f"unavailable:{state}")
        async with factory() as session:
            await cases.test_unknown_raw_value_is_retained_but_not_a_named_bu_bucket(session)
            await session.rollback()
            head = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            checks.append("unknown-value-retained")
        print(json.dumps({"migration": head, "passed": len(checks), "checks": checks,
                          "fixture_writes": "rolled back", "shared_database_touched": False}))
    finally:
        await engine.dispose()


asyncio.run(main())
