# HR Sourcing Planning UI

Isolated branch `s21/sourcing-ui` from `3504a65`. Own new API helper,
`SourcingPlanning.tsx`, its unit tests and this report only. Named export
`SourcingPlanningPage`; integration lead owns route `/people/sourcing`,
navigation, real browser proof and deployment.

## Contract and Behavior

Implemented against the committed 10:56 HTTP contract and read-only verification
of backend commit `f709de5`. Actual helpers call `/people/sourcing/rules`,
`/people/demand` and `/people/sourcing/drafts`. No local storage or mocked feature
responses in application code.

HR/SystemAdmin authorization is checked before requesting sourcing data. Rules
begin empty/unconfigured; no 45/30-day suggestions are silently populated.
Existing rule rows are prefilled, with add/remove icons, skill/location and
integer lead days, written reason, current expected version and request key.
Manual lead time justification is the committed contract's HR recruiting
judgment. Configured empty rules remain explicit, not inferred dates.

Source selector uses account/source names, publication state and publication
IDs only as opaque request keys. Pending sources cannot prepare a draft;
stale demand requires publication first. Draft preparation sends current demand,
rule and draft versions. Rules and reasons survive 409 responses. Explicit
reload refreshes CAS values without discarding typed rule/reason drafts.
Unchanged retries preserve request keys. Stale source/history responses cannot
replace a newer selection. Errors do not become empty successful histories.

Latest draft state and immutable history are separate. History pagination uses
the server's page/size support; selecting an old revision does not change the
latest version used for CAS. The snapshot shows full headcount, retained,
incremental, matched, total gap, continuity gap, incremental gap, exact gap FTE,
inclusive start/exclusive end and sourcing-by date or Not scheduled. Descriptive
win probability uses the shared formatter and does not scale headcount. Missing
reasons and incomplete status remain visible. No named supply, salaries, fees,
costs, hire controls, reservations or communication controls.

All textarea labels are separate from populated controls with explicit
`htmlFor`/`useId` associations. Layout is unframed, with horizontally scrollable
dense tables and responsive rule controls.

## Verification Scope

Ten interaction tests cover permission-before-fetch, empty configuration,
rule add/remove/save, rule conflict/reload, draft preparation with all CAS
versions, literal counts/dates, stale-publication refusal, stale selection
response, draft conflict/reload, failed history, and paged historical selection
versus current CAS. Tests were authored first while runtime was held; first
allowed execution followed implementation, not a claimed red run.

Final focused run: **10 passed in 7.68s**; final `tsc --noEmit` and
`git diff --check` passed. No skips or retries. Runtime slot released and no
processes remain. Commands:

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-sourcing-ui/web
npm exec -- vitest run src/__tests__/v2/SourcingPlanning.test.tsx --maxWorkers=1 --minWorkers=1
npm exec -- tsc --noEmit
```

Only an APFS clone of own prior node_modules was used; no install or shared
generated writes. Formatting uses the existing cached formatter on owned files.
Unit mocks isolate API transport and are not real application acceptance proof.

Real backend/browser workflows, responsive screenshots, full People/Forecast
integration and staging remain lead-owned. This bounded screen does not
establish full S21/Forecast completion.
