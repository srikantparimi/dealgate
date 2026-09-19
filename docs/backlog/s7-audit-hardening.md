# S7 — audit_event UPDATE/DELETE grant revocation + nightly S3 Object Lock export

## User story
As Finance, the audit chain must be genuinely append-only at the database
level — not just enforced by the application. The blueprint §12 says
"the application DB user has no UPDATE or DELETE on it". Currently only
enforced in the app. Ship the DB-level guarantee and the nightly export
with Object Lock so a compromise of the RDS instance cannot silently
rewrite history.

## Acceptance
- New alembic migration `20260919_XXXX_audit_hardening.py`:
  - Creates a Postgres role `dealgate_audit_writer` if not exists (idempotent).
  - `REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM dealgate_admin` (or whatever the app's role is).
  - `GRANT INSERT, SELECT ON audit_event TO dealgate_admin`.
  - Add a Postgres trigger `audit_event_no_update` that RAISES on UPDATE or DELETE. Belt + braces.
  - Skip on SQLite (the app-run tests use SQLite where grants don't exist; guard with `if op.get_bind().dialect.name == "postgresql"`).
- Test on Postgres (integration test using testcontainers-like setup OR docker-compose smoke that spins up postgres and applies the migration). If testcontainers add too much dep weight, gate the test behind an env flag `DEALGATE_POSTGRES_URL` and skip when absent — CI/staging will exercise it.

- Nightly S3 export worker `worker/audit_export.py`:
  - Runs 03:00 UTC daily via EventBridge (add to `infra-tf/modules/schedulers`).
  - Streams the previous day's `audit_event` rows to `s3://officeapp-dev-audit-exports-{account}/YYYY/MM/DD/audit.jsonl.gz`.
  - Bucket has **S3 Object Lock in COMPLIANCE mode, 7-year retention** (Terraform).
  - Emits `audit_export.written` audit row on success (chain continues).
  - Idempotent: if the day's key already exists, no-op unless the row count mismatches (then writes a `-r2.jsonl.gz` sidecar and audits `audit_export.reprocessed`).

## Data touched
- `audit_event` grants revoked; no new tables.
- New S3 bucket `officeapp-dev-audit-exports-{account}` with Object Lock.

## Roles
- Worker runs as the ECS task role; no user endpoint.

## Notes
- Blueprint §12.
- The `sqlalchemy.util` monkey-patched by Agent T's `env.py` naming
  convention already keeps SQLite migrations working; the new trigger
  wraps with the same postgresql-only guard.
