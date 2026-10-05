# Forecast Overview Increment

Isolated branch `s21/forecast-overview` from `6cd1e5a`. Budget: 20 minutes.
Only Forecast page/view components, the new Overview tests and this report are
owned. Lead retains shared API types, integration and connected browser proof.

## Scope and Evidence

FC-01/FC-04: added the Overview tab and deep link without changing the default
Company & accounts view. Current-month, current-quarter and future-quarter
figures display the existing server Decimal aggregates, never a browser sum.
Signed/potential values, cost/GM restrictions, period bounds, scenario, reporting
currency and service-schedule basis remain explicit. Existing actuals retain
their separate financial measure table; they are not added to forecast totals.

Overview shows authorized plan assumptions/status and pending/unresolved source
reasons. Plan coverage is labeled with returned page/subset/total metadata.
Source rows open the existing calculation/evidence detail. Account clicks retain
scenario, horizon, as-of and selected view; month filtering and chart drilldowns
continue through the existing shared URL state. No new feature-response mocks,
browser-local records, money arithmetic or fabricated source links were added.

Five unit tests were written first: four failed before implementation and the
existing error-state test passed. Combined verification passed 16 tests (five
Overview plus eleven existing Forecast tests), no skips/retries. TypeScript
passed. Unit API mocks are boundary fixtures, not financial or staging proof.
The existing RevenueChart and its geometry assertions were not modified.

## Backend Gaps

This increment does NOT close FC-01 or FC-04. The current `ForecastOutlook` and
`ForecastPlan` response contracts do not provide authoritative contract expiry,
renewal decision, source-SOW/follow-on relationship or resource headcount/gap
fields. Overview explicitly labels expiry risk and assessment-to-project linkage
unavailable instead of guessing relationships from names or fabricating risk.
No resource KPIs are invented. A combined selected-horizon financial aggregate
is also absent, so the existing separate period aggregates are used and labeled.

Resource demand and Next opportunities are outside this bounded increment.
Saved views, editing assumptions, automation controls, all-view acceptance and
connected backend/browser lifecycle proof remain open with the integration lead.
