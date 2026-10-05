# Plan Staffing Source Binding

Bounded correction on `s21/plan-staffing-binding`, isolated from integrated
`eda7300`. Production ownership is only `forecast_plans._bind`.

## Defect and Change

Saving a forecast plan previously rebound component source ID, source version
and policy version but retained the staffing assignments' former identities.
The real worker therefore encountered incomplete staffing bindings; cost-free
demand projection correctly rejected those same persisted components.

Before rebinding, `_bind` now validates each assignment against its original
enclosing component across source ID/version, component ID, profile version,
policy version, currency and timezone. A mismatch is HTTP 422, not silently
repaired. Valid assignments are copied with the same new source ID/version and
policy as their enclosing component. Existing hybrid recursion applies this
to children as well. Component, assignment, original request and prior plan
versions remain immutable. No historical-data migration or worker repair was
added; corrupt historical inputs still need an explicit reviewed correction.

## Proof

Sixteen new regression cases were authored before changing `_bind`; all 16
failed against the previous implementation. The tests cover ordinary and
hybrid plans, all seven mismatched original binding fields, saved commercial
revisions, assumption revisions, actual `process_plan_jobs` execution and
persisted successful schedules. Cost-free `project_staffing` produces equal
demand rows across revisions, with stable identity and original evidence.

The worker success assertion uses the canonical schedule status `ok`, not the
word `complete`; no existing tests or fixtures were altered.

Final combined run: **73 passed, 2 existing FastAPI deprecation warnings in
53.24s**, no skips or xfails.

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-plan-binding/api
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_plan_staffing_binding.py tests/test_s21_forecast_plans.py tests/test_s21_plan_assumptions.py tests/test_s21_demand_source.py -q -o addopts= -p no:cacheprovider
```

Local service/worker tests do not replace real connected publication and
staging proof, which remain integration-lead work.
