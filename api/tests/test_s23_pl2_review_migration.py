"""S23-PL2 pre-merge review (R2) — migration 0070 stays reversible once the Pipeline page is used.

The old saved-view key, unique over ``(owner_id, key, is_builtin)`` for every
row (archived rows included), allows one user-defined view per key. PL2 users
have several Pipeline views (``key='pipeline'``) and delete some of them
(archived, not removed), so the downgrade must give each user-defined view a
key of its own before it re-creates that constraint. Upgrade, data,
downgrade, upgrade on PostgreSQL; the restore statement from the migration's
docstring gives the Pipeline its views back after upgrading again.

PostgreSQL only (``DEALGATE_POSTGRES_URL``). Like ``test_migration_parity`` it
rebuilds the schema, and it leaves the database at head.
"""

from __future__ import annotations

import os
import pathlib
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

API_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PG_URL = os.environ.get("DEALGATE_POSTGRES_URL")
BEFORE_0070 = "20261014_0069_sync_run"
# The restore statement the 0070 docstring gives, for after an upgrade.
RESTORE_KEYS = "UPDATE saved_view SET key = split_part(key, ':', 1) WHERE NOT is_builtin AND key LIKE '%:%'"

pytestmark = pytest.mark.skipif(not _PG_URL, reason="requires postgres; set DEALGATE_POSTGRES_URL to run")


def _sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@pytest.fixture
def migrations():
    import app.db as _db

    url = _sync_url(_PG_URL)
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    original = _db.DATABASE_URL
    _db.DATABASE_URL = url  # alembic/env.py reads the URL from here
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    try:
        yield cfg, engine
    finally:
        command.upgrade(cfg, "head")  # the other Postgres tests need a migrated database
        _db.DATABASE_URL = original
        engine.dispose()


def _views(conn) -> dict[uuid.UUID, tuple[str, str, bool, bool]]:
    rows = conn.execute(text("SELECT id, key, name, is_builtin, archived_at IS NOT NULL FROM saved_view")).all()
    return {row[0]: (row[1], row[2], row[3], row[4]) for row in rows}


def _constraint(conn, name: str) -> bool:
    return bool(conn.execute(text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name}).first())


def _index(conn, name: str) -> bool:
    return bool(conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = :n"), {"n": name}).first())


def test_0070_round_trips_with_several_and_archived_pipeline_views(migrations):
    cfg, engine = migrations
    command.upgrade(cfg, "head")
    rita, otto = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        for user_id, email in ((rita, "rita@example.test"), (otto, "otto@example.test")):
            conn.execute(text(
                "INSERT INTO \"user\" (id, email, name, groups, hubspot_owner_id, hubspot_owner_link, cognito_sub) "
                "VALUES (:id, :email, :email, '[]', :owner, 'email', :sub)"),
                {"id": user_id, "email": email, "owner": f"o-{email}", "sub": str(uuid.uuid4())})
        views = (
            (rita, "my_opportunities", "My opportunities", True, False),  # a built-in
            (rita, "custom", "From the old page", False, False),  # a view the old route saved
            (rita, "pipeline", "Closing soon", False, False),
            (rita, "pipeline", "Big deals", False, False),  # a second live Pipeline view
            (rita, "pipeline", "Closing soon", False, True),  # a deleted (archived) one
            (otto, "pipeline", "Closing soon", False, False),
        )
        for owner, key, name, builtin, archived in views:
            conn.execute(text(
                "INSERT INTO saved_view (id, owner_id, key, name, filter_json, visibility, is_builtin, "
                "display_order, archived_at) VALUES (:id, :owner, :key, :name, '{}', 'private', :builtin, 0, "
                + ("now()" if archived else "NULL") + ")"),
                {"id": uuid.uuid4(), "owner": owner, "key": key, "name": name, "builtin": builtin})
        before = _views(conn)

    command.downgrade(cfg, BEFORE_0070)  # failed: could not create unique index "uq_saved_view_owner_key_builtin"
    with engine.begin() as conn:
        assert _constraint(conn, "uq_saved_view_owner_key_builtin")
        after = _views(conn)
    assert after.keys() == before.keys()  # every view survives
    for view_id, (key, name, builtin, archived) in before.items():
        # Built-ins keep their key; each user-defined view gets "<key>:<id>".
        assert after[view_id] == ((key if builtin else f"{key}:{view_id}"), name, builtin, archived)

    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        assert not _constraint(conn, "uq_saved_view_owner_key_builtin")
        assert _index(conn, "ux_saved_view_builtin_key") and _index(conn, "ux_saved_view_owner_name")
        assert _views(conn).keys() == before.keys()
        conn.execute(text(RESTORE_KEYS))
        assert _views(conn) == before
