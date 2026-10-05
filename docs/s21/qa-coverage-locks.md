# Independent Coverage Concurrency Proof

Scope: author-only review at `4f2d3ea`, branch `s21/qa-coverage-locks`.
Owned additions: this report and `scripts/s21_coverage_concurrency_pg.py`.
No application changes, runtime, tests, database connections, migrations,
containers, installs or cloud operations were executed by QA for this increment.
Execution evidence was missing at the author-only checkpoint. The subsequent
lead execution below supplies local PostgreSQL evidence, not staging acceptance.

## Lead Execution: 2026-10-02 15:20 UTC

PASS on migrated0059 in private database
`s21_coverage_lock_72bbc8b3c5a849d7867c9c8c236e7fc1`; ordinary owned-database
cleanup confirmed. Sourceec69a2b plus the reviewed initial-fixture correction
(two-slotmapping instead of newly forbidden emptyroot). No assertion weakened.
Same-root actual blockedPID4540 waited on4539, transactionid lock onforecast_plan;
oneaccepted/one409, exact2versions/2audits. Cross-root blockedPID4541 waitedon4540,
transactionid lock onproject; oneaccepted/one422overlap, exact4versions/4audits.
Audit hashchain passed. Both lock observations preceded releasing the writer.
No retained/shared database reset or forced drop; no staging claim.

## Lead Execution

Run only after acquiring the serialized runtime slot, with the existing local
PostgreSQL server on port 55421. From the integrated worktree, use an existing
isolated API environment with psycopg, asyncpg, SQLAlchemy, Alembic and test
dependencies already installed:

```sh
S21_COVERAGE_ADMIN_URL='postgresql+psycopg://s21@127.0.0.1:55421/postgres' PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api:. api/.venv/bin/python scripts/s21_coverage_concurrency_pg.py
```

The script upgrades a newly created private database through the actual Alembic
CLI and checks the migrated head against this checkout's single migration head.
It reuses the canonical project/publication fixtures from
`test_s21_coverage_service` but invokes real plan/publication/coverage services,
commits, ORM queries and PostgreSQL locks. Fixture environment settings are not
feature-response mocks; no metadata-based schema creation is used.

## Literal Race Oracles

1. Same-root CAS: create a valid two-slot revision 1. A writer holds the plan source row
   lock; a separate backend submits another request expecting revision 1. Before
   releasing the writer, observe that exact contender's application name/PID,
   `wait_event_type = Lock`, an ungranted `pg_locks` row, and the writer PID in
   `pg_blocking_pids`, while its active query is the source `FOR UPDATE`. The
   writer commits revision 2. The contender must fail with 409 and stale-coverage
   detail. Expect exactly one root, two versions and two coverage audits.
2. Cross-root project-slot reuse: clear through revision 3. Two different plans
   map their respective slot 0 to the same project slot 0 for inclusive dates
   2026-11-01 through 2027-04-30. The writer holds the project source row lock;
   the other plan's contender must visibly wait on that exact writer before
   release. The writer commits revision 4. The contender must fail with 422
   identifying overlap. Expect one root, four versions, four coverage audits,
   and no second root/version/audit from the rejected new pair.

Each scenario requires one actual accepted service result and one rejected
result; another success, unexpected exception, early completion or missed lock
deadline fails. History is reread in a fresh session. Revision sequences,
request identities, winner version/mappings, per-version audit references and
the complete audit hash chain are checked. Final coverage consumes one slot
once. There is no retry-to-green. Twenty-second observation/service deadlines,
30-second database statement/lock timeouts, 180-second proof and 300-second
migration deadlines bound execution. Three distinct database backends are
required per race; pending contender tasks are cancelled/awaited on failure.

## Safety Boundary

- Only the explicit `S21_COVERAGE_ADMIN_URL` is accepted: psycopg driver, user
  `s21`, literal loopback `127.0.0.1`, port `55421`, database `postgres`, no query
  options. The live administrative database, current user and session user are
  checked. Wrong hosts/ports/databases/identities fail closed. Libpq `PG*`
  environment overrides are removed before connecting.
- Every invocation internally generates `s21_coverage_lock_<32 UUID hex>`.
  No supplied target or drop name, command arguments, existing-database reuse,
  shared schema reset, forced drop or backend termination is supported.
- Admin access only creates the private database, marks it, inspects ownership
  and drops that database. Cleanup requires the same generated name, database
  OID, `s21` owner and unpredictable ownership marker recorded after creation.
  A creation/marker failure or identity mismatch leaves it intact and fails
  visibly. An unexpected remaining connection makes ordinary DROP fail rather
  than terminating it. No `s21_schema`, `s21_lead` or `s21_journey` data is used.
- All application and migration DSNs are overwritten with the private target
  before importing application modules. Proof sessions and both engines close
  before cleanup. Only after successful cleanup does the script print PASS.
  Console evidence includes database name, source revision, migration head,
  observed blocking identities, exact outcomes/counts and cleanup confirmation;
  it does not print credential-bearing DSNs.

## Requirement Status

| Contract slice | State | Evidence |
| --- | --- | --- |
| FC-05/07, T21/22/23 source-lock/CAS concurrent publication coverage | fixed and tested | Lead actual PostgreSQL same-root race, 15:20 UTC; 81278e1 |
| FC-05/07, T21/22/23 globally exclusive project staffing slot | fixed and tested | Lead actual PostgreSQL cross-root race, 15:20 UTC; 81278e1 |
| 0059 append-only coverage/audit counts and rejected-write atomicity | fixed and tested | Fresh-session counts and audit chain passed, 15:20 UTC; 81278e1 |

No concurrency result is claimed from static inspection. This proof alone
cannot establish the full numbered requirements, all schedules/interleavings,
HTTP authorization, browser behavior, archival recovery, schema downgrade,
production least-privilege grants or staging acceptance. Fixtures seed an
approved/released source; they do not prove the approval/signature workflow.
