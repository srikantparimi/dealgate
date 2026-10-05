# T19 Connected Commercial Edits

Lead owns Forecast router/service, forecast API types, NextOpportunities,
new PlanCommercialEditor, test_s21_plan_terms.py, ForecastOpportunities tests,
and local/s21-preview-edits.spec.ts. No migration. No worker owns these files.

Existing shared pricing/calendar/hybrid/period-cost controls edit a cloned plan
input. Profile and source identity remain read-only; dates do not silently shift
allocations, costs or calendars. Written reasons and optimistic version checks
are mandatory. Backend loads authoritative prior metadata under plan lock,
preserving title, account/deal, probability, lifecycle, scenario selection and FX.
New commercial revision uses existing immutable save/job/audit machinery and
current commercial policy; assumption-only edits retain their existing behavior.
Identity synchronization commits before plan locks, using canonical invited-user
identity. No preview math is implemented in the browser.

## Evidence And History

T19 CLOSED LOCALLY on application44fec5163c722e87eaeb69f0c486ce32a875d4c0.
Independent QA required old-quarter removal and final cost/scenario checks;
1474 old-period check passed, strengthened93529 passed1/28.9s. Final artifact
`docs/s21/evidence/baseline/t19-preview-old-period.json` proves December228200,
companyQ4690200, MeridianQ445000, no old source row, latest-v4-only Jan economics
0/0,18000/9000,36000/18000 and companyfuture174000/684400/930400 across scenarios.
Expected futurecost395840. All five original T19 conditions are supported by the
combined exact evidence; no parent requirement/staging/PO/main completion inferred.

- API38413 reproduced missing endpoint404.20108 passed preservation, stale409,
  immutable prior, Finance allowed/Sales denied.
- QA identified absent/invited-user identity gap.3054 reproduced both incorrect
  missing User and noncanonical author (SQLite does not enforce PostgreSQL FK).
  Fix passed. Combined54166 exposed test override leakage into the next role test;
  monkeypatch now restores it.64316 all9passed, XML t19-plan-terms.xml.
- UI58226 reproduced missing editor button.71788 all8 existing/new opportunity
  tests pass.3359 caught incomplete test fixture and missing new PeriodCost source
  ID; fixed,96773 typecheck exit0.
- Browser54224 PASSED1/1.7min on44fec5163c722e87eaeb69f0c486ce32a875d4c0.
  Prior55205 failed before mutations because the restarted API was not listening;
  waited for startup and /me200 before54224. No retries enabled or assertions weakened.
  Desktop/mobile screenshots inspected; no horizontal overflow at390px.
  Proof JSON t19-preview-edits.json records immutable versions2/3/4 and exact totals.
  Read-only PostgreSQL history additionally confirms version1 Dec30000/.35 remains,
  version2 Jan30000/.35, version3 Jan36000/.35, version4 Jan36000/.5.
  The test requires pristine
  Meridian follow-on plan version1 in /tmp/s21-preview-ab7182f1.json. It changes
  December to January explicitly in service/allocation/cost dates, fee30000 to
  36000, then probability.35 to.5; separate real worker after every save.
  Expected company future totals676900,679000,684400; account10500,12600,18000.
  Do NOT rerun the test now: Meridian is version4, so pristine-version1 precondition
  intentionally fails. Inspect preserved history before any new mutation.

Commands (integration tree):
```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-forecast/api
.venv/bin/pytest tests/test_s21_plan_terms.py tests/test_s21_forecast_plans.py -q --junitxml=../docs/s21/evidence/baseline/t19-plan-terms.xml
cd ../web
npx vitest run src/__tests__/v2/ForecastOpportunities.test.tsx
npx tsc --noEmit
cd ../tests/e2e
npx playwright test --config=playwright.s21-local.config.ts local/s21-preview-edits.spec.ts
```

Persisted pre-edit matrix passed separately25684, integrated0b8ecca, artifact
`docs/s21/evidence/baseline/t19-preview-matrix.json`. It proves T19.03, not remaining
date/value/probability/all-view UI assertions or staging. Original seed is not
idempotent; do not rerun scripts/s21_preview_fixture.py against this populated DB.
