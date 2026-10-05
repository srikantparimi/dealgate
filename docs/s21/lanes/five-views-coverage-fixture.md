# Expanded Coverage Controls Fixture

Author-only, UNEXECUTED. Owns only scripts/s21_five_views_coverage_fixture.py and
this report. No imports/tests/runtime/API/database/cloud executed by the worker.
Pure calculate_component preflight is built into the script before any write.

Requires same original S21_VIEWS_MANIFEST, owned37eb private DB/tenant/user/port,
exact SUPPORTED_REVISION20261003_0062_actual_coverage and ownership comment.
S21_VIEWS_COVERAGE_MANIFEST must be a new exclusive /tmp path. Intent and response
receipts are fsynced incrementally; failed partial fixtures are preserved, never
reseeded automatically. Existing manifests/rows are not overwritten or deleted.

Real /dev/test-fixtures creates new accountC/deal. Only this new source receives
explicitly synthetic confirmed SOW, real save_commercial_model, seeded released
package and real project_lifecycle.create_or_link. This is a declared prerequisite,
NOT extraction/signature/release verification. No objects/provider calls happen.
A real /forecast/plans request adds a tentative mirror linked to that same C deal.
Existing signed accountA, accountB and their financial facts are untouched.

Both sources have quantity2 Engineers and quantity2 Analysts, allocation1,
January1-March31 2027, New York calendar, hourlycost1/version and fixedfee600 plus
separate monthly overhead100. Literal complete costs772/740/836 reflect four
people times168/160/184 paid hours plus100; total2348. The pure preflight checks
these exact amounts, fee600 and no missing economics, not only parse success.

Demand publications and manual skills/level evidence are intentionally pending
for lead's real UI/API: Engineer/python/Senior and Analyst/analysis/Senior.
No demand, sourcing draft or coverage mapping is seeded. Forecast job remains
pending for lead's existing bounded separate worker; this script launches none.
After both publications: four committed project heads plus four tentative plan
heads before explicit coverage. Lead maps source lines/slots and verifies CAS,
history, clear revision and immutable prior versions through actual controls.

Manifest records actor/database/run/account/deal/project/plan identities and
titles, GM/SOW/package versions, January-March bounds and literal expectations.
AccountC changes company totals once materialized: keep coverage proof scoped to
C and do not reuse pre-C company360 assertions without excluding this new scope.

Lead command with existing guarded local environment/37eb DB URL:

```sh
S21_VIEWS_MANIFEST=/tmp/s21-five-views-20261003.json \
S21_VIEWS_COVERAGE_MANIFEST=/tmp/s21-five-views-coverage-20261003.json \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_five_views_coverage_fixture.py
```

Retain DEALGATE_ENV=local, matching DEALGATE_TENANT_ID and
S21_COVERAGE_DATABASE_URL. API8210 must use the original authorized fixture actor.
No existing field is repaired directly, no49 filler plans are created, and this
authoring does not establish T18.06 or staging acceptance.
