# T19 Monthly Cost Contract And Ownership

2026-10-03 02:30 UTC. Prerequisite to accepted six-account financial proof;
also implements the existing S21-15 salary/allocation obligation (directive204).
Independent QA confirmed this is a missing representation, not authorization
to invent production payroll policy. T19 remains pending, no condition promoted.

## Contract Before Code

Add backward-compatible `cost_rate_basis` to StaffingAssignment: `hourly`
(existing default) or `monthly`; explicit null stays unresolved rather than
defaulting a cleared field to hourly. Existing cost_rate remains per person at100%
allocation in assignment currency; existing cost_version remains mandatory.
Monthly amount is a confirmed monthly cost allocation, not an inferred hourly
rate or an assertion that a preview budget is HR-approved. Component cost_basis,
source evidence/version and version-author/change-reason identify the authority.

For a complete calendar month, monthly cost = rate * headcount * allocation,
each once. Calendar still determines scheduled/billable/paid hours and must be
confirmed/cover the entire interval. Revenue rate basis remains independent.
New optional `cost_proration` supports explicit `full_month` only initially;
None means no partial-month policy confirmed. Partial assignment/term intervals
with monthly cost and no explicit policy stay unresolved. Explicit full_month
charges that declared monthly amount even on a partial interval. Do not silently
reuse billing proration as a cost policy. Unsupported proration is rejected.
No new rounding rule: Decimal precision remains existing GM authority. Monthly
cost cannot be cast as an hourly ResourceInput; reject that legacy conversion.

Editor shows cost basis and partial-month cost policy, with existing rate/source
version fields. Changing basis clears the rate/version and cost-proration draft
so an hourly number cannot silently become a monthly amount. All fields persist
in immutable commercial versions and the saved calculation-detail view.
No schema migration expected: additive typed JSON fields, old snapshots must
remain readable and old hourly calculations unchanged. Verify compatibility.

## Fixture Boundary

Atlas preview uses six people *8000 monthly billed and *4800 monthly allocated
cost. Signed172800/6months and extension monthly4800/person are source facts.
Remove the duplicate28800 PeriodCost when that same cost is roster-derived.
Use an explicitly fixture-confirmed calendar, location/timezone/cost allocation;
never label these as extraction or HR approval. Start with full-month intervals
and whole-month date shifts. All12 pure sources must preflight before persistence.

## Ownership And Order

- Governance worker: new own branch/tree based on888b8a9; ONLY
  api/app/gm/calendar.py, new api/tests/test_s21_monthly_staffing_cost.py,
  and docs/s21/lanes/t19-monthly-cost-backend.md. Author tests before code.
  No database/API/provider/migrations/deployment. Lead integrates.
- Lead: web/src/api/commercial.ts, commercial-editor/CalendarFields.tsx,
  corresponding editor/detail tests, persisted real API/worker fixture and
  connected browser proof. Lead owns any cross-layer compatibility repair.
- Independent QA: read-only calculation/contract review, then isolated evidence
  review. One heavy test/runtime at a time; no shared writable DB across workers.

Order: backend red/green + hourly regression; editor red/green + typecheck;
small lead integrations; all12 literal preflight; isolated database/actual API/
workers; six-account totals; immutable date/value/probability revisions and
all affected views/reload. Do not replace scope with aggregate test counts.
