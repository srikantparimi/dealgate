# S19 slice 1 — pre-coding checklist

Derived from `docs/directives/s19-pipeline.md` §Slice 1 and the
verification report `docs/reports/s19-1-verify.md`. Every line lands
with a test or a screenshot; the slice report reprints this list with
a proof reference beside each line. **A line with no proof = the
slice is not done.** No "will follow up" entries.

## A · Data model (one alembic migration, reversible)

- A1. `hubspot_pipeline` table: `id (VARCHAR)`, `label`, `display_order INT`, `archived BOOL`, `updated_at`. Primary key = HubSpot pipeline id.
- A2. `hubspot_stage` table: `id (VARCHAR)`, `pipeline_id FK → hubspot_pipeline`, `label`, `display_order INT`, `is_closed BOOL`, `probability NUMERIC`, `archived BOOL`, `updated_at`. Index `(pipeline_id, display_order)`.
- A3. `opportunity` gains: `hubspot_pipeline_id (VARCHAR NULL)`, `hubspot_stage_id (VARCHAR NULL)`, `stage_order INT NULL`, `is_closed_won BOOL NOT NULL DEFAULT FALSE`, `is_closed_lost BOOL NOT NULL DEFAULT FALSE`, `currency VARCHAR(8) NULL`, `hubspot_created_at TIMESTAMPTZ NULL`, `hubspot_last_activity_at TIMESTAMPTZ NULL`, `hubspot_last_modified_at TIMESTAMPTZ NULL`, `primary_client_id UUID NULL FK → client.id`.
- A4. `opportunity` indexes: `(hubspot_pipeline_id, hubspot_stage_id)`, `(owner_id)`, `(hubspot_last_activity_at)`, `(close_date)`, `(primary_client_id)`.
- A5. `next_action` table: `id UUID PK`, `opportunity_id FK`, `description VARCHAR(1024)`, `owner_user_id FK → user`, `due_date DATE`, `status VARCHAR CHECK IN ('open','in_progress','blocked','complete')`, `created_by FK → user`, `created_at`, `completed_at`. Indexes `(opportunity_id, status)`, `(owner_user_id, due_date)`. Data model only in slice 1; UI in slice 2.
- A6. `sync_status` table: `source VARCHAR PK`, `last_success_at TIMESTAMPTZ`, `last_attempt_at TIMESTAMPTZ`, `last_error VARCHAR(1024) NULL`, `lag_seconds INT NULL`.
- A7. `user_preference` table: `user_id FK`, `key VARCHAR`, `value JSONB`. PK `(user_id, key)`.
- A8. Reversible downgrade for all of the above.

## B · Sync / workers (finish former §2b here)

- B1. Pipeline-stage mirror service: fetch `GET /crm/v3/pipelines/deals` on backfill / webhook start; upsert into `hubspot_pipeline` + `hubspot_stage`; return an in-memory id → label + is_closed map.
- B2. `_upsert_opportunity` populates every new column from the deal payload + the stage mirror: `stage_label` = resolved label, `is_closed_won/lost` from stage `metadata.isClosed` + `displayOrder==6/7`, `stage_order` = display order, `currency` = `deal_currency_code`, `hubspot_created_at` = `createdate`, `hubspot_last_activity_at` = `notes_last_updated` (or `hs_lastmodifieddate` fallback), `hubspot_last_modified_at` = `hs_lastmodifieddate`, `primary_client_id` = client resolved from primary company.
- B3. SQS queue + DLQ in `infra-tf/modules/hubspot/` (new); IAM for API task role (SendMessage) and worker task role (ReceiveMessage, DeleteMessage). Task-def env `HUBSPOT_EVENT_QUEUE_URL`.
- B4. `POST /integrations/hubspot/webhook` — signature + timestamp check stays; enqueue raw event to SQS instead of storing an `integration_event` row.
- B5. `worker/hubspot_intake.py` becomes an SQS consumer (long-poll 20s, visibility timeout 5m, DLQ after 3). Re-reads the deal from the CRM API, never the webhook payload.
- B6. `worker/hubspot_reconcile.py` (new). Nightly EventBridge schedule (`schedulers` module). Walks all HubSpot deals; upserts drift; updates `sync_status`.
- B7. Deleted / merged deals archive locally (`archived_at`, `archived_reason='hubspot_deleted'` or `'hubspot_merged'`); associated SOWs reassign to the surviving deal on merge.
- B8. `sync_status` written by every backfill / webhook / reconcile run.

## C · Query service (one router, `hubspot_pipeline`)

- C1. `list_clients(filters, page, page_size, sort)` — clients with: owner, open opp count, open value per currency (deduped by deal id), stage breakdown (count per stage), agreements on file (NDA yes/no, MSA yes/no), SOW approval summary (worst state across open opps), attention flags, latest activity date, next action (from slice 2). Includes zero-open clients; filterable.
- C2. `list_opportunities(filters, page, page_size, sort)` — deals with: client, name, stage label, amount, currency, close date, owner, SOW approval state, attention flags, last activity, next action.
- C3. `summary(filters)` — computed across ALL matching authorized records, not the page: open count, open value per currency (deduped), closing this month, overdue actions, pending approvals, agreement gaps (client has open deal and no NDA or MSA file).
- C4. Filter set: view, pipeline, stage[], owner[], group, readiness state[], attention[], date field ∈ {created, close, last_activity, action_due} with from/to, search (client or deal name, indexed).
- C5. Sort: default `attention desc, next_action.due asc, close_date asc`; every column sortable server-side.
- C6. Pagination: offset for clients (page sizes 25/50/100), children (deals under a client) loaded on expand, paged at 25. Total count returned.
- C7. **Query-count invariant:** ≤ 3 queries per list call — window functions / grouped subqueries, not N+1. Test asserts by wrapping the SQLAlchemy connection in a counting listener.
- C8. Grep gate: build fails if any router outside `services/hubspot_pipeline.py` runs `select(Opportunity)` for listing (single-truth guarantee).

## D · Four status columns (exact per directive)

- D1. Sales stage — HubSpot stage label, sourced from the mirror.
- D2. Agreements — NDA ✓/–, MSA ✓/–, from agreement files on client.
- D3. SOW approval — none · draft · in review (with function) · changes requested · CEO exception · approved · awaiting signature · signed. From SOW package state.
- D4. Attention — overdue action · stalled 14d+ (no activity) · no owner · pending approval · closed-won-not-released. Multiple allowed. Derived server-side, cached at query time.

## E · UI (`web/src/pages/v2/Pipeline.tsx` rebuilt)

- E1. Route `/pipeline` (existing). Toggle Clients (default) / Opportunities — remembered per user via `user_preference`.
- E2. Summary bar shows `summary()` numbers per currency where money.
- E3. Filter row with explicit date-field selector; pipeline selector shown only when >1 pipeline.
- E4. Stage strip: chip per stage with count + value for the selected pipeline; click to filter.
- E5. Clients table: sticky name column; expand row → its opportunities (paged 25). Stage breakdown as compact counts (never one "commercial stage" summary).
- E6. Opportunities table: columns from D1–D4 + amount + currency + close date + owner name + last-activity date. Latest-update preview column reserved for slice 2.
- E7. Footer: page size selector, page controls, "N matching records".
- E8. Right-side detail panel (slice 1 read-only): deal or client header, stage, amounts, agreements on file, SOWs with states, sync timestamp.
- E9. Header: "Create in HubSpot" deep link (`https://app.hubspot.com/contacts/48656168/deal/new`) replaces "New opportunity".
- E10. Owner column shows name only, "Unassigned" when unmapped (F2 sentinel).
- E11. SOW count = actual SOWs on the deal.
- E12. Sync visibility: "Synced N min ago" from `sync_status`; amber banner when lag > 30 min or `last_error IS NOT NULL`.
- E13. Command center's pipeline card reads from `list_clients` (same service).
- E14. SOW upload deal picker reads `search_pipeline_deals`; auto-suggests from extracted client name; no match → SOW saved as "Not linked to HubSpot" (per §2a preserved behaviour).

## F · Cross-page consistency (single-service rule)

- F1. Command center pipeline card, `/pipeline`, and SOW upload picker return **identical records** for a seeded deal.
- F2. After deleting that seeded deal, all three return zero records for it.
- F3. Grep test: no `select(Opportunity)` for listing outside `services/hubspot_pipeline.py`.

## G · Edge cases (each = one test)

- G1. Deal with no company → primary_client_id = "Unknown Company (HubSpot)" sentinel; renders "—" for company; NDA/MSA gap not fired on sentinel. Fixture: `32387658902` (PriceLine), `32790917642` (Edisen).
- G2. Company with no owner → owner = Unassigned sentinel (F2 lands in §2a); UI renders "Unassigned".
- G3. Deal in two companies → primary picked per rule (labeled > first); secondary associations recorded on `opportunity.hubspot_secondary_client_ids` (JSONB) so the UI can show "+2 others". Fixture: `48350247038` (EY SA).
- G4. Deal deleted in HubSpot → webhook or reconcile marks `archived_at`, reason `hubspot_deleted`; row disappears from Pipeline; audit `opportunity.archived`.
- G5. Deals merged → surviving deal keeps its rows; archived deal reassigns SOWs to survivor by `hubspot_deal_id` before archiving.
- G6. Company merged → client resolver keeps the survivor's `hubspot_company_id`; opportunities reassign transparently.
- G7. Closed Lost → is_closed_lost=true; drops from open counts; still visible under a Closed-Lost filter.
- G8. Closed Won without SOW → attention flag `closed-won-not-released`. Fixture: any of the 253 Closed-Won mirror rows without an attached SOW.
- G9. Amount empty or 0 → summary/list render "$0" for 0 and "—" for null; totals don't crash. Fixture: `33440725130` (null amount).
- G10. Mixed currencies on one client → summary shows one row per currency, never sums across.
- G11. Stage id not in `hubspot_stage` (drift) → row rendered with "Unknown stage: {id}" pill; sync_status writes an error string; alert visible on system health.
- G12. Owner email not in DealGate → falls through to Unassigned sentinel; task "Assign owner for deal X" created for Sales Leader.
- G13. HubSpot 429 → `HubSpotClient._get` retries per §2a; workers count as expected. Test uses `respx` (already covered in §2a; keep passing).
- G14. HubSpot outage mid-backfill → resume from `after=` cursor stored in `sync_status`; not restart from scratch.
- G15. Webhook replay / duplicate → SQS message id + `integration_event.source_event_id` dedupe; second delivery = no-op with audit log line.
- G16. Out-of-order events → each event re-reads the deal from CRM API, so late events see the current authoritative state (self-healing).
- G17. Client with zero deals → visible in Clients view; count = 0; no attention flag.
- G18. 10k-deal pagination timing < 500 ms per page on staging data — synthetic seed test.

## H · Sync + observability

- H1. `sync_status` rows for `hubspot_backfill`, `hubspot_webhook`, `hubspot_reconcile`.
- H2. UI banner reads `sync_status.lag_seconds`.
- H3. Backfill resumes from last-known `after` cursor on retry (persisted between runs).
- H4. Reconcile job diffs mirror vs HubSpot and writes drift count + first N drift ids to `sync_status.last_error`.

## I · Terraform / infra

- I1. Reconcile the S18 §2a inline drift **first** (`terraform apply`): `HUBSPOT_TOKEN` secret + `HUBSPOT_TOKEN_SECRET_ARN` env on api task-def; task-role inline policy `officeapp-dev-api-exec-secrets` includes the token ARN.
- I2. New `infra-tf/modules/hubspot/`: SQS main queue + DLQ + IAM.
- I3. `infra-tf/modules/api/main.tf`: `HUBSPOT_EVENT_QUEUE_URL` env from the new module.
- I4. `infra-tf/modules/schedulers/main.tf`: EventBridge schedule for nightly reconcile.
- I5. No console / CLI changes for anything TF can express (rule 12).

## J · Tests + DoD

- J1. Every A/B/C/D/E/F/G/H line has one of: `pytest -q path::name`, `vitest --reporter=dot path`, `scripts/deploy-smoke.sh` step, or a screenshot filename under `docs/reports/s19-1/`.
- J2. Per-page consistency test (F1 + F2) — Command center + Pipeline + picker for a seeded deal.
- J3. Query-count test (C7) — asserts ≤ 3 for `list_clients`, `list_opportunities`, `summary`.
- J4. Correctness-over-green rule: no test asserts a literal it also seeded without exercising the code path; every acceptance test runs against a real DB (Postgres in CI), not a mocked query service.
- J5. Verifier session reruns the proof against staging before merge.
- J6. Playwright: create a test deal in HubSpot → appears in DealGate within 2 min via webhook + SQS + worker. **DEFERRED — pending PO HubSpot deal-create access, scheduled 2026-09-30. `tests/e2e/specs/25-*` stays on main in observer mode (`E2E_DEAL_NAME` env); run then, update the report.**
- J7. Screenshots: Clients view real data, expanded client, Opportunities view, stage strip, summary bar per currency, sync banner (simulated lag), the webhook-created test deal. **Five landed today via `tests/e2e/specs/26-*` (see `docs/reports/s19-1/`); the sixth — the webhook-created deal — waits on J6.**
- J8. Kanna's click-through before squash to main. **DEFERRED to post-merge · pre-tomorrow-J6-run window per PO instruction: merge first, click through after.**

## K · Out of scope for slice 1 (carry to slice 2 or 3)

- Slice 2: next-action UI, deal_comment + timeline, manual `tracking_group` + `tracking_group_member`, agreement/SOW/margin clickable into SOW workspace.
- Slice 3: rule-based groups, HubSpot notes mirror, reminders / escalation email path.
- Write-back to HubSpot (still frozen until prod).

## L · Portal data findings (report only, no code change)

- L1. **Currency mix — 655 USD + 1 null, 0 ZAR** despite an SA-heavy client base (Capitec Bank Limited 44, Standard Bank 42, Momentum Group 37, Vitality Global, EY SA, Retro Rabbit owners with `.co.za` emails). Investigate whether the HubSpot portal default is USD or whether SA deals simply have `deal_currency_code` unset and read as USD by convention. Report the finding in the slice report; Kanna fixes the data in HubSpot if that's the cause. **No code change for this in slice 1.**
