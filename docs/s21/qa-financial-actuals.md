# Independent Financial Actuals Review

Session: 2026-10-02, bounded 15-minute QA increment; branch `s21/qa-actuals`.
Reviewed source: `83ee51205720e4529e3d98e70f0b743554ee406c`.
Scope: `FinancialImportInput`, `import_financial`, `financial_records`, models,
and the 0051 contract. Only this report and the new independent test file changed.
No production edits, assertion weakening, cloud/shared database/browser access,
migrations, deployment, or shared runtime changes.

## Confirmed Findings

1. **P1: GM references can cross tenant/environment boundaries.**
   `api/app/services/actuals_import.py:613` loads the requested GM, and line 617
   checks only its account relationship. It never checks the commercial
   snapshot's explicit tenant/environment provenance. Both a different tenant
   and a different environment are accepted and committed when the account ID
   matches. The cross-account control correctly returns 422 and writes no fact.
   This is not a PostgreSQL-specific behavior: the required source-provenance
   validation is absent from the service.

2. **P2: stale-correction replay changes the failure contract.**
   `api/app/services/actuals_import.py:634` initially rejects stale revision input
   with 409. The same actor's same idempotency key and identical body reaches
   line 581, which unconditionally replays a failed batch as 422. The observed
   sequence is `[409, 422]`, not `[409, 409]`. A client cannot preserve conflict
   handling across a normal retry. The separate invalid-account whole-batch
   case correctly replays the same 422/error report and creates one audit.

3. **P2: successful replay skips trusted-fixture expiry authorization.**
   `api/app/services/actuals_import.py:577` returns an existing matching batch
   before the account-scope validation at line 611. After a real server-issued
   fixture grant expires, `financial_records` hides its facts and a new
   correction is rejected, but replay of the earlier successful import still
   returns its committed batch. Contract 0051 requires trusted scope before
   every write/read. The observed disclosure is the prior batch response;
   this test does not claim that replay writes another fact or returns amounts.

## Evidence

Own existing QA Python 3.14 virtualenv executable; imports explicitly resolve
from this worktree via `PYTHONPATH=api`. All ledger tests use in-memory SQLite.
The independent fixture enables and verifies `PRAGMA foreign_keys=ON`, so
deletion tests exercise real metadata `SET NULL` behavior, not manual detachment.
`DEALGATE_POSTGRES_URL` is unset to disable the migration hook.

```sh
env -u DEALGATE_POSTGRES_URL PYTHONPATH=api \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest \
  api/tests/test_s21_financial_actuals_independent.py \
  api/tests/test_s21_financial_actuals.py -o addopts=-ra -q
```

Expected/collected/executed **27**; passed **23**; failed **4**; skipped **0**;
xfail **0**; not run **0**. Exit 1, 25.81 seconds. Independent file: 18 cases,
14 passed / 4 failed. All nine existing financial-import tests pass. Ruff check
of the independent file passes. Red assertions were unchanged after first run.

Failing node prefix: `api/tests/test_s21_financial_actuals_independent.py::`

```text
test_gm_link_must_match_account_tenant_and_environment[tenant]
test_gm_link_must_match_account_tenant_and_environment[environment]
test_competing_correction_replay_preserves_conflict_status_and_one_failed_batch
test_fixture_expiry_is_rechecked_on_successful_import_replay
```

Passing independent coverage includes cross-account GM rejection; immutable
account/measure correction identity; whole-batch atomic rejection, one durable
error report/audit and stable replay; literal positive/negative cent round-trips;
long exact amount/FX string preservation at the input boundary; expiry read/new
write fencing; business account and GM deletion with retained original IDs;
append-only corrections to detached business history; deleted-fixture isolation;
and tenant/environment filters on history reads.

Precision expectations are independent literals: `12345.67`, `-12345.67`,
`0.01`, with correction `12000.01`. Long Decimal strings are validated without
float expectations, but that test is input-boundary proof only. No production
calculation output is used to establish expected money. The only time patch
advances the fixture clock past real issuance expiry; no feature service is
mocked. GM fixtures seed stored source metadata, not a signed upload journey.

## Residual Boundaries

The two-actor correction test models competing optimistic revision intentions
sequentially; it is not proof of simultaneous PostgreSQL transactions. Inspection
also finds that `append_audit` at service line 637 can autoflush prepared facts
before the `IntegrityError` handler at line 640. Deleted-account corrections have
no surviving account row to lock. A genuine competing detached-source import
needs a PostgreSQL race test, including durable failed-batch/audit behavior;
this is an unverified concern, not a fourth reproduced finding.

Unscaled PostgreSQL NUMERIC round-trips, numeric precision beyond SQLite's
native representation, migration parity/rollback, crash atomicity, live Finance
sources, browser/API authentication, exports and deployed acceptance are not
proved here. Optional same-account GM-link correction policy was not inferred:
the contract explicitly freezes account/measure identity but does not state
whether correcting a mistaken optional GM link is permitted.

| Item | State | Evidence / remaining boundary |
| --- | --- | --- |
| FC-06 | missing | Durable correction/retention controls pass; GM scope gap remains. |
| FC-12 | missing | Failed-status and expired-fixture replay defects remain. |
| S21F:T21 | deferred | No actual-to-forecast matching basis or full financial journey acceptance. |
| S21F:T25 | deferred | No export/history snapshot or true concurrent Postgres acceptance. |
| S21F:T29 | deferred | No migration run or PostgreSQL numeric/constraint parity proof. |
| S21F:T32 | missing | Cross-scope GM linkage and expiry replay remain fail-open. |

The lead owns implementation changes and integration verification. This report
does not close any feature or staging acceptance gate.
