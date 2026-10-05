# Commercial Profile Editors

Owner: isolated `s21/commercial-ui` worktree from `9a27f14`. Only commercial
API types, editor/components and their unit tests. Lead owns migrations,
integration, runtime, real application journeys and deployments.

## Increment 1

Milestone, unit/story-point and time-and-materials fields use the canonical
backend pricing objects and existing preview/version endpoints. Decimal money
and quantities remain strings; no financial totals are calculated in the browser.
Milestone accounting references, quantity source identities, approved usage,
estimates, source evidence and existing cost/staffing inputs are preserved.
Pricing model replacement requires an explicit confirmation describing what is
replaced and what is retained. Signed and unauthorized models stay disabled.

New manual fields are justified only when confirmed SOW terms/actual usage do
not provide the quantity, contractual allocation, cap/minimum or milestone
acceptance. Existing canonical values prefill exactly; unknown monetary inputs
stay blank, not zero. Every save retains the written change-reason requirement.

Four initial tests failed before the new fields existed. A syntax error during
implementation was corrected without changing assertions. Unit API mocks are
not staging acceptance. Calendar staffing and hybrid fields are next; full
profile upload/approve/sign/handoff and independent financial/browser proof
remain open regardless of these unit counts.

Increment 1 verification: 13 focused tests passed, zero skips/retries;
TypeScript and diff checks passed. No real-browser/staging proof claimed.

## Increment 2

Calendar staffing now exposes assignment dates, headcount/allocation, versioned
bill and loaded-cost rates, contract rate basis, all seven weekday schedules,
and dated holiday/service overrides. New hours, headcount, costs and rates stay
unconfirmed rather than receiving assumed work hours. Existing calendar and
rate-version references remain intact.

Hybrid editing retains child identities, source evidence, costs and staffing.
Each child has structured pricing fields, with explicit confirmation before
changing its pricing model. Shared-cost selectors use source/component IDs with
readable labels; FX rows retain exact rate strings and version/date evidence.
Nested hybrid inputs remain preserved and visibly unresolved rather than being
silently flattened. Parent and child source/policy bindings are refreshed
immutably for preview/save; financial amounts are never calculated locally.

All seven registered profiles now have structured editing surfaces. T&M unit
selection preserves unfamiliar existing units. Accounting references remain
read-only. New TSX was formatted with Prettier 3.3.3 for maintainability.

The two calendar/hybrid behavior tests failed before implementation. Final
verification: 21 focused tests passed (12 profile tests and 9 existing editor
tests), zero skips/retries, and `npx tsc --noEmit` passed. Coverage includes signed
read-only behavior for every newly supported profile, Finance write prevention,
source-binding immutability, exact Decimal inputs and retained evidence.

These are component/unit results only. Real API/browser journeys across all
seven profiles, independent financial comparisons, approval/signature/amendment
flows and staging acceptance remain the integration lead's required proof.

## Independent QA Corrections

Bounded correction pass from `299d0ae` (independent QA tests cherry-picked by
the lead). Budget: 20 minutes, sole active worker; no shared runtime or cloud
operations. The independent report and its 19 tests were read-only throughout.
The initial combined run reproduced exactly 7 failures / 33 passes (40 tests).

All five findings are now fixed and tested locally:

1. Pending hybrid pricing changes bind to the immutable component ID rather
   than array index. Removing the target clears its pending confirmation;
   deleting an earlier sibling cannot redirect the change.
2. Calculation provenance distinguishes saved, unsaved preview and stale
   unsaved preview. Editing after preview keeps the values explicitly unsaved;
   only successful version persistence labels returned values saved.
3. Fixed assignment and recurring MSP expose the first calendar-cost assignment
   for both root models and hybrid children. Headcount/rates remain unconfirmed.
4. A shared structured MSP editor exposes credits, explicit overages, actual
   usage, included units and overage rate. Exact Decimal strings and source IDs
   remain intact; the backend alone computes the financial outcome.
5. Unsupported persisted root models produce explicit validation and retain
   visible source evidence. Preview/save remain unavailable and inputs unmodified.

Exact combined command from the independent report passed **40/40 tests** in
42.70 seconds, with no skips/retries or test assertion changes. `npm run
typecheck` passed. New/changed production TSX formatted with Prettier 3.3.3.
The QA report itself intentionally retains its original failure evidence.
Independent rerun, real browser/all-profile lifecycle and staging verification
remain with the lead; these unit fixes do not close S21 acceptance requirements.
