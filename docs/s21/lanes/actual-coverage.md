# Pure Actual Coverage Reconciliation

Base8ec2a8e, branch s21/actual-coverage. Owns only gm/coverage.py,
test_s21_actual_coverage.py and this report. No database, API, migration,
provider, shared runtime or frontend edits.

Tests were authored first. Test execution was held while the lead owned runtime;
the first execution occurred after implementation, so there is no observed
red-before-fix claim. Authorized focused run session68264 exited0: **28 passed**.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
-m pytest -p no:cacheprovider tests/test_s21_actual_coverage.py -q
```

Run from this worktree's api directory. No broader suite was run. Heavy runtime
slot released immediately after the finite run.

## API And Decisions

reconcile_actual_coverage(schedules, records, as_of=..., timezone=..., currency=...)
accepts authorized raw signed schedule dictionaries and financial_records JSON
with optional coverage. Only the current local month enters this estimate; the
caller keeps all Signed schedule/actuals measures separately. Output rows retain
row_id/source_id/source_version/account_id/month, with revenue and cost objects
containing scheduled, actual_to_date, covered_fraction, uncovered_forecast,
estimate, actual_ids. Top level: rows, excluded{id,reason}, cutoff, currency and
totals{revenue,cost,profit,gm_pct}. Money/fractions are Decimal; gm_pct is a ratio
using existing GM_PRECISION, not multiplied by100 or display-rounded.

Exact match is GM:index plus SOW version/account/month. Only recognized_revenue
and delivery_cost accept explicit Finance evidence. Source date and through_date
cannot exceed cutoff, source date cannot precede through_date, and through_date
must be in the matched month. No inferred elapsed-day weights or financial-basis
equivalence. Detached/unmatched/legacy/invoice/cash records remain visibly excluded.
Raw schedule and actual FX each require explicit positive rate/version/date when
not reporting currency. Unknown signed cost cannot establish uncovered cost.

Latest source_system/source_id revision wins; historical revisions are disclosed
as excluded, not combined. Caller remains responsible for authorized immutable
revision retrieval and signed-source provenance. The function does not itself
query signature or validate UUID existence. Duplicate record/schedule identities
are rejected, not counted twice. Every participant in overlapping same-row,
same-measure scope is excluded; adjacent/disjoint intervals remain usable.

Literal oracle:24000 signed revenue,10000 signed cost, half certified scope,
recognized11000.99 and cost6000 ->23000.99 revenue/11000 cost/12000.99 profit.
Correction recognized10500 ->22500 revenue/11500 profit. Tests also cover
unknown/zero/negative amounts, scope mismatches, cutoff/timezone, FX, transitive
overlap, duplicates and ambient Decimal precision independence.

## Remaining Integration

Lead owns persisted coverage validation/batch atomicity, overlap locking,
correction audit/history, migration, actual import UI/API, entitlement filtering,
outlook composition and connected same-project proof. Pure dictionary fixtures
do not verify those boundaries or close T21.07/FC-06/staging. Signed schedule
immutability and caller source authorization must be asserted in integration.

## Aggregate Precision Follow-Up

Read-only integration review identified unhandled exact-precision failures while
adding individually representable row totals or subtracting cost from revenue.
Two literal regressions were added before the repair. Session32542:28 passed,
2 failed with Decimal.Inexact. Session36384 after repair:30 passed, exit0, same
focused command. No assertions weakened; the original28 tests are unchanged.

Unrepresentable totals now emit a totals:revenue/cost/profit exclusion with a
review reason. That total and dependent profit/GM remain null; independently
representable totals and original per-row amounts remain intact. No rounding or
overflow value is presented as an exact financial result. Runtime released.

## Private Workflow Fixture

scripts/s21_actual_coverage_fixture.py is a separately authorized author-only
artifact. It preserves unrelated rows in the lead-owned private clone. Guard:
explicit local, s21 user/owner at127.0.0.1:55421, s21_cov_<32hex>, matching tenant,
database comment owned-s21-t21:<same32hex>, migration0062, explicit USD/reporting
timezone. Duplicate deterministic Finance actors or fixture source cause refusal.
No database lifecycle, runtime service, provider or storage operation is performed
by authoring. Lead alone runs the seed. The seed's transaction uses a savepoint
around real save_commercial_model, preserving outer rollback on validation errors.

Two Finance users receive a real fixture grant. One confirmed synthetic SOW
produces exactly one24000-revenue/10000-cost row in the current local reporting
month through the real commercial service. A released approval package and
verified signature row are explicitly seeded prerequisites, with a test audit
marker and empty storage keys. This does NOT prove extraction, approval routing,
signature verification or release. Existing financial/import counts must remain
unchanged; no actuals are seeded. The manifest exposes actor/source identities,
cutoff, month, row0 and literal expected financial amounts. Half certified scope
is not inferred from the number of elapsed days.

Lead invocation from repository root:

```sh
DEALGATE_ENV=local \
DEALGATE_TENANT_ID=s21_cov_3cba7a6d8a5c429c8b003047ea2d0cc2 \
DEALGATE_REPORTING_TIMEZONE=America/New_York \
DEALGATE_REPORTING_CURRENCY=USD \
S21_COVERAGE_DATABASE_URL=postgresql+asyncpg://s21@127.0.0.1:55421/s21_cov_3cba7a6d8a5c429c8b003047ea2d0cc2 \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_actual_coverage_fixture.py > /tmp/s21-actual-coverage-manifest.json
```

Only syntax is checked before handoff; no fixture execution, database access or
connected workflow is claimed. Lead performs imports/correction/concurrency and
the actual Forecast UI proof, including proper source scoping in the clone.

## Same-Identity Lock Regression

New scripts/s21_finance_identity_race.py is authored only, UNEXECUTED. No test,
database, HTTP or provider operation was run for this artifact. It requires
S21_COV_MANIFEST and S21_COVERAGE_DATABASE_URL plus matching local tenant. Guard
checks private s21_cov_<32hex>, literal127.0.0.1:55421, s21 owner/user and exact
owned-s21-t21:<suffix> comment; manifest actor must be the existing local UUID5.
No users, groups or financial records are seeded directly and no rows are deleted.

The executable proof locks only the fixture client in an independent transaction,
starts one real POST http://127.0.0.1:8210/actuals/financial-import with a unique
source and uncovered USD1 recognized amount, then observes its exact client
FOR UPDATE waiter through pg_blocking_pids. It verifies the API's committed
identity is SystemAdmin+Finance+officeapp-e2e before invoking real ensure_user
for the SAME identity with Finance+officeapp-e2e in a separate session. The
expectation is that this second authorized token sync commits while the first
import remains blocked. Four-second statement timeout makes old User-lock
behavior fail deterministically; no retries or mocked feature responses.

Both success and failure release the owned client blocker and collect the HTTP
task, printing PIDs/status/error and preserving resulting imports/audits. No
force-cancellation, destructive cleanup or shared-session termination occurs.
Local X-Test-User and direct AuthUser stand in for two authenticated token group
sets; this is actual application/PG locking proof, not Cognito verification.

Lead runs from root against the owned clone/API, with Admin+Finance+officeapp-e2e
local API groups:

```sh
DEALGATE_ENV=local \
DEALGATE_TENANT_ID=s21_cov_3cba7a6d8a5c429c8b003047ea2d0cc2 \
S21_COV_MANIFEST=/tmp/s21-actual-coverage-manifest.json \
S21_COVERAGE_DATABASE_URL=postgresql+asyncpg://s21@127.0.0.1:55421/s21_cov_3cba7a6d8a5c429c8b003047ea2d0cc2 \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_finance_identity_race.py
```
