# T21 Coverage Replacement: Local Pass

2026-10-03 00:41 UTC. T21.07 verified locally; all eight mapped T21 conditions
now support local scenario closure. Latest application19ca6f7e51ce2b367ac692eb057199aeeeb79144.
Worker27b7634->fc3d4a2, precision repairb9c2af4->3be9f31; lead persistence,
outlook and UI delta tested before checkpoint. No staging deployment.

## Current Evidence

- API88908:78 passed; XML [t21-coverage-api.xml](t21-coverage-api.xml).
  Commands from api:
  `.venv/bin/pytest tests/test_s21_coverage_import.py tests/test_s21_actual_coverage.py tests/test_s21_financial_actuals.py tests/test_s21_financial_actuals_independent.py -q --junitxml=../docs/s21/evidence/baseline/t21-coverage-api.xml`
- UI32228:15 passed/2files9.79s on final presentation (earlier46547=15/11.33s). From web:
  `npx vitest run src/__tests__/v2/CurrentEstimate.test.tsx src/__tests__/v2/Forecast.test.tsx`.
- TypeScript14973 exit0: `npx tsc --noEmit` from web.
- Alembic0062 forward/back/forward on private clone passes. Later live imports
  with JSON-null coverage remain downgrade-safe; real coverage history refuses
  downgrade and leaves0062 intact. Retained journey DB remains0061 at this snapshot.
- Literal service assertion:24000/10000 schedule, half matched11000.99/6000
  ->23000.99/11000 estimate, profit12000.99. Correct recognized10500 ->22500.
  Original schedule preserved; billed15000/cash8000 separate; Sales no estimate.
- Schema/input/whole-batch rejection, current-source overlap/correction, legacy
  replay hash, unsigned/latest-pending-upload/FX/version/month refusals pass.

Browser76926 PASSED1/51.8s (test46.5s) at637d816 afterdf8c375 repair:
real HTTPimport/replay, exact displayed estimates, correction/reload, unchanged
signed source, observed two-PG-waiter/client-lock race201/422 with overlap reason
and exact winning amount/scope. JSON-null-only downgrade/upgrade succeeds;
covered history downgrade correctly refuses and version stays0062.
[JSON proof](t21-coverage-proof.json), [screenshot](t21-coverage.png).
Same-identity PG11028 now passes after observed75253 red: identity group sync
commits while real import is still blocked on account. [Red](t21-identity-red.json)
and [green](t21-identity-green.json). New financial-request advisory lock replaces
User FOR UPDATE;48 targeted import74287 pass, [XML](t21-import-repair.xml).
Current/replay browser33980 passes1/16.2s (test11.2s): two concurrent same-key
HTTP requests return same batch with exactly one fact/batch;22500/11000 remains
through desktop/mobile reload. This is functional concurrent replay evidence,
not an observed advisory-lock waiter proof. [Desktop](t21-current-desktop.png)
and [mobile](t21-current-mobile.png) visually checked; tables scroll internally.
QA independently reviewed assertion coverage and both lock repairs; no remaining
narrow finding. The complete browser flow was not rerun after the second lock
repair: focused PG, replay/render and import regressions cover that change.
Full financial import UI and legacy ActualPeriod reconciliation remain parent
FC-06 work, not closed by this additive current-period estimate.

## Historical Failures And Repairs

-Browser25939 reached all exact financial UI/correction assertions, then failed
  two-user race:201/500, not201/422. [PostgreSQL deadlock](t21-pg-deadlock.log)
  shows account-lock/audit-chain inversion: ensure_user group sync held global
  audit42424242 before account lock; other importer held account then waited
  audit. Fix authored in financial-import route: commit identity sync and its
  audit BEFORE financial transaction; batch rows/audit remain atomic. No retry.
  Repair30450 passed48 targeted import tests. New isolated clone37ebcb10...
  for proof; old3cba7a6d... retained for diagnosis. Race assertions strengthened
  with exact waiter PIDs/queries/blocker graph, loser overlap reason and stored
  winning100/[0.5,0.75) source.
-23602 baseline fails: coverage rejected as unknown input, before implementation.
-87550:38 passed initial input + existing ledger regressions.
-43872:18 passed source/revision/legacy-hash tests.
-22863:76 passed before final whitespace/package-order/precision repairs.
-Worker32542:28 pass/2 aggregate-precision failures;36384:30 pass after
  explicit unresolved totals/exclusions. No silent rounding.
-QA static findings: old verified upload must not qualify after new pending
  replacement; absent JSON null must not block downgrade; both repaired.
-Worker static findings: normalize written evidence whitespace, resolve any
  valid same-GM package before deduplication; both repaired in lead source.

All evidence local. No known skips/retries/feature-response mocks in API proof.
UI component tests use supplied props as unit boundaries; real connected proof
is separately identified above. Seeded signature and local auth never stand in
for signature/provider/Cognito/staging acceptance.

## Exact Runtime Commands

From tests/e2e, completed full flow (requires a fresh empty-actuals fixture):
`S21_COV_MANIFEST=/tmp/s21-cov-37ebcb10-manifest.json npx playwright test --config playwright.s21-local.config.ts s21-actual-coverage.spec.ts --output test-results/s21-t21-repaired --reporter=list`

Focused current/replay check on the completed fixture:
`S21_COV_MANIFEST=/tmp/s21-cov-37ebcb10-manifest.json npx playwright test --config playwright.s21-local.config.ts s21-actual-coverage-current.spec.ts --output test-results/s21-t21-current --reporter=list`

From repository root, completed PG identity check:
`S21_COV_MANIFEST=/tmp/s21-cov-37ebcb10-manifest.json S21_COVERAGE_DATABASE_URL=postgresql+asyncpg://s21@127.0.0.1:55421/s21_cov_37ebcb10ed7f4528b7f34c846fed747b DEALGATE_ENV=local DEALGATE_TENANT_ID=s21_cov_37ebcb10ed7f4528b7f34c846fed747b api/.venv/bin/python scripts/s21_finance_identity_race.py`

Both private databases are owned markers, not staging data. Never reset retained
s21_journey. Current cleanup/disposition is recorded in the handoff.
