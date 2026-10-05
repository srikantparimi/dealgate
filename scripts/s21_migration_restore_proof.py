"""S21F:T29.05 — populated rollback, loss refusal, malformed-data atomicity,
concurrent upgrade, and real pg_dump/pg_restore restoration proof.

Owned disposable databases only (`s21_restore_*`); nothing shared is
touched. Receipt: docs/s21/evidence/baseline/t29-restore-proof.json.
Run from the repo root with the api venv:
    .venv/bin/python ../scripts/s21_migration_restore_proof.py  (from api/)
"""

import json
import subprocess
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

HOST = "host=127.0.0.1 port=55421 user=s21"
CONTAINER = "dealgate-s21-lead-db"
HEAD = "20261003_0063_agreement_versions"
ROLLBACK_TARGET = "20261002_0061_automation_jobs"
MALFORMED_AT = "20261002_0052_deletion_retention"
MALFORMED_NEXT = "20261002_0053_parent_deletion"

TABLES = ["user", "client", "opportunity", "sow", "sow_version", "gm_model",
          "approval_package", "renewal", "task", "deletion_job"]

run = uuid.uuid4().hex[:12]
root = Path(__file__).resolve().parents[1]
receipt_path = root / "docs/s21/evidence/baseline/t29-restore-proof.json"
receipt = {"run": run, "started": datetime.now(UTC).isoformat(), "legs": {}}


def admin(statement, *args):
    with psycopg.connect(f"{HOST} dbname=postgres", autocommit=True) as conn:
        conn.execute(statement, *args)


def make_config(database):
    config = Config(str(root / "api/alembic.ini"))
    config.set_main_option("script_location", str(root / "api/alembic"))
    config.set_main_option(
        "sqlalchemy.url", f"postgresql+psycopg://s21@127.0.0.1:55421/{database}"
    )
    import app.db
    app.db.DATABASE_URL = f"postgresql+psycopg://s21@127.0.0.1:55421/{database}"
    return config


def fingerprint(database):
    out = {}
    with psycopg.connect(f"{HOST} dbname={database}") as conn:
        for table in TABLES:
            row = conn.execute(sql.SQL(
                "SELECT count(*), coalesce(md5(string_agg({} :: text, '|' "
                "ORDER BY id)), '') FROM {}"
            ).format(sql.Identifier(table), sql.Identifier(table))).fetchone()
            out[table] = [row[0], row[1]]
    return out


def seed(database):
    ids = {name: uuid.uuid4() for name in
           ("user", "client", "opp", "sow", "version", "gm", "package",
            "renewal", "task", "deletion")}
    with psycopg.connect(f"{HOST} dbname={database}") as conn:
        conn.execute('INSERT INTO "user" (id,email,name,groups) VALUES (%s,%s,%s,%s)',
                     (ids["user"], f"restore-{run}@example.test", "Restore Proof", '["Sales"]'))
        conn.execute("INSERT INTO client (id,name) VALUES (%s,%s)",
                     (ids["client"], f"Restore client {run}"))
        conn.execute("INSERT INTO opportunity (id,client_id,owner_id,governance_status)"
                     " VALUES (%s,%s,%s,'Intake')", (ids["opp"], ids["client"], ids["user"]))
        conn.execute("INSERT INTO sow (id,opportunity_id,version_counter) VALUES (%s,%s,1)",
                     (ids["sow"], ids["opp"]))
        conn.execute("INSERT INTO sow_version (id,sow_id,uploaded_by,file_s3_key,file_hash,"
                     "extract_status,execution_state,version_no,agreements_signed)"
                     " VALUES (%s,%s,%s,'restore/v1.pdf',%s,'complete','draft',1,false)",
                     (ids["version"], ids["sow"], ids["user"], uuid.uuid4().hex * 2))
        conn.execute("INSERT INTO gm_model (id,opportunity_id,sow_version_id,engagement_type,"
                     "version,created_by) VALUES (%s,%s,%s,'fixed_price',1,%s)",
                     (ids["gm"], ids["opp"], ids["version"], ids["user"]))
        conn.execute("INSERT INTO approval_package (id,opportunity_id,sow_version_id,gm_model_id,"
                     "package_hash,status,submitted_by) VALUES (%s,%s,%s,%s,%s,'released',%s)",
                     (ids["package"], ids["opp"], ids["version"], ids["gm"], "f" * 64, ids["user"]))
        conn.execute("INSERT INTO renewal (id,opportunity_id,term_end,trigger_date,status)"
                     " VALUES (%s,%s,%s,%s,'open')",
                     (ids["renewal"], ids["opp"], date(2027, 3, 31), date(2027, 1, 31)))
        conn.execute("INSERT INTO task (id,owner_id,subject,status,escalation_level,category)"
                     " VALUES (%s,%s,'Restore proof task','assigned',0,'closeout')",
                     (ids["task"], ids["user"]))
        conn.execute("INSERT INTO deletion_job (id,tenant_id,environment,sow_id,subject_type,"
                     "subject_id,status,summary,objects,attempts) VALUES "
                     "(%s,%s,'local',%s,'sow',%s,'pending','{}','[]',0)",
                     (ids["deletion"], f"restore-{run}", ids["sow"], ids["sow"]))
    return ids


# ---- leg 1: populated rollback window + fingerprint-stable re-upgrade ----
primary = f"s21_restore_{run}"
admin(sql.SQL("CREATE DATABASE {} OWNER s21").format(sql.Identifier(primary)))
admin(sql.SQL("COMMENT ON DATABASE {} IS {}").format(
    sql.Identifier(primary), sql.Literal(f"owned-s21-restore:{run}")))
config = make_config(primary)
command.upgrade(config, "head")
ids = seed(primary)
before = fingerprint(primary)
command.downgrade(config, ROLLBACK_TARGET)
command.upgrade(config, "head")
after = fingerprint(primary)
assert before == after, f"populated rollback window changed data: {before} != {after}"
receipt["legs"]["populated_rollback"] = {
    "window": f"head..{ROLLBACK_TARGET}..head", "fingerprint_stable": True,
    "tables": before}

# ---- leg 2: populated loss-refusal (downgrade guard with real history) ---
with psycopg.connect(f"{HOST} dbname={primary}") as conn:
    conn.execute("INSERT INTO agreement (id,client_id,kind,file_key,filename,file_size,"
                 "uploaded_by,version_no) VALUES (%s,%s,'NDA','restore/nda.pdf','nda.pdf',9,%s,2)",
                 (uuid.uuid4(), ids["client"], ids["user"]))
    conn.execute("INSERT INTO agreement_file_version (agreement_id,version_no,file_key,"
                 "filename,file_size,uploaded_by,file_hash) "
                 "SELECT id, 2, 'restore/nda-v2.pdf','nda-v2.pdf',9,%s,%s FROM agreement "
                 "WHERE kind='NDA' LIMIT 1", (ids["user"], "a" * 64))
refused = False
try:
    command.downgrade(config, "20261003_0062_actual_coverage")
except RuntimeError as error:
    refused = "discard evidence" in str(error)
with psycopg.connect(f"{HOST} dbname={primary}") as conn:
    at_head = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
    history = conn.execute("SELECT count(*) FROM agreement_file_version").fetchone()[0]
assert refused and at_head and history >= 1, "populated downgrade was not refused safely"
receipt["legs"]["populated_loss_refusal"] = {
    "refused": refused, "still_at_head": at_head, "history_rows": history}

# ---- leg 3: real backup/restore (pg_dump -Fc -> pg_restore) --------------
restored = f"s21_restore_rest_{run}"
dump_file = f"/tmp/s21-restore-{run}.dump"
subprocess.run(["docker", "exec", CONTAINER, "pg_dump", "-U", "s21", "-Fc",
                "-f", dump_file, primary], check=True)
admin(sql.SQL("CREATE DATABASE {} OWNER s21").format(sql.Identifier(restored)))
subprocess.run(["docker", "exec", CONTAINER, "pg_restore", "-U", "s21",
                "-d", restored, dump_file], check=True)
source_fp, restored_fp = fingerprint(primary), fingerprint(restored)
assert source_fp == restored_fp, "restored database does not match its source"
with psycopg.connect(f"{HOST} dbname={restored}") as conn:
    restored_head = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
assert restored_head == HEAD
receipt["legs"]["backup_restore"] = {
    "tool": "pg_dump -Fc / pg_restore (container pg16)",
    "fingerprint_equal": True, "restored_alembic_head": restored_head}

# ---- leg 4: malformed data fails the migration atomically ----------------
malformed = f"s21_restore_mal_{run}"
admin(sql.SQL("CREATE DATABASE {} OWNER s21").format(sql.Identifier(malformed)))
mal_config = make_config(malformed)
command.upgrade(mal_config, MALFORMED_AT)
with psycopg.connect(f"{HOST} dbname={malformed}") as conn:
    # Simulated drift + bad row: a deletion_job without its sow. 0053's
    # backfill derives subject_id from sow_id, then requires NOT NULL.
    conn.execute("ALTER TABLE deletion_job ALTER COLUMN sow_id DROP NOT NULL")
    conn.execute("INSERT INTO deletion_job (id,tenant_id,environment,sow_id,status,"
                 "summary,objects,attempts) VALUES (%s,'malformed','local',NULL,"
                 "'pending','{}','[]',0)", (uuid.uuid4(),))
failed_cleanly = False
try:
    command.upgrade(mal_config, MALFORMED_NEXT)
except Exception as error:  # noqa: BLE001 — the failure class is the proof
    failed_cleanly = True
    receipt["legs"]["malformed_atomicity"] = {"error": type(error).__name__}
with psycopg.connect(f"{HOST} dbname={malformed}") as conn:
    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    partial = conn.execute("SELECT count(*) FROM information_schema.columns WHERE "
                           "table_name='deletion_job' AND column_name IN "
                           "('subject_type','subject_id')").fetchone()[0]
assert failed_cleanly and version == MALFORMED_AT and partial == 0, \
    f"malformed upgrade was not atomic: version={version} partial_columns={partial}"
receipt["legs"]["malformed_atomicity"].update({
    "version_unchanged": version == MALFORMED_AT, "no_partial_ddl": partial == 0})

# ---- leg 5: concurrent upgrades end at head without corruption -----------
# Separate OS processes, as in real deploys: two alembic runs in one
# interpreter deadlock on shared env.py state, which is not the scenario.
concurrent = f"s21_restore_conc_{run}"
admin(sql.SQL("CREATE DATABASE {} OWNER s21").format(sql.Identifier(concurrent)))
helper = (
    "import sys\n"
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "import app.db\n"
    "app.db.DATABASE_URL = sys.argv[2]\n"
    "config = Config(sys.argv[1] + '/alembic.ini')\n"
    "config.set_main_option('script_location', sys.argv[1] + '/alembic')\n"
    "config.set_main_option('sqlalchemy.url', sys.argv[2])\n"
    "command.upgrade(config, 'head')\n"
)
conc_url = f"postgresql+psycopg://s21@127.0.0.1:55421/{concurrent}"
procs = [
    subprocess.Popen(
        [str(root / "api/.venv/bin/python"), "-c", helper, str(root / "api"), conc_url],
        cwd=str(root / "api"), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    for _ in range(2)
]
errors = []
for proc in procs:
    _, stderr = proc.communicate(timeout=600)
    if proc.returncode != 0:
        errors.append(stderr.decode(errors="replace").strip().splitlines()[-1][:200])
with psycopg.connect(f"{HOST} dbname={concurrent}") as conn:
    rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
assert rows == [(HEAD,)], f"concurrent upgrade corrupted version table: {rows}"
assert len(errors) <= 1, f"both concurrent upgrades failed: {errors}"
receipt["legs"]["concurrent_upgrade"] = {
    "final_head": HEAD, "version_rows": 1,
    "loser_errors": errors, "winners": 2 - len(errors)}

# ---- cleanup: drop every owned database and the container dump -----------
for database in (primary, restored, malformed, concurrent):
    admin(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
subprocess.run(["docker", "exec", CONTAINER, "rm", "-f", dump_file], check=True)
receipt["finished"] = datetime.now(UTC).isoformat()
receipt["cleanup"] = "all owned databases dropped; container dump removed"
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
