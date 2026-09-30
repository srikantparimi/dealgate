# Directive S20 (v2): overnight end-to-end repair and proof (multi-worker)

From: Kanna Parimi, product owner. Source of findings: `docs/reviews/2026-09-29-e2e-review.md` (live findings L01–L20, architecture items A1–A8, acceptance checks T01–T44). Read it in full before planning. S19 slice 1b is superseded. v2 closes the gaps in v1: explicit file ownership, owners for tracking features and for the approval-to-delivery path, staging-isolation verification, investigation freedom, conflict rules, test-status fields, consumer cutover, SOW rollup definition.

## 0. Ground rules (non-negotiable)

1. **No merge to main tonight.** Everything integrates into `integrate/s20` and deploys to staging. Merge only after my click-through.
2. **Isolation verified before any write (§5).** Migrations, stub cleanup, role seeding, notifications and tests touch only isolated staging resources. Records that exist in the HubSpot mirror are compared read-only; the mirror is never edited by hand, only by the sync code under test.
3. **Truth over green.** Each capability ends in exactly one state: `verified working` · `fixed and tested` · `missing` · `blocked` · `deferred`. An honest placeholder ("Not configured") is truthful *and still `missing`* — it needs an owner and a next action. Zero is never a stand-in for unknown.
4. **Reuse before rebuild; investigate freely.** Inspect the actual code, models, routes, migrations, repository instructions and tests as much as a task needs. Progress notes are for resuming, not a substitute for reading the code. The Lead may revise `contracts.md` when evidence requires it — with a dated entry saying what changed and which workers must re-read it.
5. **Server enforces every state change.** A disabled button is not a control.
6. Rules 12/14/15 stand: Terraform-only infra, branch → staging → proof → click-through, no scripted yes to terraform prompts, quiet output.
7. **Autonomy:** no approvals from me tonight. Open choices → best-recommended path, logged in `docs/reports/s20/decisions.md` (decision · options · chosen · why · how to reverse). D1–D10 are fixed, not choices. Only a true hard block pauses work, and only the dependent work (§9).

## 1. Decisions resolved (fixed)

| # | Decision |
| --- | --- |
| D1 | **Many SOWs per deal.** Each SOW package has its own versions, gate, value and approval history. **Deal rollup:** counts by package state (draft · in review · changes requested · CEO exception · approved · awaiting signature · signed · released) shown as a breakdown; the single headline label is the *most-blocked open package* by this order: changes requested > CEO exception > in review > awaiting signature > approved > draft; archived/superseded packages are excluded from the headline and counted separately as "archived n". A released SOW never hides a pending one. Inspect FKs/uniqueness before UI. |
| D2 | **Ownership, three concepts:** deal sales owner = HubSpot owner id resolved via owner mirror (archived included); client account owner = HubSpot company owner property, else "not set" — never derived from a deal; local assignee = DealGate user for actions/tasks only. Unresolved reference → "Owner details unavailable"; empty source → "Unassigned". |
| D3 | **NDA/MSA:** two separate facts per client: **on file** (document uploaded: ✓/–, file link, uploader, time, explicit "on file ≠ signed/verified") and **signed/verified** (set only through the existing SOW Legal review or an explicit verification record). Neither is a blocker for review or submission (S17). Signature evidence requirements and SOW Legal review are unchanged. Remove NDA/MSA from Signature hold reasons unless an explicit verification requirement exists in code — if it does, record it in `decisions.md` rather than silently keep or remove it. |
| D4 | **Freshness:** intake consumer becomes a long-running ECS service (§4 cutover). Displayed freshness reads source-specific watermarks (received / processed / last reconcile), never a worker heartbeat. Published target "typically under 2 minutes", measured. |
| D5 | **Deployment:** official pre-merge path is the scripted branch → staging deploy: migration (backward-compatible) → API **and all worker task-defs** on one immutable image → smoke → SPA publish → invalidation → gates. CI-on-main is post-merge redeploy only. Documented in `docs/runbooks/deploy.md`. |
| D6 | **Deleting governed records:** draft SOW with no submitted package → delete by authorized role with audit line; anything submitted/approved/executed → archive or supersede. Remove routine "Delete client" from mirrored client pages. |
| D7 | **Dedupe key:** HubSpot source event id (or documented composite) with DB uniqueness guard; record + audit + outbox commit atomically before SQS ack. |
| D8 | **Renewals:** two calendar months before term end, month-end clamped, business timezone. |
| D9 | **Stage aggregation** by (pipeline id, stage id); labels for display; explicit unknown-stage bucket; zero-count stages rendered. |
| D10 | **Business Unit:** discover via properties API (deals, then companies); record internal name/type/options; type-aware mirroring. Not a property → `blocked` with evidence. |

## 2. Team, ownership and worktrees

One **Lead** + seven **Workers**, each in its own git worktree (`../dealgate-s20-W1` … `W7`) on branch `s20/W*` off `integrate/s20`. Lead writes no feature code.

**File ownership — every shared file has exactly one owner; others request changes via `docs/reports/s20/requests.md` (Lead routes within the hour):**

| Area | Owner |
| --- | --- |
| `api/app/models/*` (all ORM models), `api/alembic/versions/*` (migration numbering and sequence), `api/app/routers/__init__.py` route registration, shared schemas `api/app/schemas/*` | **Lead** — workers submit model/migration changes as patches in `requests.md`; Lead applies them in sequence and assigns migration ids to avoid multi-head |
| `api/app/integrations/hubspot*`, `api/app/services/hubspot_sync*`, `hubspot_backfill*`, `hubspot_owners*`, `hubspot_properties*`, `worker/`, `infra-tf/modules/hubspot`, `infra-tf/modules/schedulers`, `sync_status*` | W1 |
| `api/app/services/hubspot_pipeline.py` (query/read side), `api/app/routers/pipeline.py`, `web/src/pages/v2/pipeline*`, `client*`, `deal*` | W2 |
| `api/app/services/next_action*`, `deal_comment*`, `tracking_group*`, `saved_view*`, their routers, `web/src/components/tracking/*` (next-action editor, comment thread, group picker, saved-view bar) | W6 |
| `api/app/services/sow_*`, `approvals*`, `deletion.py`, `web/src/pages/v2/sow-workspace*`, `sow-studio*`, `approvals*` | W3 |
| `api/app/services/signature*`, `handoff*`, `release*`, `project*`, `forecast*`, `actuals*`, `web/src/pages/v2/signature*`, `handoff*`, `projects*` | W7 |
| `api/app/routers/reports*`, `api/app/services/report*`, `renewal*`, `web/src/pages/v2/command*`, `reports*`, `renewals*`, `settings/integrations*`, `docs/runbooks/deploy.md` | W4 |
| `tests/**`, `scripts/**` (except deploy scripts owned by W4), `docs/reports/s20/matrix.md`, `tests.md` | W5 |

Anything not listed: first worker to need it requests ownership in `requests.md`; Lead assigns within the hour and records it.

**Workers and scope:**

| Worker | Scope |
| --- | --- |
| **W1 Data truth & sync** | Owner mirror incl. archived (D2); stage/pipeline aggregation by id (D9); Business Unit discovery + type-aware custom props (D10); watermarks + continuous consumer cutover (D4, §4); source-event dedupe + atomic commit (D7, A4); backfill scan generation, resume without premature archive (A3, T33); merged/deleted/association/property-clear handling (T28); freshness alarms (backlog age, DLQ, lag). |
| **W2 Pipeline, client, deal pages** | L02–L08: stage chips filter in place; full filter bar (owner, stage, BU, pipeline, open/closed, attention, SOW state, group, date field with last/next 7/30/90, month/quarter, custom, missing-value; OR within a field, AND across); URL state with explicit-URL precedence, Back restores; 25/50/100 pagination with global totals computed before pagination (A5, T35); deal name column; client rollups (matching vs total; deal owner vs account owner); **deal page** and rebuilt **client page** per the review's surface table; Closed Lost shown plainly (74 Sky); readable activity; no engineering copy; exact-name assertions (T09). Consumes W6's components for next action, latest comment, groups. |
| **W6 Tracking features (end to end)** | Manual watchlists, dynamic groups from saved filters (owner, private/team visibility, client or deal membership, future-deal inclusion, non-additive totals, permissions in counts and shared links); saved views (My opportunities, My actions, Waiting on others, Closing soon, No next action, Stale contact, My approvals); **next action** as structured task (title, assignee, due, status, blocker, outcome) with full history, completing an approval task only via the approval decision; **comments** with history, pinning, internal vs HubSpot-note distinction, permissions. Storage, API, permissions, editing flows and the reusable UI components. T16. |
| **W3 SOW workflow integrity** | L09–L14, A1, A7: stub migration (§6); stop auto-creation; upload carries client + deal binding end to end (T11, T37); one readiness panel; tabs in-workspace with deep links/refresh/Back; CTA state machine; `Not assessed` when GM inputs missing; unknown commercial type shown; many SOWs per deal with the D1 rollup (T14, T31); deletion by state (D6); NDA/MSA per D3 (T41); reviewer/role mapping visible before submission (L14); material change → revision + invalidation (T21); stale-tab refusal (T19); functional reviews approve/reject/request-changes with reasons and rework resubmission; CEO exception conditional with `Not required` otherwise (T20). |
| **W7 Approval-to-delivery** | Signature: prepare only the current approved package; sent/signed/declined/expired; executed-document verification against approved terms; upload alone is not execution (T22). Handoff/release: verify approvals + conditions + executed terms + delivery acceptance + staffing/billing/PO setup; create or link the project exactly once; CRM Closed Won never authorizes release (T23). Projects: provenance to deal/SOW; baseline, amendments, forecast and actuals separate; duplicate-import protection; recovery on deterioration (T24). Internal signoff, client execution and delivery acceptance are three events, all exercised. |
| **W4 Truthful summaries, reporting, renewals, integrations, deploy** | L01, L15, L17–L20, A6, A8: Command center reconciles with Pipeline or shows `Unavailable` + error (T39); Portfolio labels + explicit population/basis reconciled to the mirror; approval-turnaround endpoint **implemented** (if it cannot be tonight, state `missing`, owner W4, next action); Margin/Revenue sourced or labeled unavailable; renewals two-calendar-month rule (D8, T25); integrations page derived from verified config (read-only HubSpot, Cognito configured, storage/signature split); health page with watermarks, backlog age, failures, last reconcile; deploy runbook (D5) and worker image-version proof, rollback tested (T36); API caching/auth-forwarding/webhook-signature/Cognito-claim checks documented with results (A8, T38). |
| **W5 Verification & harness** | Writes test skeletons from `contracts.md` first. T01–T44 as executable tests where possible (Playwright with role users on staging; pytest for server rules; SQL parity for T03). Multi-role e2e users (submitter, delivery, hr, finance, legal, ceo) with tagged data and teardown. Query-plan/latency evidence (A5). Injection tests: freshness (T32), duplicate events (T34), scan resume (T33), report dependency failure (T39). Release evidence. Owns `matrix.md`, `tests.md`, the morning click-through. |

**Integration (Lead), every ~2 hours:** merge each worker branch into `integrate/s20`. **Conflicts are resolved against the agreed behavior in `contracts.md` and the tests — never by precedence of branch or surface.** Record each resolution in `integration-log.md`. Run full regression + both gates; deploy `integrate/s20` to staging via D5; W5 runs the growing suite. **A red integration blocks unrelated merges and deployment; the specific corrective commits needed to restore green are permitted.**

## 3. Cross-cutting requirements

- Status vocabulary from `contracts.md` (`Unknown`, `Not assessed`, `Not configured`, `Processing`, `Failed`, `Stale`); reserve zero/none/approved/complete for verified states.
- Names, not identifiers, everywhere (T09 exact names; targeted checks that known ids never appear as labels; no rejection of legitimate numeric names, amounts, dates).
- Permissions identical across UI, API, aggregates, search, groups, exports, downloads (T27).
- Retries reconcile, never repeat. Context survives refresh/new tab/Back; unsaved-change warnings; specific recoverable errors.
- Fixtures synthetic and tagged; real mirror records read-only.

## 4. Continuous consumer cutover (W1)

1. New ECS service `hubspot_intake` (long-running drain loop, batch of 10 inside the loop, visibility extension, DLQ, alarms on backlog age > 5 min, lag, DLQ > 0) in Terraform, narrowly applied, plan pasted.
2. Deploy the service **disabled** (desired count 0), verify task-def/image/env/IAM match the tested build.
3. Cutover: disable the scheduled intake task-def's EventBridge rule → wait one full interval → confirm the queue has no in-flight messages from the old consumer → set desired count 1 → observe drain and watermarks advance.
4. Rollback: desired count 0 → re-enable the schedule rule. Test the rollback once, then cut over again. Record timings and the measured event-to-UI latency for 20 injected events (T32).
5. Queue ownership: only the service consumes; the old task-def stays registered but unscheduled until the morning decision to delete it.

## 5. Staging isolation — Lead verifies in Hour 0, before any write

Confirm and record in `docs/reports/s20/isolation.md`: database endpoint and name are the staging RDS; SQS queues are the staging queues; S3 buckets are staging; Cognito pool is staging and the test users are tagged; SES is sandbox and every recipient tonight is a verified test address; the HubSpot token is read-only (assert no write methods wired — existing test); the test-data cleanup job matches only tagged records (prove with a dry run). Any item that cannot be confirmed = hard block for writes on that resource until confirmed.

## 6. Stub migration (W3, Lead reviews the dry run before execution)

1. Locate the auto-creation path (file:line in `plan.md`).
2. Dry run: classify each no-file workspace as `empty machine-created` vs `has user content` (scope edits, GM drafts, staffing, comments, actions, documents, decisions, project links); manifest CSV with counts.
3. Back up candidates and dependencies (dated DB dump + S3 keys); record the restore command; test restore on one record.
4. Stop the auto-creation path (code + test).
5. Migrate user content to the correct deal record; archive proven-empty stubs (`archived_reason = machine_stub_s20`); never delete.
6. Legacy routes redirect to the replacement deal page; assert no orphaned attachments or decisions.
7. Reconcile counts before/after; rollback proven on staging (T29).

## 7. Token discipline

- Spawn context: this directive, the review, `contracts.md`, own `plan.md` section, CLAUDE.md — then investigate whatever the task requires. Prefer `grep -n` and ranged reads over whole-file reads; no polling loops; `pytest -q`, `vitest --reporter=dot`, `tail -50`.
- Keep `progress-W*.md` current after each commit (decisions, files, proven, next); resume from it, verify against the code.
- Save durable facts to memory (BU property name, owner mirror table, watermark keys, task-def revisions, test users, queue URLs).
- Two identical failures on one step → log the exact error, move on, flag for Lead.
- Per-worker budget ~6 hours of building; remainder for proving. Lead reserves the last 90 minutes for integration, deploy, full W5 run, and the matrix.
- Workers communicate through `docs/reports/s20/` files and commits only.

## 8. Morning deliverable

- `matrix.md`: one row per capability in the review's requirements table, per finding L01–L20 and per item A1–A8: state (five values), route, test ids, evidence link, **owner + next action for anything not `verified working` / `fixed and tested`**.
- `tests.md`: T01–T44 with **result** ∈ {pass, fail, not run, blocked} and a separate **method** ∈ {automated, manual (steps given)}.
- `decisions.md` (every open choice taken tonight, with reversal), `deploy.md` (component versions, rollback proof), `integration-log.md`, `isolation.md`, stub manifest + rollback proof, T03 parity table (BSC Staffing – UX/UI Designer or nearest real deal, say which), BU discovery evidence, consumer cutover timings.
- **Click-through for Kanna, ≤ 12 steps, through the full journey:** filtered Pipeline → client → deal (Closed Lost plain) → Upload SOW pre-bound → workspace (one readiness, in-place tabs) → scope confirm → staffing/GM → submit → all four functional reviews by role users (one returned for changes and resubmitted) → conditional CEO approval → executed-document upload and verification → delivery acceptance → project created → Command center and a report reconcile to the same rows → renewal date shown as two calendar months. Steps that cannot run tonight are listed as blocked with the reason.
- **Unresolved list** with what each item needs from me.

## 9. Stop rules

A hard block is a permission I must grant, an external service that is down, or an action irreversible on real data. Log it with the exact error, keep working on everything independent of it, list it in the unresolved section. Never work around a control, never record a test as passed that did not run, never merge to main, never write to an unconfirmed resource.
