# S3 E6 — Delivery Model Builder + GM sheet UI + Excel export

## User story
As Delivery lead, I open the Delivery Model Builder for a deal, prefilled
from adviser + SOW fields, and edit the resource grid, work breakdown,
governance roles, contingency, and delivery pattern. Saving the grid
recalculates GM live per US/India component + blended and shows floor
pass/fail. I export the GM sheet to Excel for reconciliation with
Finance's tools.

## Acceptance tests (Given/When/Then)
- Given a SOW is `SOWDraft.confirmed`, when I open the Builder, then the
  grid is prefilled with the SOW's proposed roles/locations/hours (or
  empty rows if no adviser output).
- Given I edit a resource line, then GM in the right panel recalculates
  within 200ms (debounced) and StatusChip flips green/red as floors are
  crossed.
- Given the capacity check finds a person already 100% allocated on
  another active SOW in the same dates, then the row shows an amber warning.
- Given a "to hire" line with start_date earlier than HR's `lead_time_days`,
  then the row shows a red warning; submit is still allowed but Delivery
  must acknowledge.
- Given I click Save, then a new `gm_model` version is created (immutable),
  linked to the current `sow_version`, and the deal status moves to
  `GMBuild.complete` when every resource line has location, effort,
  bill_rate, and validated_cost.
- Given I click Export to Excel, then the download matches the GM sandbox
  numbers exactly for the same inputs.

## Data touched
- New tables: `gm_model` (immutable versions), `resource_line`, `cost_line`.

## Roles allowed
- Delivery lead, Presales, HR (read), Finance (read), SystemAdmin.
- Sales/Marketing: 403 (they never see cost bands).

## Out of scope
- Approval routing (Sprint 4).
- Save-as-template (add later).

## Notes
- Blueprint §8.
- Uses `api/app/gm/compute` — the pure library.
