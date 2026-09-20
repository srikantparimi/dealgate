"""Shared fixtures.

Uses an in-memory SQLite database with `StaticPool` so multiple sessions in the
same test share the same schema. Alembic is not run for the SQLite path — we
`create_all` from metadata, and `test_migration_parity` is what proves the
migrations and the models still agree.

The Postgres-gated tests are different: they need a real, migrated database,
and they used to depend on whichever of them happened to run first having
built one. `_migrated_postgres` below makes that explicit and
order-independent.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app import models  # noqa: F401 — register mappers

# Keep the auth stub in "local" mode for the test session.
os.environ.setdefault("DEALGATE_ENV", "local")


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s


# --- Postgres-gated tests --------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _migrated_postgres():
    """Migrate the Postgres test database once, when one is configured.

    `test_audit_hardening` asserts that the append-only trigger rejects UPDATE
    and DELETE — which requires the trigger to exist, which requires the
    migrations to have run. It previously passed or failed depending on test
    ordering and on what a previous run had left behind. A session fixture
    makes the dependency real.

    No-op without DEALGATE_POSTGRES_URL, so the default SQLite path is
    untouched.
    """

    url = os.environ.get("DEALGATE_POSTGRES_URL")
    if not url:
        yield
        return

    import pathlib as _pathlib

    from alembic import command
    from alembic.config import Config

    import app.db as _db

    sync_url = url
    if sync_url.startswith("postgresql://"):
        sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif sync_url.startswith("postgresql+asyncpg://"):
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

    root = _pathlib.Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # alembic/env.py reads the URL off `app.db.DATABASE_URL`, so setting it on
    # the Config alone is not enough.
    original = _db.DATABASE_URL
    _db.DATABASE_URL = sync_url
    try:
        command.upgrade(cfg, "head")
    finally:
        _db.DATABASE_URL = original
    yield
