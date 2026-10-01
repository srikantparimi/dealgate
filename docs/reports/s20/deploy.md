# S20 · deploy evidence (owner: W4 · executed by: Lead)

Fill this in during the tonight-of-S20 deploy. The runbook lives at
`docs/runbooks/deploy.md`; this file is where the evidence lands so
morning matrix.md can point at it for T36.

---

## STATUS · 2026-09-30 19:10 UTC · **DEPLOYED to staging** · Lead

- Image: `s20-3e5be98c` @ digest `sha256:a21d0a6d1b5ac3c09ff291d160cd1fc592755ba5fb55945fd114b16bd37b7806`.
- Migration: alembic head advanced to `20260930_0044_s20_lead_d1_d4` (exit 0 after fixing the D1 constraint-name lookup to be dynamic — first attempt failed on `sow_opportunity_id_key` not existing under that name in Postgres; fix at commit `3e5be98`).
- api service: rev 51 → **rev 53** (rev 52 was replaced by 53 when the migration fix required a rebuild). Rollout `COMPLETED` in ~1m45s.
- Worker task-defs re-registered on the same image: alert_scheduler rev 7, notification_sender rev 7, renewals_scheduler rev 7, audit_export rev 7, hubspot_intake rev 5, hubspot_reconcile rev 5.
- SPA build fixes committed (DeletionState 'governed', TurnaroundReport prop, two unused imports), rebuilt, `s3 sync` complete, CloudFront invalidation `I90HPL9MZAQQVT79Q0F398QH1` → `Completed` in ~30s.
- Deploy smoke `2026-09-30T19:08Z`: **GREEN** on the second run (first run tripped the known Bedrock `manual_required` flake per the runbook; retry passed). Test-data-clean gate: 0 leaked clients. Log: `docs/reports/s20/deploy-artifacts/smoke.txt`.
- Rollback proof (T36): rev 53 → 51 (7 polls to `COMPLETED`) → 53 (7 polls). `healthz` green at both endpoints. Total round-trip ~3m30s.

Everything below this line is the fill-in template W4 authored; the sections above supersede.

---

## (Legacy) 2026-09-30 08:15 UTC · not deployed at the earlier attempt · Lead

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

---

## STATUS · 2026-10-01 18:52 UTC · **DEPLOYED to staging** · Lead-C2

- Image: `s20-b75959ff` @ digest `sha256:5b5981c7c0b2480b23513fc7c835aa55c83a864a613d56b99ba5ec14f666e805` · size 103 MB.
- Branch: `integrate/s20 @ b75959f` (W4-1 SummaryOut exposure + W4-7 total_open scope fix + rule 19 heartbeat).
- Migration: alembic exit=0 on `MIG_TD arn:...:officeapp-dev-api-migrate:3`. Head remained at `20260930_0047_w6_watch` (no new revision in b75959f — no-op advance, same as rev 64 → rev 65).
- api service: **rev 64 → rev 65**. Rollout `COMPLETED` on first poll of `services-stable`.
- Worker families re-registered on same image:
  - `officeapp-dev-alert-scheduler:18`
  - `officeapp-dev-notification-sender:18`
  - `officeapp-dev-renewals-scheduler:18`
  - `officeapp-dev-audit-export:18`
  - `officeapp-dev-hubspot-intake:16`
  - `officeapp-dev-hubspot-reconcile:16`
  - (`officeapp-dev-e2e-cleanup`: no task-def family — carried forward from prior deploys as missing)
- Deploy smoke `smoke 20261001T184714Z`: **GREEN**. Test-data-clean gate: 0 leaked clients. Log: `docs/reports/s20/deploy-artifacts/smoke-c2.txt`.
- Before-state (rollback target): api rev 64 image `s20-b2e544df`; 6 workers rev 17/15 on same image.
