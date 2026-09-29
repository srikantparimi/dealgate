# S18 §2 — HubSpot as source of Pipeline clients · pre-coding checklist

Derived from `docs/directives/s16-cleanup-hubspot.md` §S16b and the S18 §2
directive. Every line lands with a test or a screenshot; the report lists
the same lines with a proof reference beside each. **A line with no proof
in the report = the slice is not done.** No "will follow up" entries.

## A. Data model + state

- A1. `opportunity.hubspot_deal_id` — already nullable, partial-unique — is the sync key. No migration for it.
- A2. `opportunity.source` — extend the enum-checked set to keep `hubspot | sow_upload | bulk_import | manual`. Pipeline reads only `source='hubspot' AND archived_at IS NULL`.
- A3. Cache-on-intake columns on `opportunity`: `amount NUMERIC(14,2) NULL`, `close_date DATE NULL`, `stage_label VARCHAR(64) NULL`, `hubspot_last_seen_at TIMESTAMPTZ NULL`. Reversible alembic migration.
- A4. `hubspot_deal_id` on **already-uploaded SOWs**: linked via the same `opportunity` row when the user picks a deal; empty means "Not linked to HubSpot".
- A5. Deal states in DealGate: **live** (present in HubSpot, archived_at null), **archived** (deleted/merged in HubSpot, archived_at set, reason='hubspot_deleted'), **closed-lost** (sales_stage / stage_label = closedlost, still live). Pipeline filters archived; Closed-Lost is a filter tab, not hidden.
- A6. `integration_event.source_event_id` remains the dedupe key. New rows come from SQS-driven receiver; existing intake handler unchanged.

## B. Endpoints (server)

- B1. `GET /pipeline/deals` — new. Returns HubSpot-sourced live opportunities: id, hubspot_deal_id, name (from HubSpot dealname cache on client/opportunity), company (client legal_name), stage_label, amount, owner email+name, close_date, linked_sows[]. Sort by close_date asc nulls last. Query pagination. Role-gated per existing client read set.
- B2. `GET /pipeline/deals/{id}` — new. Same as B1 for a single row + last_synced_at + provenance breadcrumb.
- B3. `GET /hubspot/deals/search?q=` — new. Returns HubSpot-linked opportunities (id, hubspot_deal_id, name, client_name) matching `q` on name or company. Feeds SOW-upload picker.
- B4. `POST /sows/jobs/{id}/pick` — extend the request schema: `{ link_existing_opportunity: uuid } | { link_hubspot_deal: string } | { not_linked: true }`. `create_new` **removed** — the only way to create a new client is via HubSpot sync.
- B5. `POST /integrations/hubspot/webhook` — signature+timestamp checks stay; body now written to SQS (or a DB row when local dev), not stored-only.
- B6. `POST /integrations/hubspot/backfill` — new SystemAdmin-only trigger. Returns run_id, dispatches to worker.
- B7. `GET /integrations/hubspot/backfill/{run_id}` — new. Returns counts (deals_seen, deals_created, deals_updated, deals_archived, companies_matched, companies_created, owners_matched, owners_unassigned, errors).
- B8. `GET /integrations/hubspot/health` — new. Returns last_backfill_at, last_webhook_at, last_reconcile_at, drift_count. Feeds System health page.
- B9. `POST /sow/{opp_id}/link-hubspot` — new. Body `{ hubspot_deal_id: string | null }`. Re-links a SOW-upload opportunity to a HubSpot deal, or clears it. Audit on both sides.
- B10. Read-only guard: no new endpoint calls `HubSpotClient.update_deal`. Test proves it — assert count of write-back call sites in `app/` equals what it was at Step 0 (currently only `hubspot_writeback` service, which is unrouted this slice).

## C. Jobs / workers

- C1. Backfill worker (`worker/hubspot_backfill.py`, new). Paged `/crm/v3/objects/deals?properties=dealname,dealstage,pipeline,hubspot_owner_id,amount,closedate&associations=companies&limit=100`. Uses shared `hubspot_intake._upsert_opportunity` per deal so single-deal + backfill converge. Idempotent — a second run produces zero created, zero updated.
- C2. SQS receiver in `worker/hubspot_intake.py` — replace DB poll with `receive_message` loop against `dealgate-staging-hubspot-events`. Long-poll 20s, visibility timeout 5m, DLQ after 3.
- C3. Nightly reconcile job (`worker/hubspot_reconcile.py`, new) — walk HubSpot deals + local opportunities, count drift (missing local, missing HubSpot, stage mismatch), write to `integration_health` table. Run at 03:00 UTC via EventBridge (`schedulers` module).
- C4. Backoff on HubSpot 429 — every read path in `HubSpotClient` respects `Retry-After` header, exponential backoff 1/2/4/8s, max 4 retries, then bubble.
- C5. Owner mapping — deal's `hubspot_owner_id` → `/crm/v3/owners/{id}` → email → `user` table lookup. Unmatched: assign to sentinel `Unassigned` user (create once at first backfill), emit one `Task` "Assign owner for HubSpot deal X" to Sales Leader.

## D. Terraform / infra

- D1. `infra-tf/modules/hubspot/` (new) — SQS main queue + DLQ, IAM policy for API task role (SendMessage) and worker task role (ReceiveMessage, DeleteMessage). Outputs queue URLs.
- D2. `infra-tf/modules/api/main.tf` — inject `HUBSPOT_EVENT_QUEUE_URL` env from the new module output.
- D3. `infra-tf/modules/schedulers/main.tf` — EventBridge schedule for nightly reconcile task (`worker/hubspot_reconcile.py` in the existing worker image).
- D4. `infra-tf/modules/api/main.tf` — task-role permission for `secretsmanager:GetSecretValue` on `dealgate/staging/hubspot_token` (already present from Step 0 — verify).
- D5. No CLI, no console (CLAUDE.md rule 12). If anything can't yet be TF-expressed, list it in the report as §3 handover.

## E. Screens (SPA)

- E1. `/pipeline` — rebuilt. Reads only from `GET /pipeline/deals`. Columns: name, company, stage, amount, owner, close date, linked SOWs (count + hover list). Tabs: All / Closed-Lost. Row → `/clients/:client_id`. **Remove "New opportunity" button and `NewOpportunitySheet` import.**
- E2. `/command` — Pipeline readiness card reads from the same `GET /pipeline/deals` service — not `listClients`. Any client-count widget staying on `listClients` gets a comment stating it counts *all* clients (HubSpot + NDA-only + SOW-uploaded) and remains client-scoped by design.
- E3. SOW board (`/sow-studio` or wherever it lives) — an unlinked SOW-uploaded opportunity shows a "Not linked to HubSpot" pill next to the client name. Never appears as a Pipeline row.
- E4. SOW upload picker (`ClientPickerModal`) — replaces "create new" with a searchable HubSpot-deal dropdown backed by `GET /hubspot/deals/search`. Auto-suggests based on the extract's `client_name`. `[ Not linked to HubSpot ]` remains an explicit option; picking it flows to E3.
- E5. System health — HubSpot section shows last backfill / last webhook / last reconcile timestamps + drift count.

## F. Edge cases (each line = one test)

- F1. Deal with no company → opportunity created with `client_id` = the "Unknown Company (HubSpot)" sentinel client; Pipeline row renders "—" for company; NDA/MSA gap task NOT fired on the sentinel.
- F2. Company with no owner (deal has no `hubspot_owner_id`) → opportunity owner = `Unassigned` user; one Task "Assign owner for deal X" to Sales Leader; Pipeline row shows "Unassigned" in the owner column.
- F3. Duplicate company names — client resolver dedupes by HubSpot company id first (never on name). Two HubSpot companies with the same legal name produce two distinct DealGate clients; test asserts count.
- F4. Deal deleted in HubSpot → webhook or reconcile marks local opportunity `archived_at = now`, `archived_reason = 'hubspot_deleted'`; never hard-delete; row disappears from Pipeline; audit event `opportunity.archived`.
- F5. Deal moved to Closed Lost → `sales_stage`/`stage_label` sync; row moves to "Closed-Lost" tab, not removed. Test asserts tab count changes.
- F6. Deal with amount 0 or empty → `amount = 0` renders as "$0", `amount = None` renders as "—"; neither crashes the row or the total.
- F7. HubSpot 429 during backfill → `HubSpotClient` retries per Retry-After up to 4 times; backfill counter increments `hubspot_429_seen`; run still completes; test uses `respx` to inject 429 then 200.
- F8. HubSpot outage (5xx / connection refused for the whole run) → backfill exits non-zero with `errors > 0`; System health `last_backfill_at` unchanged; Pipeline still renders from local cache with a "HubSpot last synced X ago" banner.
- F9. SOW picker: extracted `client_name` matches zero HubSpot deals → dropdown shows "No HubSpot deals match. [ Not linked to HubSpot ]"; picking it succeeds.
- F10. SOW picker: user later re-links via `POST /sow/{opp_id}/link-hubspot` — previously "Not linked" SOW now shows on Pipeline row's linked_sows[]; audit event on both.

## G. Shared-service completeness (rule from directive)

Every page that shows deals or clients reads through **the same query service**. Grep must produce exactly this ownership after the slice:

- G1. `/pipeline` (web/src/pages/v2/Pipeline.tsx) → `GET /pipeline/deals`.
- G2. `/command` Pipeline card (web/src/pages/v2/command/PipelineReadinessTable.tsx) → `GET /pipeline/deals`.
- G3. SOW-upload picker (web/src/pages/v2/sow-studio/upload/ClientPickerModal.tsx) → `GET /hubspot/deals/search`.
- G4. SOW board (wherever a SOW row shows a deal link) → the linked_sows embed on `GET /pipeline/deals`, or a matched `GET /pipeline/deals/{id}` on the SOW detail page.
- G5. `listClients` (`web/src/api/client.ts`) survives, but only for **client-scoped** surfaces (Agreements register, Client list/detail). Any other caller listed on grep day-of is either routed through the shared service or written as a §3 handover line in the report with the file path.

## H. Proof matrix (this fills the report)

Every A/B/C/D/E/F/G line above gets one of: `pytest -q path::name`, `vitest --reporter=dot path`, `scripts/deploy-smoke.sh` step, or a screenshot filename under `docs/reports/s18-2/`. The report is the checklist reprinted with the proof in a right-hand column.

## I. Out of scope for this slice

- HubSpot write-back (any of the three governance properties). `HubSpotClient.update_deal` and `services/hubspot_writeback.py` stay on disk, unrouted, un-called.
- HubSpot pipeline-rule enforcement (blueprint §6.3).
- AI adviser HubSpot notes.
- Prod portal cutover — staging portal only.
