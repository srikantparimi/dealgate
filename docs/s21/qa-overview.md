# Independent Forecast Overview QA

## Scope

Production baseline: `2d9fc163896702aa872634e8f9b68921fe2031cf` on `s21/qa-overview`. Owned additions are this
report and `web/src/__tests__/v2/ForecastOverviewIndependent.test.tsx` only.
The bounded review covers the actual v3 directive FC-01 through FC-06 and
FC-11/FC-12 requirements as they apply to the Overview UI/API boundary.
No production or worker tests changed. No server, browser, database, or cloud
was used. Dependencies were copied into this worktree's own `node_modules`.

## Evidence

Fourteen independent cases use literal Decimal strings and real UI/export code.
Only `getForecastOutlook` and `getForecastPlans` are mocked as network boundaries.
These mocks cannot establish server authorization, persistence, calculations,
connected workflows, staging behavior, or acceptance.

Combined result: **27 passed / 3 failed**, 30 cases in **17.00 seconds**, with
no skips, xfails, or retries. Independent file: 11 passed / 3 failed (14 cases).
The unchanged worker files contribute 16 passing cases. The runtime was held
until the lead's browser process finished, then run with one worker.
`npm run typecheck` passed with exit code 0 after the test process exited.

```sh
cd web
npm test -- --run src/__tests__/v2/ForecastOverviewIndependent.test.tsx \
  src/__tests__/v2/ForecastOverview.test.tsx src/__tests__/v2/Forecast.test.tsx \
  --maxWorkers=1 --minWorkers=1 --no-file-parallelism
npm run typecheck
```

## Reproduced Findings

All three nodes are in `web/src/__tests__/v2/ForecastOverviewIndependent.test.tsx`
under `Independent Forecast Overview boundaries`.

1. **Medium: export drops reporting basis already supplied by the API.** Node:
   `exports the supplied timezone and row FX basis for reproducible reporting`.
   FC-11 requires timezone and currency/FX basis. Actual CSV omits the supplied
   `America/Los_Angeles`, `EUR`, `approved-rate-17`, and `2026-09-29` values.
   `web/src/api/forecast.ts:156` neither declares nor writes these columns.
2. **Medium: source detail drops original currency and FX date.** Node:
   `shows the supplied original currency and FX date alongside the conversion version`.
   The same converted source shows `approved-rate-17` but neither `EUR` nor
   `2026-09-29`. The API type supplies all three fields; rendering at
   `web/src/pages/v2/Forecast.tsx:573` includes only the version. This limits the
   user's ability to inspect the conversion basis of a displayed source amount.
3. **Low: zero-denominator coverage uses the wrong semantic state.** Node:
   `labels signed coverage N/A when Expected revenue is zero`.
   Given Expected revenue `0` and signed coverage `null`,
   `web/src/pages/v2/forecast/Overview.tsx:77` renders `Unassessed`, not the
   explicit FC-05 `N/A` state. Zero denominator is not an unresolved assessment.

Controls cover exact aggregate strings independently of paginated plan counts;
out-of-range plan pages; role-limited scope labels; account/date/scenario/horizon
and month URL preservation; omission versus null cost; stale and failed source
states; post-refresh 403 cleanup; stale rejected-request isolation; exact source
version, link and evidence without the relevant plan page; and financial actuals
remaining separate from service schedules.

## Missing Contract Boundaries

- FC-01: **missing**. Only three Forecast views are present. Resource demand,
  Next opportunities, saved views, editable assumptions, and automation controls
  are not established by this slice or its tests.
- FC-02: **missing**. Renewal dependency, revenue ending without replacement,
  and scenario/horizon-specific concentration are not supplied to Overview.
- FC-03: **missing**. This boundary suite does not establish persisted editing,
  full staffing/components drilldown, or company/account arithmetic correctness.
- FC-04: **missing**. Overview explicitly reports expiry risk and
  assessment-to-project linkage unavailable (`Overview.tsx:150`). Owner, BU,
  pipeline/stage, model and forecast-status filters are absent from this API/UI.
- FC-05: **missing**. Boundary assertions are not financial-engine acceptance;
  zero-denominator display and supplied FX provenance remain under test here.
- FC-06: **missing**. The suite checks display separation only, not a connected
  Finance import, correction, or matched actual-to-forecast coverage workflow.
- FC-11: **missing**. Export basis assertions are local only; historical snapshot
  persistence and all-page authorized export reconciliation are not proved.
- FC-12: **missing**. URL/API boundary checks do not prove tenant permissions,
  source-update transactions, worker recovery, mixed-snapshot rejection, or
  server pagination population. Stale-request isolation is only a UI control.

No other directive item is claimed by this narrowly owned increment. The lead
retains the release-wide item-by-item checklist and connected proof. No gate
is marked verified working (staging) or fixed and tested by mocked evidence.

## Parent Cleanup Follow-Up

Read-only inspection of `8106641` found changes addressing the prior eight red
assertions: participant schema and current identities, full agreement/upload
ownership, mirrored-source refusal, foreign forecast scope, and malformed child
dependency isolation. No parent test was edited or rerun in this task; this is
diff review, not independent runtime re-verification or acceptance.
