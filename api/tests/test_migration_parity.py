"""Every model table/column must actually be created by a migration.

This is the test that was missing. ``tests/conftest.py`` builds the schema
with ``Base.metadata.create_all`` and never runs alembic — its own comment
says "the migration and the models are 1:1" — so a model change shipped
without a matching migration is *structurally invisible* to the entire suite.

That is exactly what reached production: the code knew about
``sow_upload_job`` and ``opportunity.source``, migration 20260921_0028 created
them, and the migration was never applied. 708 tests were green the whole
time, while `POST /sows/upload`, `/deals`, `/dashboards/*` and `/renewals`
returned 500 on the deployed app.

This test runs the real migration chain against a scratch database and
compares the result with the models. It cannot tell you whether a migration
has been *applied* to a given environment — only a deployment check can do
that — but it does guarantee that one exists to apply.

PostgreSQL only, gated on ``DEALGATE_POSTGRES_URL`` (same convention as
``test_audit_hardening.py``). SQLite cannot run the chain: 0028 alters
constraints, which SQLite only supports through batch mode. Running against
the real engine is the point anyway — the Postgres-only branches of a
migration are exactly where drift hides. CI supplies a service container.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db.base import Base

API_ROOT = pathlib.Path(__file__).resolve().parents[1]

_PG_URL = os.environ.get("DEALGATE_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not _PG_URL,
    reason="requires postgres; set DEALGATE_POSTGRES_URL to run",
)


def _sync_pg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

# Columns a migration deliberately creates only on PostgreSQL. The SQLite
# branch of a migration may skip them, so they are not drift.
_POSTGRES_ONLY: set[tuple[str, str]] = set()


@pytest.fixture(scope="module")
def migrated_inspector():
    """Run `alembic upgrade head` against an empty SQLite file."""

    import app.models  # noqa: F401 — register every mapper
    import app.scheduler.ledger  # noqa: F401

    url = _sync_pg_url(_PG_URL)

    engine_admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine_admin.begin() as conn:
        # Start from nothing so the chain is exercised end to end.
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine_admin.dispose()

    if True:
        cfg = Config(str(API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
        cfg.set_main_option("sqlalchemy.url", url)

        # alembic/env.py overrides sqlalchemy.url from `app.db.DATABASE_URL`
        # (line 50), so setting it on the Config alone is not enough — point
        # the module attribute at the scratch file instead. env.py is
        # re-imported per run, so it picks this up.
        import app.db

        original = app.db.DATABASE_URL
        app.db.DATABASE_URL = url
        try:
            command.upgrade(cfg, "head")
        finally:
            app.db.DATABASE_URL = original

        engine = create_engine(url)
        try:
            yield inspect(engine)
        finally:
            engine.dispose()


def test_every_model_table_is_created_by_a_migration(migrated_inspector) -> None:
    migrated = set(migrated_inspector.get_table_names())
    declared = set(Base.metadata.tables)

    missing = sorted(declared - migrated - {"alembic_version"})
    assert not missing, (
        "These tables are declared on a model but no migration creates them: "
        f"{missing}. Add a migration, or the code will 500 against a database "
        "that only has what the migrations built."
    )


def test_every_model_column_is_created_by_a_migration(migrated_inspector) -> None:
    migrated_tables = set(migrated_inspector.get_table_names())
    problems: list[str] = []

    for table_name, table in sorted(Base.metadata.tables.items()):
        if table_name not in migrated_tables:
            continue  # reported by the table test
        migrated_cols = {c["name"] for c in migrated_inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in migrated_cols:
                continue
            if (table_name, column.name) in _POSTGRES_ONLY:
                continue
            problems.append(f"{table_name}.{column.name}")

    assert not problems, (
        "These columns exist on a model but no migration creates them: "
        f"{sorted(problems)}. This is the failure mode that produced "
        "'column opportunity.source does not exist' in production."
    )


def test_the_sow_upload_tables_specifically_exist(migrated_inspector) -> None:
    """Named explicitly because these are the ones that were missing."""

    tables = set(migrated_inspector.get_table_names())
    assert "sow_upload_job" in tables
    assert "client_alias" in tables

    opportunity_cols = {c["name"] for c in migrated_inspector.get_columns("opportunity")}
    assert "source" in opportunity_cols
