# S18 §2 — running progress notes

Update after every commit. Kept short. When the slice ships this becomes
the input for `docs/reports/s18-2a.md`. §2b as a standalone slice is dead
— its scope is folded into S19 slice 1 (see `docs/directives/s19-pipeline.md`).

## Sequencing decision (2026-09-28)

Kanna approved splitting §2 into two branches so each PR stays under
CLAUDE.md rule 8 (~400 lines) and each half stands on its own.

- **§2a — backend read-path + backfill** merged to main as one squash commit; the pre-merge branch was `feat/s18-hubspot-pipeline`. Nothing user-visible changed. See `docs/directives/s18-2-checklist.md` for the full scope.
- **§2b — dissolved**. SQS + webhook enqueue, nightly reconcile, Pipeline page rebuild on `/pipeline/deals`, Command Center card swap, SOW picker deal dropdown, SOW board pill, and the outage-UI banner are all requirements of S19 slice 1's Sync + UI sections. Deal picker "Not linked to HubSpot" concept survives verbatim; the SQS + webhook wiring lands under the Sync heading of the directive.

## §2a — landed and shipped

Squash-merge to main + fresh CI deploy from main. Pre-merge branch was `feat/s18-hubspot-pipeline` (see git log for the individual fixup SHAs).

Staging deploy proof (pre-merge, image `s18-2a-ae5fe36` on rev 47):
- Backfill run 1 clean: seen 656 / created 135 (+521 from earlier partial runs) / unchanged 521 / archived 0 / companies_matched 591 / companies_created 65 / owners_matched 656 / owners_unassigned 0 / errors 0.
- Backfill run 2 idempotent: seen 656 / created 0 / updated 0 / unchanged 656 / errors 0.
- Smoke green, gate 0 test-tagged rows.
- Top-5 by amount (Costco Travel × 2, Services SETA, AECI, Capitec Bank Limited) sanity-checked; Costco Travel dates carried into S19 slice 1's verification sample.

## §2a — scope in the merged commit

**Backend read-path + cache**
- Migration `20260928_0040_hubspot_pipeline_cache.py` — adds `opportunity.amount`, `close_date`, `stage_label`, `hubspot_last_seen_at` + index on `(source, archived_at)`. Reversible.
- `opportunity` model gains the four columns.
- `HubSpotClient.list_deals_page()` + stub — paged `/crm/v3/objects/deals`; `get_deal` projection now includes amount + closedate + stage label.
- `services/hubspot_intake._upsert_opportunity` writes the cache; un-archives an opportunity when a new event arrives on a previously archived deal; bumps `hubspot_last_seen_at` every touch.
- `services/hubspot_pipeline.py` — shared query service (`list_pipeline_deals`, `get_pipeline_deal`, `search_pipeline_deals`, `is_hubspot_linked`). HubSpot-sourced + non-archived only. Closed-Lost split into a separate count for the UI tab.
- `routers/pipeline.py` — `GET /pipeline/deals`, `GET /pipeline/deals/{id}`, `GET /pipeline/deals/search`. Registered in `main.py`.

**Backfill**
- `services/hubspot_backfill.py` + `POST /integrations/hubspot/backfill` (SystemAdmin). Paged loop, per-deal transactional upsert, end-of-run archive sweep (skipped on any error — see F8 backend half). Counts: seen / created / updated / unchanged / archived / companies_matched / companies_created / owners_matched / owners_unassigned / errors + `error_deal_ids`.

**Rate-limit + outage handling (§2a — decision + tests)**
- **F7 · HubSpot 429 rate-limit** — landed in §2a. `HubSpotClient._get` retries on 429 with `Retry-After` header (or exponential 1/2/4/8s), max 4 attempts, then re-raises so the caller counts an error. Tests: `test_hubspot_client_retries_on_429` and `test_hubspot_client_gives_up_after_max_retries` in `tests/test_hubspot_backfill.py`.
- **F8 · HubSpot outage — backend half** — landed in §2a. If pagination fails OR any deal errored, `run_backfill` skips the archive sweep so a partial run cannot mass-archive rows we didn't reach. Tests: `test_backfill_skips_archive_sweep_when_a_deal_errored` and `test_backfill_skips_archive_when_pagination_fails`.
- **F8 · HubSpot outage — UI half** — deferred to §2b. Pipeline page renders local cache with a "HubSpot last synced X ago" banner; System health surface shows drift + last_backfill_at / last_webhook_at / last_reconcile_at.

**Tests**
- `tests/test_hubspot_backfill.py` — 9 acceptance tests (full upsert, idempotency, archive-on-missing, unassigned owner + amount=0, no-company sentinel, unarchive-on-return, archive-skip-on-deal-error, archive-skip-on-pagination-error, 429 retry × 2).
- `tests/test_hubspot_readonly.py` — grep-assertion locking `update_deal` to two dormant files (`integrations/hubspot.py`, `services/hubspot_writeback.py`).

**Green:** 814 pass, 6 skipped (all Postgres-gated).

## Checklist status — carried forward

Every checklist line from `docs/directives/s18-2-checklist.md` mapped to the half it lands in and its proof reference.

**§2a — proven in this branch**
- A1 hubspot_deal_id key → uses existing partial-unique index (no change).
- A2 `opportunity.source` filter — `services/hubspot_pipeline._base_query()`.
- A3 cache columns — migration `20260928_0040_hubspot_pipeline_cache.py`.
- A5 live/archived/closed-lost states — `list_pipeline_deals` + `_is_closed_lost`.
- A6 dedupe on `source_event_id` — unchanged.
- B1 `GET /pipeline/deals` — `routers/pipeline.py::list_deals`.
- B2 `GET /pipeline/deals/{id}` — `routers/pipeline.py::get_deal`.
- B3 `GET /pipeline/deals/search` — `routers/pipeline.py::search_deals` (lands as `/pipeline/deals/search`; no separate `/hubspot/deals/search` needed — one router path).
- B6 `POST /integrations/hubspot/backfill` — `routers/hubspot.py::run_hubspot_backfill`.
- B10 read-only guard — `tests/test_hubspot_readonly.py`.
- C1 backfill worker — `services/hubspot_backfill.py::run_backfill` + tests (see above).
- C4 backoff on 429 — `integrations/hubspot._get` + tests.
- C5 owner mapping — reuses `services/hubspot_intake._resolve_owner`; unassigned deals counted by `owners_unassigned`.
- F1 deal with no company — `test_backfill_handles_deal_with_no_company`.
- F2 owner-less deal — `test_backfill_counts_owner_unassigned_and_amount_zero` (assignment task creation follows the intake path; the count is what §2a proves).
- F3 duplicate company names — dedup rule stays on HubSpot company id (unchanged; carried forward to §2b test).
- F4 deleted deal → archive — `test_backfill_archives_deals_missing_from_hubspot`.
- F5 Closed Lost — filter in `list_pipeline_deals`; UI tab is §2b.
- F6 amount 0 / null — `test_backfill_counts_owner_unassigned_and_amount_zero` (0) + `test_backfill_upserts_every_deal` (null tolerated).
- F7 429 — see above.
- F8 backend half — see above.

**§2b — not started, carried forward from the checklist**
- A4 SOW `hubspot_deal_id` linkage via `POST /sow/{opp_id}/link-hubspot`.
- B4 SOW-upload pick request-schema extension.
- B5 webhook receiver → SQS enqueue.
- B7 `GET /integrations/hubspot/backfill/{run_id}` (§2a runs synchronously; async status endpoint waits for prod-scale).
- B8 `GET /integrations/hubspot/health` — feeds System health.
- B9 `POST /sow/{opp_id}/link-hubspot`.
- C2 SQS receiver (replace DB poll in `worker/hubspot_intake.py`).
- C3 nightly reconcile (`worker/hubspot_reconcile.py`) + `integration_health` + `schedulers` module.
- D1 `infra-tf/modules/hubspot/` — SQS main + DLQ, IAM.
- D2 `HUBSPOT_EVENT_QUEUE_URL` env in api task-def.
- D3 EventBridge schedule for reconcile.
- E1 Pipeline page rebuild.
- E2 Command Center pipeline card swap.
- E3 SOW board "Not linked to HubSpot" pill.
- E4 SOW upload picker deal dropdown + auto-suggest.
- E5 System health HubSpot section.
- F3 test — dup-company-name integration test on the SQS webhook path.
- F5 test — Closed-Lost tab count changes on stage transition.
- F8 UI half — "HubSpot last synced X ago" banner + drift on System health.
- F9 SOW picker no-match branch.
- F10 SOW re-link via `POST /sow/{opp_id}/link-hubspot`.
- G1–G5 shared-service completeness re-grep after UI rebuild.
- Playwright: create test deal in HubSpot → appears in DealGate within 2 min → SOW linked to it. Kanna clicks through before merge.

## Grep survey (task #40) — reference for §2b UI work

**Must route through `/pipeline/deals` in §2b:**
- `web/src/pages/v2/Pipeline.tsx:124` — currently `listClients({ size: 200 })`.
- `web/src/pages/v2/CommandCenter.tsx:293-296,308,372,455,546` — currently builds `dealByClient` from `listClients` + `getDeals`.

**Must route through `/pipeline/deals/search` in §2b:**
- `web/src/pages/v2/sow-studio/upload/ClientPickerModal.tsx`.
- `web/src/pages/v2/sow-studio/StepPanels.tsx:40`.

**Gets the "Not linked to HubSpot" pill in §2b:**
- `web/src/pages/v2/SowApprovals.tsx`.

**Stays on `listClients` (client-scoped, by design):**
- `web/src/pages/ClientList.tsx`, `web/src/pages/v2/AgreementsRegister.tsx`, `web/src/ui-v2/GlobalSearch.tsx`.

**Stays as-is (renders `hubspot_deal_id` as a label on rows from other list endpoints, not a Pipeline substitute):**
- `AdminReplay`, `ClientDetail`, `ClientSowGm`, `RenewalBoard`, `RenewalsV2`, dashboards (`CEODashboard`, `FinanceDashboard`, `SalesDashboard`), reports (`MarginReport`, `RenewalsReport`), `SystemHealthSection`.

## Decisions made this session

- Backfill and single-deal intake converge on `_upsert_opportunity` so idempotency is proven once.
- HubSpot amount / close_date / stage_label cached on `opportunity` so Pipeline queries do not fan out to HubSpot per row.
- Client resolver dedupes on HubSpot company id; duplicate names produce distinct clients (F3).
- "Not linked to HubSpot" SOWs live only on the SOW board — never as Pipeline rows (E3 + E4).
- `HubSpotClient.update_deal` stays on disk but unrouted; grep test enforces that (B10).
- Deals archived in HubSpot re-open when a new event arrives (intake un-archives + audits `archived_at → null`).
- 429 handling and backend-side outage tolerance land in §2a with tests, because the backfill is the first thing that will hit them.
- The UI-side outage banner + drift surface land in §2b alongside the Pipeline rebuild — pointless to add UI copy for a page still reading `listClients`.

## Failures / blockers

None. TypeError on SQLite naive-vs-aware datetime hit once in the backfill company-created heuristic — normalized to UTC before subtracting. Archive-sweep test needed a `monkeypatch` of `_process_deal` rather than trying to force a domain-level failure.
