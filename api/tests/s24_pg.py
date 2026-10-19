"""S24-AG1 test helper: a scratch Postgres database per test module (T4, T5, T13).

The batch sets the global cutover and stamps every client, and its job commits on its own sessions,
so these tests cannot share the CI database or run inside a rolled-back transaction. ``scratch_postgres``
creates a fresh database on the server named by DEALGATE_POSTGRES_URL, migrates it to head, yields an
engine and a session factory, and drops it afterwards. Skipped when no Postgres is configured.
"""

from __future__ import annotations

import os
import pathlib
import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

POSTGRES = pytest.mark.skipif(not os.environ.get("DEALGATE_POSTGRES_URL"),
                              reason="DEALGATE_POSTGRES_URL not set (Postgres-only test)")


def _url(database: str, driver: str):
    base = make_url(os.environ["DEALGATE_POSTGRES_URL"])
    return base.set(drivername=f"postgresql+{driver}", database=database)


def _migrate(sync_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    import app.db as _db

    root = pathlib.Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    original = _db.DATABASE_URL
    _db.DATABASE_URL = sync_url
    try:
        command.upgrade(cfg, "head")
    finally:
        _db.DATABASE_URL = original


@asynccontextmanager
async def scratch_postgres():
    name = f"ag1_scratch_{uuid.uuid4().hex[:10]}"
    admin = create_async_engine(_url("postgres", "asyncpg"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = None
    try:
        import asyncio

        await asyncio.to_thread(_migrate, _url(name, "psycopg").render_as_string(hide_password=False))
        engine = create_async_engine(_url(name, "asyncpg"), pool_size=5, max_overflow=5)
        yield engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()
