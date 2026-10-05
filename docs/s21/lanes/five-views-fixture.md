# Five-View Forecast Fixture

Author-only, UNEXECUTED. Owns scripts/s21_five_views_fixture.py and this report.
No tests, imports of the script, HTTP, worker or database activity performed.

Requires existing S21_COV_MANIFEST and a NEW S21_VIEWS_MANIFEST path directly in
/tmp, exclusive-created before mutation. Target guard requires local environment,
literal127.0.0.1:55421/s21, private s21_cov_37eb<28hex>, matching tenant/input
manifest, owned-s21-t21:<suffix> comment, migration0062, explicit reporting settings.
PG overrides and password/options are refused. Existing signed fixture is read,
not reseeded; API preflight must expose that authorized GM before new writes.

Real /dev/test-fixtures creates B and empty accounts; A remains the existing
signed account. Names come from actual Client rows. Real /forecast/plans creates
linked tentative A Jan-Mar2027 fee600/cost100 per month/probability0.50, B Apr-Jun
fee240/cost40 per month/probability0.25. Canonical source/calendar identity is
consistent. Each source has one US full-time Engineer. Skills/level are not fields
of canonical StaffingAssignment, so this script does not pretend to enrich them;
People publication/capability edits remain real browser actions. No49 filler plans.

Separate actual worker runs once, is awaited and its PID/exit/output recorded.
The script refuses an already-running worker with this repository cwd; it does
not control unrelated processes. A120-second limit terminates/collects only the
child it launched. No cloud/storage/mail calls occur. Plan job completion is
verified through the real API, not merely the worker's handled count.

Receipt checkpoints fsync operation intent and API result, generatedIDs and
worker state. Existing receipt always refuses before mutation. Plan idempotency
keys are UUID5(runUUID,A/B). Fixture issuance has no idempotency API: on uncertain
network failure, inspect run-labelled grant audits and preserved receipt before
manual recovery; never automatically recreate. No automatic retries or cleanup.

Independent browser oracle at2026-10-15T12:00:00Z: signed24000 currentmonth/current
quarter; AExpected nextquarter300; B adds60 over nexttwoquarters, future360;
futureUpside840; futureCommitted0; accountAfutureExpected300. All names/IDs,
signedGM/SOW references and literal expected amounts are written to the manifest.
This authoring does not prove those browser outcomes or close T18.

Lead invocation from integrated repository root, with the actual37eb DBname:

```sh
DEALGATE_ENV=local \
DEALGATE_TENANT_ID=DB_NAME \
DEALGATE_REPORTING_TIMEZONE=America/New_York \
DEALGATE_REPORTING_CURRENCY=USD \
S21_COV_MANIFEST=/tmp/s21-actual-coverage-manifest.json \
S21_VIEWS_MANIFEST=/tmp/s21-five-views-manifest.json \
S21_COVERAGE_DATABASE_URL=postgresql+asyncpg://s21@127.0.0.1:55421/DB_NAME \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_five_views_fixture.py
```

API8210 must be owned and configured Finance,SystemAdmin,officeapp-e2e for the
same actor email. No identity group mismatch is introduced. No retained database
or existing financial facts are mutated by fixture seeding.

## Static Constructor Follow-Up

Review caught an incorrect migration prefix guard. It now compares the single
head to the exact SUPPORTED_REVISION constant20261003_0062_actual_coverage.
Authorized lightweight validation session96222 exited0: loading the script without
calling its entrypoint, constructing both A/B components, and Pydantic parsing
both succeeded. Assertions check literal fees600/240, one-person staffing,
matching source identities and calendar/service bounds. No database connection,
API, seed, worker, cloud or heavy test execution occurred. This supersedes the
earlier statement that the script had not been imported; the actual seed remains
unexecuted. Constructor positional parameters match the current canonical types.

## Staffing Cost Correction

Lead execution67649 exposed missing staffing cost_rate/cost_version despite valid
Pydantic construction. The seed now requires real calculate_component completeness
BEFORE any API mutation. Staffing hourly cost is explicitly1 with source version;
the existing monthly100/40 is separately labelled overhead, not a replacement for
staffing cost. Jan/Feb/Mar2027 have21/20/23 weekdays: costs268/260/284, total812.
Apr/May/Jun have22/21/22: costs216/208/216, total640. Revenue remains600/240, and
Expected next-two-quarter revenue360 remains unchanged. Pure calculation check
session40923 passed all literal costs/revenues. An earlier check61860 used wrong
status vocabulary complete instead of canonical ok; it failed before the B check,
not due to changed arithmetic. Session97321 passed both new complete preflights
and repair syntax. No seed/repair/API/DB/worker executed by this worker.

New scripts/s21_five_views_repair.py is lead-only, unexecuted. It guards the owned
37eb database marker/exact schema, original manifest and exact two existing plan
IDs. It preserves the original manifest and writes a separate exclusive receipt.
Each correction uses POST /forecast/plans/{plan_id}/versions, the actual revision
endpoint (not plan creation), original source CAS, stable UUID5 repair request key,
written reason and immutable new version. Original failed versions remain intact.
Repaired source also passes real pure schedule completeness before mutation.
An actual separate worker is bounded/collected, followed by unchanged360 oracle
and owned-source exclusion checks. No reseeding, deletion or direct DB updates.

Lead command with the existing local env/DB configuration:

```sh
S21_VIEWS_MANIFEST=/tmp/s21-five-views-20261003.json \
S21_VIEWS_REPAIR_RECEIPT=/tmp/s21-five-views-repair-20261003.json \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_five_views_repair.py
```

DEALGATE_ENV=local, DEALGATE_TENANT_ID and S21_COVERAGE_DATABASE_URL retain the
same guarded37eb target. Existing receipt refuses; any partial success needs
explicit receipt review and current CAS, never automatic retry or overwrite.
