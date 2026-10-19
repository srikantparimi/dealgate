"""S24-AG1 B1 — migration 0072 is reversible on PostgreSQL, and its downgrade refuses to discard AG1 evidence.

Upgrade to head, downgrade to 0071 (the five AG1 tables and every added column are gone, the old non-unique
``(client_id, kind)`` index is back), upgrade again; then with a cutover set, and separately with a saved
HubSpot ``msa_type`` mapping (bug #95), the downgrade raises and the database stays at 0072. Runs on its own
scratch database (created and dropped here), so it never rebuilds the shared test database.

PostgreSQL only (``DEALGATE_POSTGRES_URL``).
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.s24_pg import POSTGRES, _url

pytestmark = POSTGRES

API_ROOT = pathlib.Path(__file__).resolve().parents[1]
HEAD = "20261015_0072_agreements_ag1"
BEFORE = "20261014_0071_cognito_sub"
AG1_TABLES = ("standard_agreement", "agreement_batch", "agreement_mark", "agreements_settings", "agreement_hubspot_map")
AG1_COLUMNS = {
    "agreement": ("source", "standard_agreement_id", "batch_id", "note"),
    "agreement_file_version": ("source", "standard_agreement_id", "batch_id", "note"),
    "client": ("relationship", "relationship_basis", "relationship_set_by", "relationship_set_at"),
    "opportunity": ("hubspot_msa_type",),
}


def _alembic(url: str, action: str, target: str) -> None:
    import app.db as _db

    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    original = _db.DATABASE_URL
    _db.DATABASE_URL = url  # alembic/env.py reads it
    try:
        getattr(command, action)(cfg, target)
    finally:
        _db.DATABASE_URL = original


@pytest.fixture
def scratch_url():
    name = f"ag1_mig_{uuid.uuid4().hex[:10]}"
    admin = create_engine(_url("postgres", "psycopg"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield _url(name, "psycopg").render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _schema(url: str) -> dict:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = set(conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).scalars())
            columns = {(r[0], r[1]) for r in conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'"))}
            indexes = {r[0]: r[1] for r in conn.execute(text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'agreement'"))}
    finally:
        engine.dispose()
    return {"version": version, "tables": tables, "columns": columns, "indexes": indexes}


def _assert_at_head(schema: dict) -> None:
    assert schema["version"] == HEAD
    assert set(AG1_TABLES) <= schema["tables"]
    for table, names in AG1_COLUMNS.items():
        for name in names:
            assert (table, name) in schema["columns"], (table, name)
    assert "UNIQUE" in schema["indexes"]["ux_agreement_client_kind"]


def test_0072_upgrades_downgrades_and_upgrades_again(scratch_url):
    _alembic(scratch_url, "upgrade", "head")
    _assert_at_head(_schema(scratch_url))

    _alembic(scratch_url, "downgrade", BEFORE)
    down = _schema(scratch_url)
    assert down["version"] == BEFORE
    assert not set(AG1_TABLES) & down["tables"]
    for table, names in AG1_COLUMNS.items():
        for name in names:
            assert (table, name) not in down["columns"], (table, name)
    assert "ux_agreement_client_kind" not in down["indexes"]
    assert "UNIQUE" not in down["indexes"]["ix_agreement_client_kind"]  # the pre-AG1 index is back

    _alembic(scratch_url, "upgrade", "head")
    _assert_at_head(_schema(scratch_url))


@pytest.mark.parametrize("evidence", ["cutover", "hubspot_mapping"])
def test_the_0072_downgrade_refuses_while_ag1_evidence_exists(scratch_url, evidence):
    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    try:
        with engine.begin() as conn:
            if evidence == "cutover":
                conn.execute(text("UPDATE agreements_settings SET cutover_date = DATE '2026-10-01' WHERE id = 1"))
            else:
                user_id = uuid.uuid4()
                conn.execute(text('INSERT INTO "user" (id, email, name, groups) VALUES (:id, :email, :name, :groups)'),
                             {"id": user_id, "email": "ada.mig@example.test", "name": "Ada Admin",
                              "groups": '["SystemAdmin"]'})
                conn.execute(text("INSERT INTO agreement_hubspot_map (value, action, updated_by) "
                                  "VALUES ('Signed MSA', 'covered', :uid)"), {"uid": user_id})
    finally:
        engine.dispose()
    with pytest.raises(RuntimeError, match="AG1 agreement evidence exists"):
        _alembic(scratch_url, "downgrade", BEFORE)
    _assert_at_head(_schema(scratch_url))  # nothing was dropped
