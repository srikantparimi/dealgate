# S20 · click-through for Kanna (W5 owned)

Per directive §8 last bullet:

> Click-through for Kanna, ≤ 12 steps, through the full journey.
> Steps that cannot run tonight are listed as blocked with the reason.

**Written FROM the app's actual state at the end of the night**, not
from what the directive said should exist. This file gets its final
edit during the last 90 minutes of the run when W1–W7 have committed
their landings.

Environment for the click-through:
- Base URL: `https://app.dealgateapp.com` (staging behind CloudFront).
- Auth: `e2e-staging@smartek21.com` (SystemAdmin + every governance
  group; see `isolation.md` §Test-user tags).
- Deal marker: `S20 e2e {YYYYMMDD-HHMMSS}` — created by hand in HubSpot
  before step 1, or use the existing example deal named in T03.
- Build tag: TBD (captured at deploy time; recorded in
  `docs/reports/s20/deploy.md`).

## The 12 steps

### 1. Filtered Pipeline · **not_run**

- `/pipeline?open_closed=open&owner=<me>` opens with the filter bar
  visible, correct total (`open_count`) reconciles with the stage chip
  sum + unknown bucket.
- 25/50/100 pagination visible; global total on the page.
- Reload preserves URL state; Back after clearing filters restores them.
- Expected owner: W2.
- Currently: SKELETON (W2 not yet landed).

### 2. Client detail · **not_run**

- Click a client name in the list; land on `/clients/{id}` with:
  - client name + account owner + NDA/MSA rows (two facts per D3);
  - matching opportunities section reconciles to a subset of Pipeline;
  - deal owner ≠ account owner where that is the case.
- Owner: W2.

### 3. Deal detail · Closed Lost 74 Sky **not_run**

- Search for `74 Sky`; open the deal detail.
- Stage renders as `Closed Lost` (readable), NOT numeric.
- Open 0 shown plainly; is_closed_lost=true visible.
- Activity is human-readable; no raw JSON.
- Owner: W2 (L07 regression).

### 4. Upload SOW pre-bound · **not_run**

- From the deal detail, click Upload SOW.
- `/sows/new?dealId=…` opens with client + deal name filled in and
  read-only.
- Upload a synthetic SOW file; exactly one package created; deep link
  survives refresh.
- Owner: W3.

### 5. Workspace one-readiness + tabs in place · **not_run**

- `/sows/{id}` shows one Readiness panel (regression on L10 that had two).
- Tabs (Overview, Scope, Staffing & GM, Approvals, Signature, Handoff)
  render INSIDE the workspace shell; refresh + Back work; deep links
  land on the correct tab.
- Owner: W3.

### 6. Scope confirm · **not_run**

- Confirm extracted fields; missing scope → `Not assessed` displayed
  explicitly; save draft + resume works.
- Owner: W3.

### 7. Staffing / GM · **not_run**

- Fill in staffing plan; GM computes; assert US-35%/India-50% behavior
  (T17). Below-floor triggers CEO exception flag (T20 preview).
- Owner: W3.

### 8. Submit for approvals · **not_run**

- Submit; assigned reviewers shown before submission (L14 fix).
- One reviewer returns for changes; submitter reworks; version bumps.
- Owner: W3.

### 9. All four functional approvals by role users · **not_run**

- Delivery / HR / Finance / Legal each approve via the appropriate
  Cognito role.
- Owner: W3.
- **Blocked tonight unless** the multi-role Cognito partitioning is
  applied via Terraform. Fallback: use `e2e-staging` (member of every
  governance group) to drive each approval and note the coverage gap.

### 10. Conditional CEO exception · **not_run**

- If GM is below floor: CEO reviews conditions, approves with expiry.
- If GM is compliant: /sows/{id}/exception reads `Not required`.
- Owner: W3.

### 11. Executed doc upload + verification, delivery accept, project created · **not_run**

- Upload executed SOW; verify terms match approved package (T22).
- Delivery accepts (T23); project provisioned exactly once with
  provenance to (deal_id, package_id).
- Owner: W7.

### 12. Command center + report + renewal reconcile · **not_run**

- Command center metric for open + approved packages includes the
  released package.
- Reports approval-turnaround aggregate includes its cycle time
  (T42, contingent on W4 implementing the endpoint).
- Renewal shown as term_end minus two calendar months (D8, T25), NOT
  60 days.
- Owner: W4.

## Blocked / deferred steps

| step | reason | owner | next action |
| --- | --- | --- | --- |
| 4 (upload prefilled) | W3 not yet landed on `integrate/s20` | W3 | commit + integrate; then unblock |
| 5 (tabs in workspace) | same | W3 | same |
| 6-8 (scope, staffing, approvals) | same | W3 | same |
| 9 (multi-role approvals) | Cognito pool has 4 users tonight; role partitioning not applied | Lead | terraform apply on `officeapp-dev-e2e-approvers` module; document in decisions.md |
| 10 (CEO conditional) | depends on step 7-9 landing | W3 | same |
| 11 (executed doc, delivery accept, project) | W7 not yet landed | W7 | commit + integrate |
| 12 (report reconcile) | approval-turnaround endpoint may not be implemented tonight (L18) | W4 | if not tonight → `missing` in matrix.md with next-action |

## Build under test

- Recorded here after the final integration + staging deploy:
  - Commit: TBD
  - API image: TBD
  - Worker image: TBD (same immutable image per D5)
  - Web build: TBD
  - Alembic head: TBD

## Log

- 2026-09-30 · W5 cycle 0 · skeleton committed. Every step `not_run`;
  step-by-step evidence added as workers land.
