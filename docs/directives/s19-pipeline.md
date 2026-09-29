# Directive S19: Pipeline — clients, opportunities, readiness and next actions

From: Kanna Parimi, product owner. Commit as `docs/directives/s19-pipeline.md` before any code. Three slices, each its own branch → staging → smoke green → my click-through → squash to main. Fresh session per slice. Builds on S18 §2a (HubSpot backfill, `hubspot_pipeline` query service, deal cache columns).

## Principles

- HubSpot owns commercial records (companies, deals, stages, owners, notes). DealGate owns governance and collaboration (agreements on file, SOWs, approvals, next actions, comments, groups). Read-only toward HubSpot until production.
- Page loads query the local DB only. Workers keep the mirror current. No HubSpot call in a request path.
- One query service feeds every view: Pipeline (both views), Command center, SOW picker, groups. Any page building its own client/deal query is a defect.
- Closed Won in HubSpot never implies approved for delivery. Sales stage and DealGate readiness are separate columns, always.
- Agreements stay S17-simple: NDA/MSA = documents on file (yes/no, optional expiry from the file) + the SOW checkbox. No agreement state machine.

## Slice 1 — Data correctness and navigation

**Verify before building (first commit, report only):**
1. Pull pipelines and stages from `GET /crm/v3/pipelines/deals`; store id, label, display order, closed-won/lost flags. Assert every cached deal's stage id resolves to a label.
2. Sample 10 deals at random plus the 3 clients with the most deals; compare name, stage, amount, currency, owner, close date and company associations against the HubSpot UI/API. Confirm Capitec's count in HubSpot with a company filter. Any mismatch is a bug in the mapper — fix and rerun backfill before any UI work.
3. Count deals associated with more than one company; decide primary company = the association labeled primary, else the first; document.
4. Report: pipelines found, stage table, sample diff, multi-company count, currency mix (deal counts per currency).

**Data model (migration, reversible):**
- `opportunity`: add `hubspot_pipeline_id`, `hubspot_stage_id`, `stage_order`, `is_closed_won`, `is_closed_lost`, `currency`, `hubspot_created_at`, `hubspot_last_activity_at`, `hubspot_last_modified_at`, `primary_client_id`. Index `(pipeline, stage)`, `(owner_id)`, `(hubspot_last_activity_at)`, `(close_date)`, `(primary_client_id)`.
- `hubspot_pipeline`, `hubspot_stage` tables (mirror).
- `next_action`: id, opportunity_id, description, owner_user_id, due_date, status (open/in_progress/blocked/complete), created_by, created_at, completed_at. Index `(opportunity_id, status)`, `(owner_user_id, due_date)`. Data model only in slice 1; UI in slice 2.
- `sync_status`: source, last_success_at, last_attempt_at, last_error, lag_seconds.
- `user_preference`: user_id, key, value (for remembered view).

**Query service contract (`hubspot_pipeline`):**
- `list_clients(filters, page, page_size, sort)` → clients with: owner, open opp count, open value per currency, stage breakdown (count per stage), agreements on file (NDA yes/no, MSA yes/no), SOW approval summary (worst state across open opps), attention flags, latest activity date, next action (from slice 2 onward). Clients with zero open deals included, filterable.
- `list_opportunities(filters, page, page_size, sort)` → deals with: client, name, stage label, amount, currency, close date, owner, SOW approval state, attention flags, last activity, next action.
- `summary(filters)` → computed across ALL matching authorized records, not the page: open count, open value per currency (deduped by deal id), closing this month, overdue actions, pending approvals, agreement gaps (client has open deal and no NDA or MSA file).
- Filters: view, pipeline, stage[], owner[], group, readiness state[], attention[], date field ∈ {created, close, last_activity, action_due} with from/to, search (client or deal name, indexed).
- Sort: default `attention desc, next_action.due asc, close_date asc`; any column sortable server-side.
- Pagination: offset for clients (page sizes 25/50/100), children (deals under a client) loaded on expand, paged at 25. Total count returned. All in ≤ 3 queries per page load, no N+1 (window functions / grouped subqueries; verify with query logging in tests).

**Four status columns (exact definitions):**
| Column | Values | Source |
| --- | --- | --- |
| Sales stage | HubSpot stage label | mirror |
| Agreements | NDA ✓/–, MSA ✓/– | agreement files on client |
| SOW approval | none · draft · in review (with function) · changes requested · CEO exception · approved · awaiting signature · signed | SOW package state |
| Attention | overdue action · stalled 14d+ (no activity) · no owner · pending approval · closed-won-not-released | derived, multiple allowed |

**UI:**
- Route `/pipeline`. Toggle Clients (default) / Opportunities; remembered per user.
- Summary bar: the `summary()` numbers, per currency where money.
- Filters row with the explicit date-field selector; pipeline selector shown only when >1 pipeline.
- Stage strip: chips with count and value for the selected pipeline; click to filter.
- Clients table: sticky name column; expand row → its opportunities (paged). Stage breakdown shown as compact counts, never one "commercial stage".
- Opportunities table: columns per contract; latest-update preview column reserved (slice 2).
- Footer: page size, page controls, "N matching records".
- Right-side panel (slice 1 = read-only): deal or client header, stage, amounts, agreements on file, SOWs with states, sync timestamp. Editable pieces arrive in slice 2.
- Header: "Create in HubSpot" (deep link to the portal's new-deal URL) replaces "New opportunity". Owner shows name only, "Unassigned" when unmapped. SOW count = actual SOWs.
- Sync visibility: "Synced 4 min ago"; amber banner when lag > 30 min or last error set.
- Command center's pipeline card and the SOW upload deal picker read from the same service (picker auto-suggests from extracted client name; no match → SOW saved as "Not linked to HubSpot").

**Sync (finish §2b here):** webhooks (deal create/update/delete/association change, signature verified) → SQS → worker re-reads from API; dedupe by event id; deletes/merges archive locally and reassign SOWs to the surviving deal; nightly reconcile; sync_status updated every run; 429 → backoff with jitter; outage → status shows delayed, page still serves cached data.

**DoD slice 1:** verification report; all suites + smoke green; test-data gate 0; query-count test (≤3 per list call); per-page consistency test (Command center, Pipeline, picker show identical records for a seeded deal, and none after deletion); screenshots: clients view with real data, expanded client, opportunities view, stage strip, summary bar per currency, sync banner (simulate lag), a webhook-created test deal appearing ≤2 min; my click-through.

## Slice 2 — Operational tracking

- **Next action UI:** on every open opportunity: description, responsible person (user picker), due date, status. Inline in the detail panel and editable from the row. Completing creates the audit event; "overdue" attention flag derives from it. Optional per client too (rolls down to no deal).
- **Internal comments:** `deal_comment` (opportunity or client scope), author, body, pinned flag, created_at. Permissions: visible to roles per People & access; never sent to HubSpot. Latest comment (author, date, source tag) as the row's update preview; pinned comment wins over newer routine ones.
- **Combined timeline** in the detail panel: DealGate comments + next-action events + SOW/approval events, each labeled by source. HubSpot notes appear here in slice 3.
- **Manual groups:** `tracking_group` (name, owner, visibility private/team, member_kind client|opportunity), `tracking_group_member`. Client groups auto-include current and future opportunities of member clients. Group picker = searchable dropdown + up to 5 pinned tabs. Groups filter the Pipeline and show counts on Command center; totals across overlapping groups never double-count on dashboards (dashboard sums deals, not group memberships).
- Agreement/SOW/margin status already shown from slice 1; slice 2 makes them clickable into the SOW workspace.
- **DoD:** create a next action, see it sort to the top when overdue; comment + pin; manual group of 3 clients shows all their deals; permissions test (a user without comment rights sees none); screenshots; my click-through.

## Slice 3 — Automation

- **Rule-based groups:** rule stored on the group as explicit predicates (pipeline id, stage ids within it, owner ids, close date range, readiness states); evaluated server-side by the same filter engine as the page — no second implementation. Membership shown live; "why is this here" explains the matched predicates.
- **HubSpot notes:** first check the installed app's scopes and whether the portal supports engagement webhooks for notes; use them if available, else 15-minute incremental poll by `hs_lastmodifieddate`. Mirror note id, body, author, timestamp, associations into `hubspot_note`; show in the timeline with source label. Never write notes back.
- **Reminders and escalation:** next action due tomorrow → owner email (existing SES path); overdue 3 business days → owner's manager; stalled 14d+ with open SOW → account owner. All through the existing notification outbox; configurable in Settings.
- **DoD:** rule group updates when a deal changes stage (webhook-driven); note appears within one poll cycle or via event; reminder email screenshot from noreply@dealgateapp.com; escalation test with clock advance.

## Edge cases (each needs a test; list them in the checklist)

Deal with no company · company with no owner · deal in two companies · deal deleted in HubSpot · deals merged · company merged · Closed Lost (drops from open counts, stays visible with filter) · Closed Won without SOW (attention flag) · amount empty or 0 · mixed currencies on one client · stage id not in pipeline table (unknown stage shown as such, alerted) · owner email not in DealGate · 429 rate limit · HubSpot outage mid-backfill (resume, not restart) · webhook replay/duplicate · out-of-order events · client with zero deals · 10k-deal pagination timing (< 500 ms per page on staging data).

## Engineering standards (apply to all slices)

- **Correctness over green tests:** no test may assert a literal it also seeds without exercising the code path; every acceptance test runs against a real DB (Postgres in CI), not mocks of the query service. The verifier (a different session) reruns the proof before merge.
- **Efficiency:** no N+1 (assert query counts), indexes as listed, aggregation in SQL not Python/JS, no client-side filtering of paged data, response payloads carry only rendered fields.
- **Single service, single truth:** grep gate fails the build if any router outside `hubspot_pipeline` selects from `opportunity` for listing.
- **Checklist and proof matrix:** `docs/directives/s19-checklist.md` written before coding, one line per screen/endpoint/job/edge case; the report puts a proof reference beside every line; no proof = not done.
- **Token discipline:** read CLAUDE.md, this directive and the previous slice's report only; keep `docs/reports/s19-<slice>-progress.md` updated after each commit and resume from it; save durable facts (pipeline ids, secret ARNs, task-def revisions, e2e users) to memory; quiet test output, tail/grep logs, read line ranges; two identical failures → stop and write the error into the progress file.
- **Reporting:** standard format per slice, plus the verification report in slice 1 and the checklist matrix in all three. Stop for my click-through before each merge.
