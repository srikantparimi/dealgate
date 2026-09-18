# S6 (user-added scope) — Reconciliation: SOW upload ↔ imported resource lines

## User story
As Finance, after uploading a batch of legacy SOWs and an Excel of resource
lines, I open the reconciliation screen and see: `X SOWs uploaded, Y have
matching resource lines, Z do not, W resource lines have no matching SOW`.
Every mismatch is a task assigned to the account owner. I can approve the
reconciliation (freezes the batch) or send back for fixes.

## Acceptance tests
- Given I upload 5 SOWs and an Excel with 4 sow_refs matching, then the
  screen shows 1 unmatched SOW and lists which one.
- Given I upload 5 SOWs and an Excel with 6 sow_refs (one extra), then the
  screen shows the orphaned resource lines.
- Given I click "Approve reconciliation", the batch is frozen and appears
  on the Finance dashboard as "Legacy: N projects imported".
- Given a project has GM `complete=false`, it appears in a "Needs data"
  section — Finance can nudge the owner (files a task).

## Roles
- Finance / CEO / SystemAdmin.

## Notes
- Uses tasks + notifications from S2.
- Uses gm library from S1.
