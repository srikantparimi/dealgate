# Forecast UI Increment

Owner: `s21/forecast-ui`, isolated `dealgate-s21-forecast-ui` worktree from
`65fa260`. Scope: new Forecast API module/page/chart/tests only. Lead owns
route/navigation registration, backend changes, runtime, integration and deploy.

Partial FC-01 through FC-05: Company & accounts is the default; Revenue
projection is the second implemented view. Scenario, account, quarter count,
as-of, month and source page persist in URL parameters. Quarter options are
1/2/4; the API supplies organization-local periods and all 15 months for four
future quarters. Account/month drilldown preserves parameters. No localStorage
or browser financial calculation: totals, ratios and monthly schedules are
server strings. Number conversion is restricted to chart pixel geometry and
existing percentage presentation, not business results.

Company/current/future totals, per-account quarter totals and signed coverage
use the scoped response. Signed and potential series remain separate. The
source basis, actuals availability, source coverage, pending calculations,
excluded/unresolved reasons, versioned plan job errors and watermark stay
visible. Cost/GM omission reads Restricted, null reads unresolved/unassessed.
Old responses cannot overwrite a later selection. Failures are errors, not
empty data. Source identities, authoritative names, calculation versions,
assumptions and evidence are inspectable when supplied by the backend.

CSV includes the actual authorized rows in the selected horizon/month, never
browser-recalculated totals; exact Decimal text is preserved and formula-like
cells are escaped. Cost columns are omitted when all rows are cost-redacted.
Source-plan pagination follows API metadata and does not calculate aggregates.

Tests were written first; the initial run failed because the page did not yet
exist. Unit responses are explicit mocks, not acceptance evidence. Own npm ci
installed 304 packages; no browser, database, cloud or shared runtime used.

Verification: nine focused component/API-export tests cover default periods,
15-month account/month drilldown, stale network responses, source version
binding/evidence, error vs empty states, role-redacted cost, pending sources,
pagination and safe exact-decimal CSV. Final focused run: 9 passed, no skips or
retries (16.88 seconds). `tsc --noEmit` passed after adding the optional enriched
excluded-source name to the response type; `git diff --check` passed. Real
screenshot and financial acceptance remain lead work.

Remaining: Overview, Resource demand, Next opportunities, saved views, more
server-backed filters, editing assumptions, automation controls, renewal/ending
work and concentration metrics, complete economic-scope journeys, real browser
visual validation and staging acceptance. FC-01 and the full release remain
incomplete; this is an integrated display increment only.

## Chart Geometry Correction

Independent lead screenshot `forecast-accounts-desktop.png` showed monthly
labels and nonzero potential totals but no bars. Percentage bar heights depended
on an implicitly sized flex/grid parent and collapsed in the real browser.
The regression test first failed with expected 184px versus actual 100% for a
35000 potential bar. Chart plot rows and bar heights now have definite pixel
geometry; zero stays zero and half-value bars have half-height. This is display
scaling only, not revenue calculation. Unit tests cannot prove pixel rendering;
lead owns the real browser screenshot/pixel confirmation after integration.
Final focused run: 10 passed, no skips/retries, 14.03 seconds; TypeScript and
diff checks passed. The Reports regression commit remains preserved beneath
this focused chart correction.
