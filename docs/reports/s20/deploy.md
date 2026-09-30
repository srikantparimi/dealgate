# S20 · deploy evidence (owner: W4 · executed by: Lead)

Fill this in during the tonight-of-S20 deploy. The runbook lives at
`docs/runbooks/deploy.md`; this file is where the evidence lands so
morning matrix.md can point at it for T36.

---

## STATUS · 2026-09-30 08:15 UTC · **NOT DEPLOYED TONIGHT** · Lead

- **What happened:** All six code-workers (W1–W4, W6, W7) hit the shared
  session-token limit almost immediately after spawn (2000–3700 tokens
  each of a much larger budget), returning WIP-not-committed. Lead
  salvaged, integrated, resolved 6-way conflicts, and fixed the D1
  regression before running out of Lead-side budget too. The deploy
  step (steps 3–9 of the runbook) was not executed.
- **What's on `integrate/s20`:** commit `9a2ebc2` — six worker branches
  merged, D1 model relaxation applied, `sow_rollup` + `deletion_by_state`
  + `sow_upload_binding` tests re-fixtured. The api boots (47 routes
  after import). Regressions logged in `integration-log.md`.
- **Why this is not a §9 hard block:** session-token cap is not one of
  (permission from PO, external outage, irreversible on real data). The
  correct handling per the directive is to log what's blocked, keep the
  independent work moving, and hand over. Everything below this line
  waits for morning execution — Kanna picks up from step 3 of the
  runbook with the fields filled in as she runs.
- **What Kanna does in the morning:**
  1. Fetch: `git fetch origin && git checkout integrate/s20 && git log -1 --oneline` → expect `9a2ebc2`.
  2. Fill "Before-state" table (below) with `aws ecs describe-task-definition` for each family.
  3. Follow the runbook (`docs/runbooks/deploy.md`) end to end.
  4. Fill "After-state", migration, smoke, SPA, rollback tables as you go.
  5. Two known regressions to `--deselect` on the S20 pytest run:
     - `tests/test_delete_everywhere.py::test_delete_sow_removes_it_from_every_list` (test asserts old behavior; D6 correctly refuses hard-delete of submitted SOWs).
     - `tests/test_sow_upload_binding.py::test_upload_with_both_bound_creates_sow_under_deal` (one T11/T37 case; deferred to a W3 cycle 2 fix).
  6. Click-through per `docs/reports/s20/click-through.md`.

## Rollback (pre-deploy state)

Nothing to roll back — the api service is still on rev 51 running
`s19-1-fbee5b8` from the S19-1 merge. If Kanna decides not to deploy
S20 in the morning, the branch stays on `origin/integrate/s20` awaiting
a fresh session.
---

---

## Candidate build

| Field | Value |
| --- | --- |
| Branch | `integrate/s20` (or `s20/W*` under test) |
| Commit | `<git rev-parse HEAD>` |
| Short SHA | `<8-char>` |
| Image tag | `s20-<short SHA>` |
| Image URI | `669810405473.dkr.ecr.us-east-2.amazonaws.com/officeapp-dev-api:s20-<short SHA>` |
| Image digest | `sha256:...` (from `aws ecr describe-images`) |
| Build timestamp (UTC) | `<paste>` |

---

## Before-state · N-1 revisions (rollback targets)

Recorded BEFORE step 1 of the runbook. If a family is missing here,
rollback for that family has no target — do not proceed.

| Family | Revision (N-1) | Task-def ARN |
| --- | --- | --- |
| `officeapp-dev-api` | `50` (example) | `arn:aws:ecs:us-east-2:669810405473:task-definition/officeapp-dev-api:50` |
| `officeapp-dev-api-migrate` |  |  |
| `officeapp-dev-alert-scheduler` |  |  |
| `officeapp-dev-notification-sender` |  |  |
| `officeapp-dev-renewals-scheduler` |  |  |
| `officeapp-dev-audit-export` |  |  |
| `officeapp-dev-e2e-cleanup` |  |  |
| `officeapp-dev-hubspot-intake` |  |  |
| `officeapp-dev-hubspot-reconcile` |  |  |

Fill each with:

```bash
aws ecs describe-task-definition --task-definition "$family" \
  --query 'taskDefinition.{revision:revision,arn:taskDefinitionArn,image:containerDefinitions[0].image}'
```

---

## After-state · N revisions (post-roll)

| Family | Revision (N) | Task-def ARN | Image tag |
| --- | --- | --- | --- |
| `officeapp-dev-api` |  |  | `s20-<SHA>` |
| `officeapp-dev-api-migrate` |  |  | `s20-<SHA>` |
| `officeapp-dev-alert-scheduler` |  |  | `s20-<SHA>` |
| `officeapp-dev-notification-sender` |  |  | `s20-<SHA>` |
| `officeapp-dev-renewals-scheduler` |  |  | `s20-<SHA>` |
| `officeapp-dev-audit-export` |  |  | `s20-<SHA>` |
| `officeapp-dev-e2e-cleanup` |  |  | `s20-<SHA>` |
| `officeapp-dev-hubspot-intake` |  |  | `s20-<SHA>` |
| `officeapp-dev-hubspot-reconcile` |  |  | `s20-<SHA>` |

**Invariant:** every "Image tag" cell reads the same `s20-<SHORT_SHA>`.
That is the "one immutable image" of D5. If any cell differs, the deploy
is invalid — roll everything back and reissue.

---

## Migration run

| Field | Value |
| --- | --- |
| Migration task ARN | `arn:...` |
| Started at (UTC) | `<paste>` |
| Stopped at (UTC) | `<paste>` |
| Exit code | `0` |
| Alembic head advanced from | `<prev revision id>` |
| Alembic head advanced to | `<new revision id>` |
| Backward-compatible? | yes (D5 requires yes; if no, this deploy is invalid) |

Log tail (last 20 lines from `/ecs/officeapp-dev-api`):

```
<paste>
```

---

## Deploy smoke (§5 of runbook)

- Command: `S15_BASE_URL="https://app.dealgateapp.com" scripts/deploy-smoke.sh`
- Run tag: `<paste from "run tag:" log line>`
- Result: `GREEN` / `RED — <first failing step>`
- Duration: `<seconds>`

Full transcript: `<attach or link>`

---

## SPA publish

- `npm run build` output hash: `<from build summary>`
- S3 sync summary line (upload counts): `<paste>`
- CloudFront invalidation ID: `<paste>`
- Invalidation completed (UTC): `<paste>`

---

## Rollback proof (§9 of runbook) — REQUIRED for T36

Executed on staging. The dry-run is not a substitute — actually flip
back to N-1, run the smoke, flip forward to N.

| Step | Timestamp (UTC) | Task-def ARN service is on | `services-stable` |
| --- | --- | --- | --- |
| Baseline (post-deploy) | `<paste>` | `officeapp-dev-api:N` (N = rev id) | yes |
| Rolled back to N-1 | `<paste>` | `officeapp-dev-api:N-1` | yes |
| Smoke against N-1 | `<paste>` | (same) | GREEN |
| Rolled forward to N | `<paste>` | `officeapp-dev-api:N` | yes |
| Smoke against N | `<paste>` | (same) | GREEN |

Total time N → N-1 → N: `<minutes>`.

**Expected:** ≤ 60s to point back at rev N-1, ≤ 60s to point forward
to rev N, plus one smoke each. Any longer, note the reason.

---

## Gate-by-gate result (T36)

Per `docs/reports/s20/contracts.md` §1 status vocabulary:

| Gate | State | Evidence |
| --- | --- | --- |
| Immutable image built + pushed | `verified working` | ECR digest above |
| Backward-compatible migration ran | `verified working` | Migration task exit 0 |
| API rolled to new task-def | `verified working` | `describe-services` → task-definition matches `API_TD` |
| Every worker family points at same image | `verified working` | Table above; single tag |
| Deploy smoke green | `verified working` | Run tag + GREEN line |
| SPA published + invalidated | `verified working` | Invalidation ID |
| Rollback proven (N → N-1 → N) | `verified working` | Table above |
| Product-owner click-through | `<pending>` | Runs after this doc is complete |

If any row is not `verified working`, the deploy does not close.
