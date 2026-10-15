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
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app import models  # noqa: F401 — register mappers

# Keep the auth stub in "local" mode for the test session.
os.environ.setdefault("DEALGATE_ENV", "local")


def _sqlite_transactions_like_postgres(eng) -> None:
    """SQLAlchemy's documented aiosqlite recipe for real SAVEPOINT semantics.

    pysqlite/aiosqlite only emit BEGIN before the first write. A SAVEPOINT
    issued first therefore starts the transaction itself, and releasing it
    COMMITS everything, so per-record savepoints (S23-PL1 item 4) would leak
    out of a page that is later rolled back. Emitting our own BEGIN makes the
    test engine behave like PostgreSQL, which staging runs.
    """

    @event.listens_for(eng.sync_engine, "connect")
    def _disable_driver_begin(dbapi_connection, _record):  # noqa: ANN001
        dbapi_connection.isolation_level = None

    @event.listens_for(eng.sync_engine, "begin")
    def _explicit_begin(conn):  # noqa: ANN001
        dbapi = conn.connection.dbapi_connection
        # StaticPool shares one connection between sessions; when another
        # session already opened the transaction, join it as before.
        if dbapi._connection.in_transaction:
            return
        # Straight to the driver, so statement-count budgets in tests do not
        # see it.
        dbapi.execute("BEGIN")


async def _memory_engine(*, postgres_like_transactions: bool = False):
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    if postgres_like_transactions:
        _sqlite_transactions_like_postgres(eng)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return eng


@pytest_asyncio.fixture
async def savepoint_engine():
    """Opt-in engine for tests that rely on SAVEPOINT rollback (S23-PL1).

    A module opts in by overriding ``engine``::

        @pytest_asyncio.fixture
        async def engine(savepoint_engine):
            return savepoint_engine

    The default ``engine`` keeps the driver's own transaction handling, which
    some app code (e.g. the SQLite branch of the Pipeline export) relies on.
    """
    eng = await _memory_engine(postgres_like_transactions=True)
    try:
        yield eng
    finally:
        await eng.dispose()


def _sqlite_foreign_keys_on(eng) -> None:
    @event.listens_for(eng.sync_engine, "connect")
    def _fk_on(dbapi_connection, _record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


@pytest_asyncio.fixture
async def fk_engine():
    """Opt-in engine that enforces foreign keys, as PostgreSQL does (S23-PL2).

    SQLite ignores foreign keys unless asked, so a row keyed on a login id
    that is not a ``user.id`` (the HubSpot-created-user bug, B11) passes here
    and fails on staging. A module opts in by overriding ``engine``::

        @pytest_asyncio.fixture
        async def engine(fk_engine):
            return fk_engine
    """
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _sqlite_foreign_keys_on(eng)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


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
