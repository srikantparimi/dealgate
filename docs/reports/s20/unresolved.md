# S20 · unresolved (morning hand-over)

Everything on this list is either (a) something Kanna needs to grant / decide, (b) a downstream action deferred by tonight's session-token cap, or (c) a known regression. Nothing here is silently marked "done".

## Hard blocks (permission / external / irreversible)

| # | Blocker | Owner | What I need from you |
| --- | --- | --- | --- |
| U01 | Multi-role Cognito approvers do not exist. T27 (permissions uniform) + T44 (12-step full journey with role hand-offs) cannot run. | Kanna | Approve the follow-up TF slice (`infra-tf/modules/e2e-approvers/`) creating 5 Cognito users + populating `officeapp-dev-e2e-approvers` secret. Decision recorded as D-COG-01. |
| U02 | HubSpot token is read-only. J6 creator path (from S19-1) still cannot POST deals to the portal. | Kanna | Grant `crm.objects.deals.write` on a separate token stored at `dealgate/staging/hubspot_token_write`, OR decide to keep J6 in observer mode indefinitely. Recorded as D-ISO-01. |
| U03 | Shared session-token cap capped tonight's work. Cycle-2 spawn not attempted. | Anthropic account | Wait for reset (1:40 AM PT) OR raise the cap. |

## Deferred to Kanna's morning execution

| # | Item | Where | Action |
| --- | --- | --- | --- |
| U04 | D5 deploy to staging not run tonight. | `docs/runbooks/deploy.md` + `docs/reports/s20/deploy.md` (empty tables ready to fill) | Kanna runs the runbook end-to-end; fills evidence tables in `deploy.md`. |
| U05 | Alembic revision to relax `sow.opportunity_id` uniqueness on Postgres. Model already relaxed at commit `9a2ebc2` (works for SQLite tests); Postgres deploy needs migration or the running staging DB rejects multi-SOW inserts. | `api/alembic/versions/` | Kanna writes a new revision: `ALTER TABLE sow DROP CONSTRAINT sow_opportunity_id_key;`. Roll into D5 migration step. |
| U06 | Alembic revision to add sync_status watermark columns per contracts §5. W1's `sync_status.py` feature-detects the columns so tests + partial-migrated staging both work; but production Postgres needs the new columns for the freshness watermarks to actually persist. | `api/alembic/versions/` | Fold into the same D5 migration or a companion revision. Backward-compatible (`ADD COLUMN ... DEFAULT NULL`). |

## Regressions to fix (not blockers, but visible in the suite)

| # | Test | Cause | Fix |
| --- | --- | --- | --- |
| U07 | `tests/test_delete_everywhere.py::test_delete_sow_removes_it_from_every_list` | Test asserts pre-D6 behavior (hard-delete a submitted SOW). D6 correctly refuses. | Update test to call `archive_sow` instead. |
| U08 | `tests/test_sow_upload_binding.py::test_upload_with_both_bound_creates_sow_under_deal` | Unknown; T11/T37 case fails while sibling cases pass. | W3 cycle 2. |
| U09 | W5 cross-worker requests W5-01, W5-03, W5-04 remain unrouted (owner workers didn't touch their target files before session limit). | `docs/reports/s20/requests.md` | W1 cycle 2 lands them, OR Kanna picks them up manually before deploy. |

## Blocked capabilities in the matrix (per §Vocabulary)

- T27 permissions uniform · **blocked (U01)**
- T44 12-step full journey · **blocked (U01, partial)** — steps 1–6 runnable; role hand-offs (delivery → hr → finance → legal → ceo → back to submitter) require U01.
- J6 creator-mode Playwright (S19-1 carry-forward) · **blocked (U02)**.
- D5 deploy · **deferred (U04)** — not blocked; not run tonight.

## Nothing here is a synonym for "we didn't get to it"

Every item on this list is either something you decide, something external is preventing, or a specific follow-up commit that's owed. The matrix marks capabilities as `verified working` / `fixed and tested` / `missing` / `blocked` / `deferred` — the honest state is on the matrix, not this file. This file is the "what needs Kanna" companion.
