"""S21F:T31 — list/filter/summary/export at the declared representative load.

Seeds 10,000 deals / 200 clients / 1,000 SOWs (one version each) spread
across 24 monthly close-date buckets and 9 mirrored stages into an owned
disposable Postgres database, then measures the deployed query paths
in-process (ASGI transport, no network hop — recorded honestly) with a
per-request SQL statement counter. Receipt:
docs/s21/evidence/baseline/t31-load-proof.json. Misses are reported, not
hidden.
"""

import asyncio
import json
import os
import platform
import statistics
import time
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

HOST = "host=127.0.0.1 port=55421 user=s21"
DEALS, CLIENTS, SOWS, BUCKETS, STAGES, OWNERS = 10_000, 200, 1_000, 24, 9, 26
REQUESTS = 30

run = uuid.uuid4().hex[:12]
database = f"s21_load_{run}"
root = Path(__file__).resolve().parents[1]
receipt_path = root / "docs/s21/evidence/baseline/t31-load-proof.json"

with psycopg.connect(f"{HOST} dbname=postgres", autocommit=True) as admin:
    admin.execute(sql.SQL("CREATE DATABASE {} OWNER s21").format(sql.Identifier(database)))
    admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(
        sql.Identifier(database), sql.Literal(f"owned-s21-load:{run}")))

url = f"postgresql+psycopg://s21@127.0.0.1:55421/{database}"
os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID=f"s21-load-{run}",
                  DEALGATE_TEST_GROUPS="SystemAdmin",
                  DEALGATE_REPORTING_TIMEZONE="America/Los_Angeles",
                  DEALGATE_REPORTING_CURRENCY="USD")
import app.db  # noqa: E402
app.db.DATABASE_URL = url
config = Config(str(root / "api/alembic.ini"))
config.set_main_option("script_location", str(root / "api/alembic"))
config.set_main_option("sqlalchemy.url", url)
command.upgrade(config, "head")

seed_started = time.perf_counter()
owner_ids = [uuid.uuid4() for _ in range(OWNERS)]
client_ids = [uuid.uuid4() for _ in range(CLIENTS)]
with psycopg.connect(f"{HOST} dbname={database}") as conn:
    conn.execute("INSERT INTO hubspot_pipeline (id,label,display_order) VALUES ('default','Sales Pipeline',0)")
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO hubspot_stage (id,pipeline_id,label,display_order,is_closed)"
                        " VALUES (%s,'default',%s,%s,%s)",
                        [(f"stage-{i}", f"Stage {i}", i, i >= STAGES - 2) for i in range(STAGES)])
        cur.executemany('INSERT INTO "user" (id,email,name,groups) VALUES (%s,%s,%s,%s)',
                        [(oid, f"load-owner-{i}-{run}@example.test", f"Load Owner {i}", '["Sales"]')
                         for i, oid in enumerate(owner_ids)])
        cur.executemany("INSERT INTO client (id,name) VALUES (%s,%s)",
                        [(cid, f"Load client {i:04d} {run}") for i, cid in enumerate(client_ids)])
        deal_rows, sow_rows, version_rows = [], [], []
        for i in range(DEALS):
            deal_id = uuid.uuid4()
            bucket = i % BUCKETS
            close = date(2026 + (bucket // 12), bucket % 12 + 1, 15)
            deal_rows.append((
                deal_id, f"HS-LOAD-{run}-{i}", client_ids[i % CLIENTS], owner_ids[i % OWNERS],
                "Intake", f"Load deal {i:05d}", f"{(i % 400) * 500 + 5000}.00", close,
                "default", f"stage-{i % STAGES}", i % STAGES, f"Stage {i % STAGES}",
            ))
            if i < SOWS:
                sow_id, version_id = uuid.uuid4(), uuid.uuid4()
                sow_rows.append((sow_id, deal_id))
                version_rows.append((version_id, sow_id, owner_ids[i % OWNERS],
                                     f"load/{i}.pdf", uuid.uuid4().hex * 2))
        cur.executemany(
            "INSERT INTO opportunity (id,hubspot_deal_id,client_id,owner_id,governance_status,"
            "name,amount,close_date,hubspot_pipeline_id,hubspot_stage_id,stage_order,stage_label)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", deal_rows)
        cur.executemany("INSERT INTO sow (id,opportunity_id,version_counter) VALUES (%s,%s,1)", sow_rows)
        cur.executemany("INSERT INTO sow_version (id,sow_id,uploaded_by,file_s3_key,file_hash,"
                        "extract_status,execution_state,version_no,agreements_signed)"
                        " VALUES (%s,%s,%s,%s,%s,'complete','draft',1,false)", version_rows)
seed_seconds = round(time.perf_counter() - seed_started, 1)


async def main():
    import httpx
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db import get_session
    from app.main import app as application

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    counter = {"n": 0}
    event.listen(engine.sync_engine, "before_cursor_execute",
                 lambda *a, **k: counter.__setitem__("n", counter["n"] + 1))

    async def _session():
        async with factory() as session:
            yield session

    application.dependency_overrides[get_session] = _session
    headers = {"X-Test-User": f"load-admin-{run}@example.test"}
    results = {}
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://load",
                                 timeout=120) as client:
        targets = {
            "list": "/pipeline/clients?page=1&page_size=25",
            "filter": "/pipeline/clients?page=1&page_size=25&stage=stage-3&stage=stage-4"
                      f"&search=Load+client+00",
            "summary": "/pipeline/summary",
            "export_csv": "/reports/pipeline/export.csv",
        }
        for name, path in targets.items():
            timings, queries = [], []
            for i in range(REQUESTS):
                counter["n"] = 0
                started = time.perf_counter()
                response = await client.get(path, headers=headers)
                timings.append(time.perf_counter() - started)
                queries.append(counter["n"])
                assert response.status_code == 200, f"{name}: {response.status_code} {response.text[:300]}"
            timings.sort()
            results[name] = {
                "requests": REQUESTS,
                "p50_ms": round(statistics.median(timings) * 1000, 1),
                "p95_ms": round(timings[int(0.95 * REQUESTS) - 1] * 1000, 1),
                "max_ms": round(timings[-1] * 1000, 1),
                "sql_statements_min": min(queries),
                "sql_statements_max": max(queries),
            }

        # T31.02 — pagination correctness across the 10k population.
        seen, total = set(), None
        for page in (1, 2, 50, 99, 100):
            response = await client.get(
                f"/pipeline/opportunities?page={page}&page_size=100", headers=headers)
            assert response.status_code == 200, response.text[:300]
            payload = response.json()
            total = payload.get("total", total)
            ids = [row["opportunity_id"] for row in payload["items"]]
            assert len(ids) == 100, f"page {page} returned {len(ids)} rows"
            assert not (seen & set(ids)), f"page {page} overlaps earlier pages"
            seen.update(ids)
        pagination = {"sampled_pages": [1, 2, 50, 99, 100], "rows_per_page": 100,
                      "total_reported": total, "distinct_rows_seen": len(seen),
                      "overlap": False}
    application.dependency_overrides.pop(get_session, None)
    await engine.dispose()
    return results, pagination


results, pagination = asyncio.run(main())

with psycopg.connect(f"{HOST} dbname=postgres", autocommit=True) as admin:
    admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))

receipt = {
    "run": run,
    "recorded_at": datetime.now(UTC).isoformat(),
    "population": {"deals": DEALS, "clients": CLIENTS, "sows": SOWS,
                   "close_date_buckets": BUCKETS, "stages": STAGES,
                   "owners": OWNERS, "seed_seconds": seed_seconds},
    "environment": {
        "hardware": platform.platform() + f" / {os.cpu_count()} cpus",
        "database": "pgvector/pgvector:pg16 in Docker (dealgate-s21-lead-db), same host",
        "transport": "in-process ASGI (httpx ASGITransport); no network or TLS hop",
        "concurrency": "sequential, single client — single-user latency, not throughput",
    },
    "thresholds": {"list_p95_ms": 2000, "summary_p95_ms": 3000},
    "results": results,
    "pagination": pagination,
    "verdict": {
        "list_within_2s": results["list"]["p95_ms"] <= 2000,
        "filter_within_2s": results["filter"]["p95_ms"] <= 2000,
        "summary_within_3s": results["summary"]["p95_ms"] <= 3000,
    },
}
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
