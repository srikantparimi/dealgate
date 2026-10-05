# Resource Demand Source Component

Isolated branch `s21/demand-ui` from `0090261`. Ownership is the new API helper,
`ResourceDemand.tsx`, its new unit tests and this report. No route/navigation,
parent page, backend, shared runtime or deployment changes.

## Integration

Named export `ResourceDemand`, props `accountId?: string` and
`onRefresh?: () => void`. The integration lead owns placement in Forecast and
People planning. Reads actual `GET /people/demand`; publication uses actual
`POST /people/demand/publications`. No mocked feature-response browser proof.

The component checks `getMe` before fetching demand. Read roles match the
backend. Only Delivery/SystemAdmin see publication and capability-editing
controls; server authorization remains authoritative. Current account filter
applies to the authorized rows. Source/account labels never fall back to UUIDs.
Authorized `source_url` and `account_name` are optional additive DTO fields,
provided by the lead; absent names say Account unavailable, absent links remain
plain source titles.

Sources show pending/current/stale state, source revision, lifecycle, selection,
missing fields, full integer headcount, exact allocation strings, inclusive
dates, capability and evidence. Unknowns remain unknown. No browser financial
math, probability weighting, invented matches, sourcing or hire controls.

Pending publication sends empty enrichments, both expected-version values,
written reason and UUID request key. Existing lines prefill skills, level and
evidence. Source counts/dates and hidden continuity cannot be edited here.
Only actually edited capability fields are submitted; unrelated concurrent
changes are not overwritten after an explicit source reload. Each submitted
enrichment carries evidence. Unchanged retries preserve request keys. Stale
responses are ignored; errors are not rendered as empty success states.

Conflict errors, typed draft and reason remain visible across reload. Reload
refreshes CAS versions explicitly. On successful publication the source list
reloads and `onRefresh` notifies the parent. Missing-input publication is allowed
and the success notice retains those missing reasons.

Required backend dependency, confirmed being implemented by lead: publication
must preserve omitted existing enrichment/continuity for still-present source
line identities. Delivery cannot see named continuity and must not clear it by
omitting a redacted field. The UI never guesses those hidden IDs.

## Local Verification

Ten meaningful unit tests were authored before production implementation.
Authoring continued while runtime was held; the first permitted test execution
was after implementation, not a claimed red run. First focused run: 10 passed
in 15.39s. Initial typecheck caught three unsupported button variants; these
were changed to the existing `secondary` variant. The conflict test was then
strengthened to verify preservation of a concurrently updated untouched level.

Final focused run: **10 passed in 4.68s**, no skips/retries. Final
`tsc --noEmit` passed. Runtime slot released; no processes remain. Commands:

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-demand-ui/web
npm exec -- vitest run src/__tests__/v2/ResourceDemand.test.tsx --maxWorkers=1 --minWorkers=1
npm exec -- tsc --noEmit
```

Coverage: literal source facts and link, pending empty-enrichment publication,
CAS fields, prefilled editor, field-limited submission, conflict/reload draft
preservation, read-only HR/account scope, role-before-fetch, unknown values,
stale-response race, source failure and idempotent retry. API mocks are unit
isolation only, not acceptance evidence. Own dependency copy; no install or
shared node_modules writes. Existing cached formatter ran on owned files only.

Lead-owned remaining work: parent wiring, real API/browser workflow, responsive
screenshots, sourcing/global allocation integration and staging proof. This is
not completion of the fifth Forecast view or FC-07.

## Label and Probability Follow-Up

Separated all editor labels from controls while retaining explicit `htmlFor`
and `useId` bindings. Populated skills, level, evidence and reason now have
exact string-name textbox assertions. These assertions passed under jsdom even
before the markup change; the real-browser label-risk was supplied by the lead
from prior connected proofs, not falsely reproduced by this unit environment.

Added descriptive win probability using existing `formatPercent`, without
changing integer people or Decimal allocation. The new literal 70.0% assertion
failed before the display change (1 failed / 9 passed). After the changes,
10 passed in 7.74s; `tsc --noEmit` and `git diff --check` passed. Runtime released,
no processes remain. Parent browser proof remains required.
