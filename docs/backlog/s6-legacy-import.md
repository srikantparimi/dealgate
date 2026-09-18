# S6 (user-added scope) — Legacy SOW bulk upload + Excel resource import + current GM

## User story
As Finance/CEO, I bulk-upload every executed SOW currently in flight and
paste in an Excel of the per-project resource data (roles, hours, cost,
revenue split). The system computes the current GM per US/India component
per project, flags below-floor projects, and shows aggregate GM by client
and by geography on the Finance dashboard. Every imported record is
tagged "legacy — approval not evidenced" so nobody mistakes the historical
projects for freshly approved ones.

## Acceptance tests (Given/When/Then)
- Given I POST `/legacy/sow-upload` with multiple PDFs (zip or multi-file
  form), each file is stored in `officeapp-dev-sows-legacy-{account_id}`
  and a `sow_version` is created with `legacy=true, approval_evidenced=false`.
- Given I POST `/legacy/excel-import` with a spreadsheet matching the
  template spec (Task #18), each row becomes a `resource_line` on the
  correct `gm_model` (matched by `sow_ref`), and the GM library computes
  per component GM.
- Given a row has unknown location or missing cost, then the row is
  rejected with a specific error and no partial insert (all-or-nothing
  per file).
- Given a SOW is uploaded without matching resource lines (or vice versa),
  then the reconciliation screen (Task #19) shows the mismatch and files
  a task against the account owner.
- Given a project computes below the floor, then it appears on the
  Finance dashboard's "Legacy below-floor" list.
- Given I try to fake a historical approval (e.g. POST /approvals for a
  legacy record), then 403 with a message pointing at the rollout rule.
- Given I am Sales, then 403 on all legacy endpoints (Finance / CEO / SystemAdmin only).

## Data touched
- Extends `sow_version` with `legacy` boolean and `approval_evidenced` boolean.
- New table `legacy_import_batch` (id, uploaded_by, uploaded_at, sow_count, resource_line_count, errors JSONB).

## Roles allowed
- Finance, CEO, SystemAdmin: upload + import + view.
- Others: 403.

## Out of scope
- Retroactively creating approvals (explicitly forbidden per §13 rollout).

## Notes
- Blueprint §13 rollout: "Import as 'legacy approval not evidenced' and let
  executives disposition them; do not backfill fake approvals."
- Depends on: `resource_line` table (Sprint 3 story), Excel template spec (Task #18), reconciliation UI (Task #19).
