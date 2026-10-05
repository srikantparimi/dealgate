"""Dedicated, migrated PostgreSQL export race proof with exact ownership cleanup."""
import asyncio
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from s21_coverage_concurrency_pg import ROOT, admin_identity, database_identity, require


def main():
    require(len(sys.argv) == 1, "No external target/drop names accepted")
    require(not any(name == "app" or name.startswith("app.") for name in sys.modules),
        "Run standalone before application imports")
    raw = os.environ.get("S21_PIPELINE_EXPORT_ADMIN_URL")
    require(raw is not None, "Set explicit S21_PIPELINE_EXPORT_ADMIN_URL")
    admin_url = make_url(raw)
    require((admin_url.drivername, admin_url.username, admin_url.host, admin_url.port, admin_url.database)
        == ("postgresql+psycopg", "s21", "127.0.0.1", 55421, "postgres") and not admin_url.query,
        "Require s21 at literal127.0.0.1:55421/postgres with psycopg and no query options")
    for key in list(os.environ):
        if key.startswith("PG"):
            os.environ.pop(key)
    name, marker = "s21_pipeline_export_" + uuid.uuid4().hex, "owned-s21-export:" + uuid.uuid4().hex
    print(json.dumps({"process_id": os.getpid(), "private_database": name}), flush=True)
    private = admin_url.set(drivername="postgresql+asyncpg", database=name).render_as_string(hide_password=False)
    os.environ.update(POSTGRES_URL=private, DATABASE_URL=private, S21_PROJECTION_TEST_PG_URL=private,
        PYTHONDONTWRITEBYTECODE="1", DEALGATE_ENV="local", DEALGATE_TENANT_ID=name,
        AWS_EC2_METADATA_DISABLED="true", PYTHONPATH=os.pathsep.join((str(ROOT / "api"), str(ROOT))))
    os.environ.pop("DEALGATE_POSTGRES_URL", None)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT / "api"), str(ROOT)]
    with psycopg.connect(admin_url.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True, connect_timeout=5, application_name="s21-export-admin",
        options="-c statement_timeout=15000 -c lock_timeout=5000") as admin:
        admin_identity(admin)
        created, identity = False, None
        try:
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(sql.Identifier(name), sql.Identifier("s21")))
            created = True
            admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(marker)))
            identity = database_identity(admin, name)
            require(identity and identity[1:] == ("s21", marker), "Private database ownership verification failed")
            subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
                cwd=ROOT / "api", env=os.environ.copy(), check=True, timeout=300)
            spec = importlib.util.spec_from_file_location("export_proof", ROOT / "api/tests/test_s21_pipeline_fixture_projection.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            import pytest
            async def proof():
                from app.db import engine
                try:
                    with pytest.MonkeyPatch.context() as patches:
                        await asyncio.wait_for(module.prove_postgres_export_snapshot(patches), 120)
                finally:
                    await engine.dispose()
            asyncio.run(proof())
        finally:
            if created:
                admin_identity(admin)
                require(re.fullmatch(r"s21_pipeline_export_[0-9a-f]{32}", name) and identity is not None
                    and database_identity(admin, name) == identity, "Cleanup refused: exact ownership changed: " + name)
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
                require(database_identity(admin, name) is None, "Private database cleanup not confirmed")
                print(json.dumps({"private_database": name, "cleanup": "confirmed"}), flush=True)
    print(json.dumps({"result": "PASS", "rows": 1002, "expected_usd": "2002.00",
        "same_snapshot_fields_and_totals": True, "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}), flush=True)


if __name__ == "__main__":
    main()
