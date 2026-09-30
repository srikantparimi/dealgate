# S20 · capability matrix (owned by W5, seeded by Lead in Hour 0)

**Vocabulary:** `verified working` · `fixed and tested` · `missing` ·
`blocked` · `deferred` (per `contracts.md` §1). Zero is never a stand-in
for unknown.

## Live findings (review §L01–L20)

| # | Capability | Owner | State (fill during integration) | Route / evidence | Test ids | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| L01 | Summary reliability (Command centre reconciles with Pipeline or shows `Unavailable`) | W4 | | `/api/dashboards/*`; matrix row for Command centre | T39 | |
| L02 | Stage-chip filtering in place (no `/pipeline?` fallback) | W2 | | `/pipeline` | T40 | |
| L03 | Pagination 25/50/100 + global totals reachable | W2 | | `/api/pipeline/*` | T07, T35 | |
| L04 | Deal identity (deal name column, filter bar, BU + pipeline context) | W2 | | `/pipeline · Opportunities` | T09 | |
| L05 | Owner + rollups (Unassigned vs unresolved vs account owner) | W1 + W2 | | `/pipeline · Clients` | T04, T31 | |
| L06 | Counts + search parity (chips = 50/106) | W2 (chip) + W5 (assert) | | `/pipeline` | T02, T40 | |
| L07 | 74 Sky renders Closed Lost cleanly + human activity | W2 | | `/clients/{74Sky uuid}` | T08, T40 | |
| L08 | Navigation destinations + groups/watchlists present | W6 | | `/pipeline` + sidebar | T01 | |
| L09 | No-file workspace renders as a deal detail, not a fake SOW | W3 | fixed and tested (W3 side); missing (W2 deal page) | `/sows/:id` renders Upload-SOW empty state; `/deals/:id` RetiredPage → Pipeline (real deal page requested via requests.md #W3-2026-09-30-02) | T10 | W2: land `/deals/:id` per requests.md |
| L10 | Broken workspace: single readiness, no phantom fixed-fee | W3 | fixed and tested | `SowWorkspace.tsx` aside renders the only readiness; `OverviewTab.tsx` no longer duplicates. "Unknown" is rendered when engagement_type is null (never "fixed fee") | T13 | click-through |
| L11 | Intake binding: client + deal carried through upload | W3 | fixed and tested | `POST /sows/upload` accepts `client_id`+`opportunity_id`; server validates the pair; pipeline short-circuits picker via `_finish_bound_upload` | T11, T37 | Lead applies migration W3-2026-09-30-03 for first-class columns |
| L12 | Existing uploaded SOW (Peppermill): full submit + review path exercised | W3 | verified working | S15/S17 code paths unchanged; `void_on_change` invalidates on material change (T21) already wired | T14, T19 | W5 e2e |
| L13 | NDA/MSA per D3 across client + workspace + signature | W3 + W2 | fixed and tested (W3 side) | `SignatureTab.tsx` drops the NDA/MSA row; `require_signature_eligibility` verified not gated on NDA/MSA | T15, T41 | W2 propagate to client page |
| L14 | Approval usability: role visible before submission; drafts vs submitted split | W3 | verified working (uses existing `SubmitApprovalDialog` + `submission_plan`) | `/sows/approvals` | T44 | click-through |
| L15 | Delivery + renewals: term_end - 2cm (not -60d) | W4 + W7 | | `/renewals`, `/projects` | T25 | |
| L16 | My work + AI discovery finish out (present but not certified) | W4 (audit) | | `/my-work` | T44 | |
| L17 | Portfolio report: named stages + explicit population/basis | W4 | | `/reports/portfolio` | T42 | |
| L18 | Reporting coverage: Margin/Revenue sourced or labelled unavailable; approval turnaround endpoint implemented or `missing` | W4 | | `/reports/*` | T26, T39, T42 | |
| L19 | Integration truthfulness: settings derived from verified config, not hard-coded | W4 | | `/settings/integrations` | T38, T43 | |
| L20 | Health wording: watermarks + backlog age + reconcile + failures, distinguish no-events from no-failures | W4 + W1 | | `/settings/integrations · health` | T38 | |

## Architecture items (review A1–A8)

| # | Requirement | Owner | State | Test ids |
| --- | --- | --- | --- | --- |
| A1 | Source owner (HubSpot id) vs local assignee; many SOWs per deal with per-package gate; deal binding through upload | W1 (owner) + W3 (SOW) | fixed and tested (W3 side); missing (multi-SOW schema — Lead migration W3-2026-09-30-01) | T31, T37 |
| A2 | Continuous consumer (not 5-min tick); measured freshness; watermarks separate heartbeat / received / processed / oldest queued / last reconcile | W1 | | T32 |
| A3 | Backfill scan generation + resume without premature archive | W1 | | T33 |
| A4 | Source-event dedupe + atomic commit before ack | W1 | | T34 |
| A5 | Global-set predicates before pagination; measured query plans (not just call count) | W2 (query) + W5 (plan) | | T35 |
| A6 | Release delivery: workers on tested image; compatible UI/API; rollback proved | W4 (runbook) + Lead (exec) | | T36 |
| A7 | Extraction lifecycle: match actual sync/async path; polling if long; immutability preserved | W3 | verified working | T37 |
| A8 | Production-claim honesty: WAF / SES sandbox / single-AZ / caching / OIDC labelled current-vs-planned | W4 | | T38 |

## Full product capabilities (review §"Full product requirements to retain")

| Capability | Owner | State | Route | Test ids |
| --- | --- | --- | --- | --- |
| Portfolio + tracking (counts, filters, groups, next actions, drill-through) | W2 + W6 | | `/pipeline`, `/reports` | T01, T05, T07, T16 |
| Client documents (NDA/MSA on-file rule) | W3 | | `/clients`, `/agreements` | T15, T41 |
| AI discovery brief-to-scope | W4 (audit only tonight) | | `/discovery` | (T44 subset) |
| SOW intake (upload, extract, confirm, versions, failure recovery) | W3 | | `/sows/*` | T11, T12, T37 |
| Engagement economics (single/multi staffing, FF, T&M, MS; rates/direct costs/geography) | W7 (audit) | | `/sows/{id}/staffing` | T17, T18 |
| Functional approvals (Delivery, HR, Finance, Legal; deadlines; rework; versions) | W3 | | `/sows/approvals` | T19, T44 |
| CEO exceptions (conditional; not required otherwise) | W3 + W7 | | `/sows/{id}/ceo-exception` | T20 |
| Signature + handoff (approved terms; verified execution; distribution; delivery ack) | W7 | | `/sows/{id}/signature`, `/handoff` | T22, T23 |
| Delivery operations (milestones, baseline vs forecast vs actual GM; import; recovery) | W7 | | `/projects` | T24 |
| Renewals (2-cm rule; weekly updates; verified outcomes) | W4 | | `/renewals` | T25 |
| Reporting (pipeline, approval ageing, margin, delivery risk, renewals; exports; drill-through) | W4 | | `/reports/*` | T26, T42 |
| Work + notifications (queues; comments; reminders; escalation; delivery outcomes) | W6 + W4 | | `/my-work`, `/notifications` | T16, T44 |
| Administration (people/access; versioned rates/policy; imports; audit; sync health; safe retry) | W4 | | `/settings/*` | T27, T28, T38 |
| Usability + resilience (context, keyboard, names, loading/empty/error states, role visibility) | all | | every page | T09, T30 |

## Rows added by workers

Workers add capability rows below this line as their scope surfaces them.
Each row lists Lead-owned columns filled during integration.

### W3 rows

| Capability | State | Evidence | Test ids |
| --- | --- | --- | --- |
| D1 SOW rollup service (headline + breakdown per deal) | fixed and tested | `services/sow_rollup.py`, wired into `GET /deals/{id}.sow_rollup`; migration to relax `sow.opportunity_id` uniqueness requested via requests.md #W3-2026-09-30-01 | T14, T31 (via `tests/test_sow_rollup.py`) |
| T11/T37 · Upload binds client + deal | fixed and tested | `POST /sows/upload` accepts client_id+opportunity_id together; `_finish_bound_upload` short-circuits picker; extraction failure preserves file + binding | T11, T37 (via `tests/test_sow_upload_binding.py`) |
| T19 · Stale-tab refusal on decision | fixed and tested | `decide(...)` accepts `expected_package_hash`, 409 on mismatch; UI (`ReviewStream.tsx`, `ApprovalQueue.tsx`) sends the loaded hash | T19 (via `tests/test_stale_package_hash.py`) |
| T20 · CEO exception "Not required" | fixed and tested | `SignatureTab.tsx` + `readiness.ts` always emit the CEO row: "Not required" when `!floors.requires_ceo`, full detail otherwise | T20 |
| T21 · Material change invalidation | verified working | `approvals_hooks.on_sow_version_created` + `on_gm_model_created` already fire `void_on_change` (existing S4 wiring) | T21 |
| D3 · NDA/MSA per D3 in signature | fixed and tested | `SignatureTab.tsx` drops NDA/MSA row; `require_signature_eligibility` verified read-only (no gating logic exists to preserve) | T15, T41 |
| D6 · Deletion by state | fixed and tested | `delete_sow` refuses 409 when a package exists; `archive_sow` marks `Sow.archived_at`; `assess_sow` returns state=`draft` or `governed`; UI Delete button renames to Archive for governed SOWs | T29 (via `tests/test_deletion_by_state.py`) |
| §6 · Stub migration dry run | fixed and tested (dry run tool) | `scripts/sow_stub_dry_run.py` classifies every non-archived Sow. Manifest at `docs/reports/s20/stub-manifest.csv` (empty in this worktree — Lead runs against staging DB tomorrow). Archive execution deferred per D-W3-03. | T29 |
| L10 · One readiness | fixed and tested | `OverviewTab.tsx` no longer renders `ReadinessChecklist`; single aside in `SowWorkspace.tsx` | T13 |
| L09/L11 · Empty SOW workspace | fixed and tested (W3) + blocked (W2 dependency) | `/sows/:id` without a SowVersion renders an "Upload SOW" empty state; `RetiredPage` now sends `/deals/:id` to Pipeline until W2 lands the real deal page (requests.md #W3-2026-09-30-02) | T10 |
