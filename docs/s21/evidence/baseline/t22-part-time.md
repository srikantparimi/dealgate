# T22 People Capacity: Local Scenario Closure

2026-10-02 23:17UTC. Application e879213a18be8028bafe1a5ce063c4c4c45b1398
(production code unchanged froma5ee76d). Browser84625 passed1/1.2m total,
1.1m test, zero retries/skips/failures. Independent QA reviewed expectations and
the combination of evidence below; no production correction was required.

From tests/e2e, requires newly seeded private fixture and matching API:
```sh
S21_PART_MANIFEST=/tmp/s21-part-fe461783-manifest.json npx playwright test --config playwright.s21-local.config.ts s21-part-time-demand.spec.ts --output test-results/s21-t22-part --reporter=list
```
[Browser assertions](../../../../tests/e2e/local/s21-part-time-demand.spec.ts),
[visible sourcing result](t22-part-time.png), [27 targeted results](t22-capacity.xml).
Backend96252 passed27/13.55s on7a41a72, two existing lifecycle deprecations;
files test_s21_people_company_x.py, test_s21_people_allocation_service.py,
test_s21_demand_allocation.py. From repository root:
```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api api/.venv/bin/pytest api/tests/test_s21_people_company_x.py api/tests/test_s21_people_allocation_service.py api/tests/test_s21_demand_allocation.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-t22-current-7a41 --junitxml=docs/s21/evidence/baseline/t22-capacity.xml
```
Later fixture-only
integration does not change matching code. No broader suite rerun.

## Condition Mapping

- T22.01/.02: existing Company X connected browser in
  [prior S5 mapping](../../scenario-conditions.md#s21ft22---full-team-demand)
  preserves2US+5India at70/40% and Expected/Upside; independent service
  [Company X proof](../../lanes/qa-company-demand.md) supplies the other oracles.
  Current27 cases also verify70->20/100/0/unknown. New browser preserves seven
  half-time slots at70/40%; never probability-weighted headcount.
- T22.03: current service/pure tests exercise global competing accounts and
  filters; one person cannot be duplicated by an account/Sales filter.
- T22.04: real plan/publication, browser roster import and sourcing rules/draft,
  PostgreSQL-backed allocation API. Two US/five India slots at0.5 need3.5FTE.
  OneUSperson1.0 can occupy only one same-line slot (0.5FTE); fourIndia0.5 people
  fillfour slots (2FTE); India0.25 person cannot fill0.5slot. Exact person-key
  sets, matched2.5, gap1, regional gap0.5 each, every interval asserted.
- T22.05: current foreign commitment roll-off cases verify inclusive15Nov,
  capacity available16Nov and peak monthly gap retained.
- T22.06: current retained-person commitments reuse own capacity; seven retained
  plus an eighth slot creates one incremental gap, not eight new hires.
- T22.07: visible sourcing draft US45day/India30day rules produce17Sep/2Oct
  deadlines, both revisions reload and retain identical staffing rows.

Focused additional API check after browser: exact month labels2026-11-01 through
2027-04-01, six adjacent contiguous intervals ending2027-05-01. Exit0.
The browser's original endpoints/count assertions were not changed after its run.
No reservation/hiring; both versions explicitly is_reservation=false. Draft
history[2,1] preserves probabilities0.4/0.7 and identical staffing rows.

## Isolation And Boundaries

Fixture3704473 integratede879213 creates source only, not outcomes. Private DB
s21_part_fe4617831bc2427cb8fb48da2438c1cc OID96637,owner s21,
comment owned-s21-t22:fe4617831bc2427cb8fb48da2438c1cc; schema0061,
seed13153 exit0. Occupied-target guard90632 refuses without writes. API60565
stopped/collected143. Exact ownership rechecked; DROP without FORCE succeeded,
absence count0. Retained s21_journey untouched; manifest no longer reusable.

Local identity adapter and synthetic managed roster, not live HR/Cognito/staging.
No financial pricing, extraction/provider or all signed-amendment continuity
claim. T22 local scenario closure does not close whole FC-07 or operational gates.
