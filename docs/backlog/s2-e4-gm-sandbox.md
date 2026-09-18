# S2 E4 — GM calculator sandbox (M1 sign-off screen)

## User story
As Finance, I open the GM sandbox, pick an engagement type, fill in the
inputs directly (no SOW needed), and see the calculated GM per US/India
component + blended, floor pass/fail, and required min price. I export the
result as an Excel row to reconcile against my current sheet. This is the
M1 milestone gate — Finance signs off on the math before the UI ships
to Sales.

## Acceptance tests (Given/When/Then)
- Given I am Finance, when I POST `/gm/sandbox` with engagement_type and
  inputs (resource lines + revenue split), then response is the full
  `TemplateResult` (revenue_us/cost_us/revenue_india/cost_india, gm_us,
  gm_india, gm_blended, complete, missing[]) plus policy check.
- Given the section §7 discounted case (US $90k/$65k, India $55k/$30k),
  when I submit, then response shows US GM 27.78%, India GM 45.45%, both
  fail floor, requires_ceo=true. (This is the automated M1 evidence.)
- Given a resource line has missing hourly_cost, when I submit, then
  `complete=false` and `missing` names the field; result GM shows N/A
  (never a spurious zero).
- Given I am Sales, then 403 (Sales cannot see cost bands or GM math tools).
- Given I click "Export to Excel", the download is an xlsx that Finance can
  paste into their sheet with the same numbers rendered identically.

## Data touched
- No persistence (sandbox is stateless).
- Requires: rate_card_version + policy_version resolved from Agent L's tables
  so the sandbox uses the "current" published values by default.

## Roles allowed
- Finance, Delivery, Presales, SystemAdmin: read + run.
- Sales, Marketing: 403.

## Out of scope
- Saving sandbox scenarios (that's the Delivery Model Builder in Sprint 3).

## Notes
- This is the M1 evidence gate. Finance MUST click through this page and
  agree the numbers match their Excel before Sales sees any GM UI.
- Uses `api/app/gm/compute` — the pure library. Never bypass it.
