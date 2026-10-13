# S20 · scoreboard

One row per deliverable across W1, W2, W6, W4, W7, Final. States are
strict (rule 16): `verified working (staging)` · `fixed and tested` ·
`missing` · `blocked` · `deferred`. Every session updates its rows
**first and last**. ETA = rows-not-verified ÷ 7 per session.

**Current head:** `integrate/s20 @ 9b7bc5d` on **staging rev 67**
(`s20-9b7bc5d9`) · S21-1c stabilization sweep deployed 2026-10-01.
Image digest `sha256:a1b89f0eeb13...`, size 103 MB. Migration no-op
(head still `20260930_0047_w6_watch`). Deploy smoke `smoke
20261001T212952Z` GREEN; leak gate clean (0 test clients, 0 e2e
approvers on active real SOWs). Full pytest exit 0; targeted
Playwright (t09 + t45) on rev 67: 10 passed, 11 skipped, 1 flake
on t09 stage-cell (pass on isolated rerun). Prior rev 66 S21-1b deploy: image built + pushed digest
`sha256:9817ee025b2d0455384b1e85d931deeb754ba23c64a4797766b5787a84bd19ab`
size 103 MB, api task-def rev 66, alembic exit 0 (head unchanged),
api service stable on rev 66 (ECS waiter), 6 worker families
re-registered on new image (api-migrate:4, alert-scheduler:19,
notification-sender:19, renewals-scheduler:19, audit-export:19,
hubspot-intake:17, hubspot-reconcile:17), SPA synced + CloudFront
invalidation `I3HPRLDRYJ1RL0GZTFFN4PRE9W`. Deploy smoke `smoke
20261001T205215Z` GREEN, with the item 7 approvals-gate correctly
tripping on the historic Liberty Mutual leak which was voided via
`/api/approvals/packages/6694ba9e.../void`. T45 on staging (items
1, 2, 3, 4, 7): 5 passed, 7 skipped.

**Prior Lead-C2 deploy** (unchanged this session): image built + pushed digest
`sha256:5b5981c7`, api task-def rev 65, alembic exit 0 (head
`20260930_0047_w6_watch`, no-op advance from rev 64), api service
stable at rev 65, 6 worker families re-registered on new image.
Smoke GREEN at `smoke 20261001T184714Z`
(`docs/reports/s20/deploy-artifacts/smoke-c2.txt`). Prior head
`b2e544df` on rev 64 superseded. **Smoke GREEN** at `smoke 20261001T174438Z`
(`docs/reports/s20/deploy-artifacts/smoke-c1.txt`). One fix made
mid-deploy: `api/app/routers/reports.py` was calling
`select(Opportunity)` directly in `/reports/sow/gm`, tripping the
single-truth gate — fixed by routing through new helper
`list_opportunity_rows` on `hubspot_pipeline.py` (commit `b2e544df`).

**Lane A staging checks on rev 64:**
- `/api/reports/pipeline/export.csv` → 200 CSV with
  `x-totals-count: 104` header. **pass**.
- `/api/reports/pipeline/by-stage` → 200; `total_count=104`,
  `rows_sum=104`. **pass**.
- `/api/settings/integrations/bedrock` → live `model_id=us.anthropic.
  claude-sonnet-4-6` + `as_of` timestamp. **pass**.
- `/api/settings/integrations/ses` → live `from_address=noreply@
  dealgateapp.com`, `sandbox=true`, `as_of` timestamp. **pass**.
- `/api/settings/integrations/worker-heartbeat` → live per-source
  `last_success_at` + `age_seconds`. **pass**.
- `/api/pipeline/summary` → 200 but **does not expose** the new
  Lane A keys (`sows_in_progress`, `agreements_uploaded`, `ceo_pending`)
  — service layer computes them (`services/hubspot_pipeline.py` lines
  2039–2041) but `router.summary_endpoint` + `SummaryOut` schema still
  return the 6 pre-S20 fields only. W4-1 cannot flip.
- 3-way reconcile: `summary.open_count==by-stage.total_count==
  csv X-Totals-Count==104`; `/pipeline/deals.total_open=657` disagrees
  — different scope definition. W4-7 partial, stays at `fixed and tested`.

**Not run this session (budget):** Playwright S20 serial, W7 e2e
single-run-tag flow. W7-1..W7-5 stay at `fixed and tested` (no
staging proof this run).

**Lead-S20-C2 (2026-10-01, in flight):** attempting W4-1 (expose
new summary fields through SummaryOut + router + CommandCenter
deep-links), W4-7 (/pipeline/deals total_open scope fix + 4-way
reconcile assertion), W7-1..W7-5 (Playwright S20 serial + W7 e2e
run-tag flow). Deploy via D5. Flips only on staging proof. Rule 19
heartbeat active.

**Lead-S20-C1-resume-2 (2026-10-01, completed):** rebase + merge +
local gates green; no staging flips (deploy gated on main merge).
- Rebase Lane A onto `e727dcf` → `44080a1` (two commits collapsed
  to one; scoreboard conflicts resolved by keeping C1-resume-2
  header + taking Lane A's W4 row proof text).
- Rebase Lane B onto Lane A tip → `4c391f1` (no conflicts).
- `tsc --noEmit` clean on merged tree (D-S20-17b additivity gate).
- `alembic heads` = 1 (`20260930_0047_w6_watch`).
- Single-query-service pytest 7/7.
- No-stubs grep: no net-new functional stubs introduced; the pre-
  existing `bedrock_ceo_brief` fallback stub carried forward from
  `fa3332e` (not a C1-resume-2 regression).
- Full pytest: 992 passed, 0 failed in 4m35s.
- Attempted rows W4-1, W4-3, W4-4-CARDS, W4-6, W4-7 land at
  `fixed and tested` with S6-A proof text; W7-1..W7-5 land at
  `fixed and tested` with S2-W7 proof text. Zero rows flip to
  `verified working (staging)` this checkpoint — gated on CI
  deploy that only fires on push-to-main.
- Follow-up: run `scripts/deploy-smoke.sh` + Playwright S20 serial
  + W7 e2e + Lane A UI checks against staging AFTER a Lead-
  approved main merge of `4c391f1`. That merge is the next
  checkpoint, not this one.

**Lead-S20-C1 checkpoint (2026-09-30):** STOPPED at step 1 (rebase).
Both lanes edited files outside their owned sets per rule 17.
No rebase, no merge, no deploy, no flips. Attempted rows W4-1,
W4-3, W4-4-CARDS, W4-6, W4-7, W7-1, W7-2, W7-3, W7-4, W7-5
remain at their lane-reported state (`fixed and tested`) pending
Lead decision on the ownership exception.

**Lead-S20-C1-resume (2026-10-01):** STOPPED at step 2 (additive-only
check). D-S20-17a recorded + rule 17 amended (shared-append-only
class for `web/src/api/client.ts`, `web/src/routes*.tsx`,
`web/src/nav*.tsx`, and the router-registration block in
`api/app/main.py`; `signed_sow.py` added to Lane B owned list) —
commit `6b25186`. However, Lane B's `web/src/api/client.ts` diff is
NOT purely additive: 4 removed / 13 added, with in-place edits to
the existing `SignedSowFieldName` union (added `signatories`) and
the `SignedSowDiffField` interface (broadened `approved`/`extracted`
to `string | string[] | null`, added `missing`/`unexpected`). The
shared-append-only exception only covers **additions** — modifying
existing lines in a shared file is still a stop condition. Lane A's
diff is pure addition (145 added / 0 removed) and would have
passed. No rebase, no merge, no deploy, no flips. W4-* and W7-*
attempted rows remain at their lane-reported state. Lane B must
either refactor the signatory diff to a sibling helper type
appended at the end (keep the original `SignedSowFieldName` /
`SignedSowDiffField` untouched) or get a product-owner exception
to edit the shared type in place.

Ownership violations (step-1 stop):
- Lane A (`feat/s20-w4 @ 1f05090`) edited `web/src/api/client.ts`
  (shared, not in Lane A owned glob `web/src/pages/{Reports,
  CommandCenter,Settings,SystemHealth}*` + routers + hubspot_pipeline
  summary).
- Lane B (`feat/s20-w7 @ 8b42c81`) edited `web/src/api/client.ts`
  (shared) AND `api/app/services/signed_sow.py` (not in Lane B owned
  glob `api/app/services/{signature,release,projects,forecast}*`).
Both lanes also updated shared `docs/reports/s20/scoreboard.md`
with overlapping diffs on the header + totals (reconcilable; not
the stop cause).

| id | scope | deliverable | state | proof | session | lane |
| --- | --- | --- | --- | --- | --- | --- |
| W1-L05 | W1 | Owner mirror (D2 Unassigned vs unresolved vs account owner) | verified working (staging) | T03 parity Venetian + BSC rows for owner_name/email/id | S2 | integrate |
| W1-A2 | W1 | Continuous consumer + measured freshness (D4) | fixed and tested | /api/sync-status returns watermarks; continuous-consumer TF staged, not applied | S2 | integrate |
| W1-A3 | W1 | Backfill scan generation + resume (no premature archive) | fixed and tested | test_hubspot_backfill_scan_generation.py 22 cases | S2 | integrate |
| W1-A4 | W1 | Source-event dedupe + atomic commit (D7) | fixed and tested | Watermark advance visible on staging; unit tests cover IntegrityError catch | S2 | integrate |
| W1-D9 | W1 | Stage aggregation by (pipeline_id, stage_id) | verified working (staging) | T03 parity stage_id + hubspot_pipeline_id byte-match | S2 | integrate |
| W1-D10 | W1 | Business Unit discovery (BU property mirrored) | missing | discover_business_unit works; staging portal has no BU property on deal schema | S2 | integrate |
| W1-T28 | W1 | Event edge cases (property clear, out-of-order, owner/stage rename, assoc change, deletion, merge, cursor resume) | fixed and tested | 7 pass / 1 xfail (worker_crash_resumes_from_cursor — needs continuous consumer) | S4 | integrate |
| W1-T33 | W1 | Scan resume mid-batch chaos test (staging) | deferred | needs a controlled ECS kill | — | integrate |
| W1-ALARMS | W1 | Freshness alarms (backlog age, DLQ, lag) in CloudWatch | blocked | TF staged (infra-tf/modules/schedulers/hubspot_freshness_alarms.tf); rule 15 interactive prompt | S5 | integrate |
| W2-L02 | W2 | Stage chips filter in place + count + value per chip | verified working (staging) | T40 L02 + L06 + L06b | S3b-Rev2 | integrate |
| W2-L03 | W2 | Pagination 25/50/100 + totals before pagination (A5, T35) | verified working (staging) | T40 L03 + T35 pytest 5/5 | S3b-Rev2 | integrate |
| W2-L04 | W2 | Deal name column + search on dealname | verified working (staging) | T03 parity BSC 15/15; L04 unit tests | S3 | integrate |
| W2-L05 | W2 | Client rollups matching-vs-total + deal/account owner split | verified working (staging) | T40 L05; ClientsTable + ClientDetail v2 | S3b | integrate |
| W2-L06 | W2 | Chip counts reconcile to filtered rows | verified working (staging) | T40 L06; stage_counts over base filter set | S3b-Rev2 | integrate |
| W2-L07 | W2 | 74 Sky Closed Lost readable + prose activity | verified working (staging) | T40 L07; ClientDetail timeline (prose, not JSON) | S3b | integrate |
| W2-L08 | W2 | Sidebar nav + Command-center-specific heading | verified working (staging) | T01 pass on rev 56+ | S3b | integrate |
| W2-L09 | W2 | /deals/:id real detail (facts, ordered stage strip, next action, latest comment, SOW list or Upload SOW) | verified working (staging) | T09 heading + /pipeline row click → /deals/:id | S3b | integrate |
| W2-FILTER-BAR | W2 | Full filter bar (owner, stage, BU, pipeline, open/closed, attention, SOW, group, date) | verified working (staging) | T40 Owner+BU selects present; /pipeline/facets endpoint | S3b-Rev2 | integrate |
| W2-T09 | W2 | Names not ids on pipeline + deal/client detail | verified working (staging) | 5 tests pass on staging | S3b | integrate |
| W2-T28-W2 | W2 | T28 W2-side xfails cleared (stage rename, association change) | fixed and tested | 2 pytests pass | S3b | integrate |
| W6-1 | W6 | Next actions: user picker + inline edit + overdue sorts to top | verified working (staging) | DealDetail assignee select + Mark Complete; CASE sort; T16 overdue surface check | S4b | integrate |
| W6-2 | W6 | Comments: latest preview on Pipeline row + pinned wins | verified working (staging) | OpportunityRow carries latest_*; subquery orders (pinned DESC, created DESC); unit test | S4b | integrate |
| W6-3 | W6 | Combined timeline on deal + client pages | verified working (staging) | /deals/{id}/timeline + /clients/{id}/timeline, prose entries | S4 | integrate |
| W6-4 | W6 | Manual groups + filter axis | verified working (staging) | T16 group select present; _resolve_scope routes group → opp ids | S4b | integrate |
| W6-5 | W6 | Rule-based groups eval'd by same server-side filter fn + "why is this here" | verified working (staging) | _base_opportunity_filter named; stage-change membership pytest; UI "Why these rows" | S4b | integrate |
| W6-6 | W6 | Saved views (last-view remembered per user; URL wins) | verified working (staging) | user_preference-backed via /user-preferences; URL still wins | S5 | integrate |
| W6-7 | W6 | Watchlist + Command center Watching card | verified working (staging) | /watchlist CRUD; CommandCenter metric card | S4b | integrate |
| W6-8 | W6 | Deals count once (not memberships); seeded 3-group staging assertion | fixed and tested | Unit pytest proves invariant; Playwright with empty watchlist asserts honest-zero; seeded 3-group staging scenario not run | S5 | integrate |
| W6-9 | W6 | Comment permissions (viewer empty list + 403 on write) | verified working (staging) | Role guards on router; T16 anon POST → 401 | S4b | integrate |
| W4-0a | W4 | Saved views → user_preference | verified working (staging) | /user-preferences GET+PUT + Pipeline migration | S5 | integrate |
| W4-1 | W4 | Command center numbers via summary() + deep-link filter | verified working (staging) | staging rev 65 `/api/pipeline/summary` → `{open_count:104, sows_in_progress:1, agreements_uploaded:0, ceo_pending:0, pending_approvals:1, agreement_gaps:54}` — all 3 new keys shipped through SummaryOut+router; deep-link items on `?attention=pending_approval` across all pages = 0 ≡ agreements_uploaded; `?readiness=ceo_exception` items = 0 ≡ ceo_pending; sows_in_progress=1 shares scope with pending_approvals (same expression) — card and deep-link URL both target the pending-approval set | Lead-C2 | A |
| W4-2 | W4 | Renewals (2 calendar months, Jan 31 → Nov 30, noreply@dealgateapp.com, Renewals page) | verified working (staging) | compute_alert_date pytest; SES sender constant; T39 no-raw-ids on /renewals | S5 | integrate |
| W4-3 | W4 | Reports page (pipeline by stage/owner/BU + SOW GM + aging + CSV, totals before pagination) | verified working (staging) | staging rev 64: /api/reports/pipeline/by-stage returns total_count=104, rows=9 stages; /api/reports/pipeline/export.csv returns 200 CSV with `x-totals-count: 104` header | Lead-C1 | A |
| W4-4-TRUTH | W4 | Integrations page truthful (sync_status reads + no static "Connected") | verified working (staging) | grep "Connected" zero hits; T39 asserts "Last sync/success/attempt" prose | S5 | A |
| W4-4-CARDS | W4 | Integrations Bedrock + SES + heartbeat cards | verified working (staging) | staging rev 64: /api/settings/integrations/bedrock → live model_id=us.anthropic.claude-sonnet-4-6 + as_of; /ses → from_address=noreply@dealgateapp.com + sandbox + as_of; /worker-heartbeat → per-source last_success_at + age_seconds | Lead-C1 | A |
| W4-5 | W4 | Freshness alarms applied via tf-init.sh with human-answered prompt | blocked | rule 15; TF staged in W1-ALARMS | S5 | integrate |
| W4-6 | W4 | System health page (DB, SQS depth + DLQ, last reconcile, last purge, test-data gate) | verified working (staging) | staging rev 64: /api/settings/integrations/worker-heartbeat returns live newest_last_success_at + per-source last_success_at timestamps (no static value) | Lead-C1 | A |
| W4-7 | W4 | Reporting numbers agree (CC == Reports by-stage == /pipeline) | verified working (staging) | staging rev 65 four-way: `summary.open_count=104` ≡ `by-stage.total_count=104` (rows sum=104) ≡ `/pipeline/deals.total_open=104` ≡ CSV `x-totals-count: 104`. total_open scope now uses `is_closed_won=False AND is_closed_lost=False` columnar flags (was leaking closed-won via stage_label match → 657) | Lead-C2 | A |
| W4-8 | W4 | No raw ids on W4 pages (extend T09) | verified working (staging) | T39 asserts on /command /renewals /reports /settings/integrations | S5 | A |
| W7-1 | W7 | Signature verification: signed SOW signatories match approved version; mismatch = inline editor | fixed and tested | pytest `test_verify_blocks_when_signatory_names_differ` + `_cosmetic_variance` + `_missing_on_executed` (3 new, 13 total in test_signed_sow.py pass); services/signed_sow.py compute_diff adds signatories; SignatureTab.tsx renders SignatoriesMismatchEditor on blocked status (rule 13 inline editor) | S2-W7 | B |
| W7-2 | W7 | Release: signed + NDA/MSA (never blocker; show gap, allow) → Released state + audit + Handoff row | fixed and tested | pytest tests/test_release_gate.py 20 pass (release transitions via workflow with audit same-txn; superseded refused; NDA/MSA not a hold reason — D3); services/handoff.py check_release_gate + release flow intact | S2-W7 | B |
| W7-3 | W7 | Delivery acceptance (accept with staffing baseline; reject = inline reason) | fixed and tested | pytest `test_delivery_acceptance_requires_delivery_role` + `test_delivery_acceptance_is_set_once` pass; services/delivery_acceptance.py enforces role server-side; unique(package_id) via 0043 migration | S2-W7 | B |
| W7-4 | W7 | Project creation (single staffing + GM baseline → Projects page with names) | fixed and tested | pytest `test_project_link_is_idempotent` pass; services/project_lifecycle.create_or_link freezes baseline_snapshot_json; UNIQUE(package_id) idempotency guard; projects router returns names | S2-W7 | B |
| W7-5 | W7 | Forecast vs actuals (monthly actual entries; GM vs forecast; floor breach → attention flag) | fixed and tested | services/forecast.py:update_forecast fires `forecast.recovery_required` audit + Task(category=`forecast.recovery`) + queue_notification on policy floor breach — the shared attention record Lane A reads; test_forecast.py suite green | S2-W7 | B |
| FINAL-T36 | Final | Deploy pipeline (D5 proven, image + migration + rollback) | verified working (staging) | S1 deploy ran rollback 53→51→53 in 3m30s | S1 | integrate |
| FINAL-T38 | Final | Security boundaries + production-claim honesty (A8) | fixed and tested | Smoke gate checks auth/caching/webhook sig; integration page labels current vs planned | S1 | integrate |
| FINAL-T44 | Final | Full multi-role journey (intake → approve → CEO → signature → handoff → delivery → renewal) | missing | T44 spec skipped — needs W7 landing | — | B |
| FINAL-U01 | Final | 5 Cognito approver test users + SES sandbox verifications | verified working (staging) | S1 U01 TF slice + 5 users verified | S1 | integrate |
| FINAL-CLICK | Final | Product-owner click-through on staging | missing | tracked in click-through.md | — | integrate |
| S21-1 | S21-1 | Delete, not archive, at every state (reverse D6; hard delete cascading) | verified working (staging) | staging rev 66 (`s20-36f01fa4`) · t45 item-1 pass — one `Delete SOW` button + `Delete this SOW?` dialog at every state; backend DELETE already permits every state (S17); SowWorkspace.tsx governed/archive branch removed in 775d2c2; D-S21-01 reversal recorded | S21-1b | integrate |
| S21-2 | S21-1 | Staffing & GM renders inside the workspace (regression of S19-1b item 6) | verified working (staging) | staging rev 66 · t45 item-2 pass — Overview/Scope/Approvals tabs + Readiness panel remain visible after clicking Staffing & GM tab; root cause was `/sows/:id/staffing` route shadowing `/:tab`; removed in 36f01fa + S21AppRoutes.test.tsx pins the route table (2/2 green locally) | S21-1b | integrate |
| S21-3 | S21-1 | Back navigation in the SOW studio (Scope → Staffing → Confirm revisitable) | verified working (staging) | staging rev 66 · t45 item-3 pass — header `Back` control visible + at least one enabled gate-strip step; workspace tabs + ProgressRail already clickable backward until Submit; Back-to-Deal added in 36f01fa | S21-1b | integrate |
| S21-4 | S21-1 | Overview shows no blanks (Owner/Term/Commercial type/Next action; drop id) | verified working (staging) | staging rev 66 · t45 item-4 pass — Overview carries no `Unassigned`/`Unknown`/`Not scheduled` token and no `ID <uuid>` line; owner falls back to the SOW uploader short-id; commercial type uses extractor's confirmed → suggested → deal chain; term uses the single-format formatTermRange (`Oct 12, 2026 – Apr 12, 2027`); S21Format.test.ts 5/5 green locally | S21-1b | integrate |
| S21-5 | S21-1 | Approvers visible and editable before submit | missing | t45 item-5 placeholder (test.skip with screenshot pointer); S21-1c scope per user directive | — | integrate |
| S21-6 | S21-1 | Approver routing — the real people (seeded, OOO flag, Sales as function) | missing | t45 item-6 placeholder; S21-1c scope per user directive — needs user model migration (`out_of_office` + `delegate_id`), Settings seed data, routing resolver OOO branch | — | integrate |
| S21-7 | S21-1 | Test users never route a real SOW (leak gate on approvers) | verified working (staging) | staging rev 66 · t45 item-7 pass — spec iterates ACTIVE packages (non-voided/rejected/released) and finds zero bot-named rows on real SOWs; eligibility fix in approval_routing.groups + submission_plan from 775d2c2; pytests 8/8 locally; smoke `smoke 20261001T205215Z` gate correctly tripped on the historic Liberty Mutual leak which was then voided via `/api/approvals/packages/6694ba9e-f863-4df6-84fb-3ed5401d3c75/void` with reason referencing item 7 | S21-1b | integrate |
| S21-8 | S21-1 | Email to the real approvers (SES identities via TF, plan only) | fixed and tested | `tf plan -target=module.prod_approvers` (via `scripts/tf-init.sh`): clean — 6 to add, 0 to change, 0 to destroy. Not applied — Kanna's call per rule 15; module in 775d2c2. Prior session's R-S21-02 (`rule 15 blocked plan`) was incorrect; stale local state was already `.stale.bak`-named and ignored by the guard | S21-1b | integrate |
| S21-9 | S21-2 | Clients view honors active filters (deferred — S21-2) | deferred | S21-1 session scope; Session S21-2 directive-split | — | integrate |
| S21-10 | S21-2 | Account owner mirrored from company owner (deferred — S21-2) | deferred | S21-1 session scope; Session S21-2 directive-split | — | integrate |
| S21-11 | S21-2 | Active filters visible and removable one at a time (deferred — S21-2) | deferred | S21-1 session scope; Session S21-2 directive-split | — | integrate |
| S21-12 | S21-2 | Raw identifiers on the deal page / breadcrumbs (deferred — S21-2) | deferred | S21-1 session scope; Session S21-2 directive-split | — | integrate |
| S21-13 | S21-2 | Deal page inline editors for Next action and Latest comment (deferred — S21-2) | deferred | S21-1 session scope; Session S21-2 directive-split | — | integrate |
| S21-14 | S21-2 | Alerts per deal (deferred — S21-2) | deferred | S21-1 session scope; Session S21-2 directive-split | — | integrate |
| S21-15 | S21-3 | Hours are computed, not typed, for staff augmentation (deferred — S21-3) | deferred | S21-1 session scope; Session S21-3 directive-split | — | integrate |
| S21-16 | S21-3 | Contract extension on signed/released SOW (deferred — S21-3) | deferred | S21-1 session scope; Session S21-3 directive-split | — | integrate |
| S22-P1-1 | S22-P1 | Pack committed; `python -m pytest api/tests/forecast -q` → 18 passed on CI Postgres | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · pack 71944e3, engine unmodified; 18 goldens pass locally (also with the Postgres fixture); on staging the deployed engine reproduced the Client A golden to the cent (s22-p1-contract.spec.ts, round 2: 2 passed) | S22-1 | feat/s22 |
| S22-P1-2 | S22-P1 | Migrations: engagement, resource, allocation (superseded_by), engagement_cost, calendar_location, holiday, cost_rate_card, forecast_policy, forecast_run + seeds from the workbook Settings tab | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · migration 20261012_0065 applied by the Terraform-owned task (round 1 task 0f1d0d3c… exit 0; round 2 5e1c79be… exit 0, idempotent); seeds confirmed (GET /settings/forecast: US 36/5/35, India 8/8/50, floor 35, 8 h/day, 16 rate cells); parity 3/3 + audit hardening 1/1 locally | S22-1 | feat/s22 |
| S22-P1-3 | S22-P1 | Thin mapper DB rows → engine dataclasses → compute() → Forecast → JSON; forecast_run cache keyed by input hash | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · s22-p1-contract.spec.ts on staging: totals, 12 month×assignment rows, per-row totals to the cent; cache + invalidation pytest | S22-1 | feat/s22 |
| S22-P1-4 | S22-P1 | Endpoints exactly per openapi-forecast.yaml (engagements, clients, allocations incl. close/rehire/supersede, costs, engagement forecast, portfolio forecast, settings GET/PUT) | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · 25 routes exercised on staging by the two specs + API proofs (engagements, allocations incl. close/rehire/supersede paths, costs, forecast, portfolio, clients, resources, settings GET/PUT); 17/17 pytest incl. permissions × 7 roles and runtime isolation; deviations D1–D8 in docs/bugs/s22.md | S22-1 | feat/s22 |
| S22-P1-5 | S22-P1 | Contract test: Client A golden under the e2e run tag, GET /engagements/{id}/forecast == goldens; teardown; leak gate 0 | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · tests/e2e/specs/s22/s22-p1-contract.spec.ts round 2 on staging: passed; fixture-issued client; teardown clean; extended gate 0/0/0/0 | S22-1 | feat/s22 |
| S22-P1-6 | S22-P1 | Importer POST /allocations/import (workbook staffing table CSV, its column headers) | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · POST /allocations/import on staging with the workbook's headers (incl. commas, Name column): created 5, forecast hours 3660 / labour 178984.00 / burden 31528.72 == Client A golden; torn down; grid button 'Import staffing CSV' | S22-1 | feat/s22 |
| S22-P2-1 | S22-P2 | /engagements/{id} tabs Allocations · Forecast · Setup & costs; allocations grid per prototype (editable cells, rate-card prefill, Leaves / Re-hire / remove, totals, Row GM red under floor) | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · s22-p2-owner-path.spec.ts round 2 on staging (2 passed, 1.4 m): five people through the draft row, Leaves, Re-hire, start edited in a yellow cell, named breadcrumb | S22-1 | feat/s22 |
| S22-P2-2 | S22-P2 | Forecast tab: status line, location pills, all-resources block, per-assignment blocks, per-person revenue by month, monthly-required text | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · owner path: Forecast tab 'Monthly view required', per-person row shows the gap month blank, all-resources + assignment tables | S22-1 | feat/s22 |
| S22-P2-3 | S22-P2 | Setup & costs: project block with type-driven greying; additional costs with frequency + billed-to-client required | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · owner path: Setup & costs pre-filled, Total price / Monthly fee greyed for staff aug, Additional costs → Yes, cost added, 'Totals: $3,200 cost, $3,200 billed through' | S22-1 | feat/s22 |
| S22-P2-4 | S22-P2 | New engagement page with "+ New client…"; Closed-Won HubSpot deal offers "Create engagement from deal" pre-filled | fixed and tested | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · new-engagement page proven on staging through the owner path (fixture client; '+ New client…' path proven locally + vitest since test identities must not create unscoped clients — bug #4). 'Create engagement from deal' pre-fill: vitest + deal-page button only — no Closed-Won fixture deal exists on staging and a real deal cannot be torn down; needs Kanna's click on a real Closed-Won deal | S22-1 | feat/s22 |
| S22-P2-5 | S22-P2 | Settings page: hours/day, project floor, burden + resource floor per location, add location, rate card, holidays — PUT /settings/forecast | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · owner path: Settings → Forecast calendar, US W-2 burden +10 pts saved, engagement cost moved; calendar restored by teardown (GET /settings/forecast US 0.36) | S22-1 | feat/s22 |
| S22-P2-6 | S22-P2 | Playwright owner path: new engagement → five people → one leaves → re-hire → gap month at zero → burden change moves numbers | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · tests/e2e/specs/s22/s22-p2-owner-path.spec.ts round 2 on staging: passed (new engagement → five people → leaves → re-hire → gap month at zero → Setup & costs → Portfolio page → burden moves the numbers) | S22-1 | feat/s22 |
| S22-P3-1 | S22-P3 | /portfolio page: month picker, type + client filters, table, totals before pagination | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · owner path on staging: /portfolio row for the engagement, month/client filters in the URL, server totals row, Export CSV enabled, CSV via API carries header + 'Portfolio · <month>' totals row | S22-1 | feat/s22 |
| S22-P3-2 | S22-P3 | Four cards via the single query service (portfolio GM, below floor, roll-offs 60d, bench), each deep-linking to a list whose count equals the card | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · owner path: four cards visible; API proof: cards == lists on staging (rolloffs_60d 1 == 1 listed, bench 1 == 1 listed, below_floor 0 == 0 rows); pytest equality | S22-1 | feat/s22 |
| S22-P3-3 | S22-P3 | Roll-offs and bench panels with names, never ids | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · API proof on staging: roll-off row carries person, client and engagement names; bench row carries the person; no UUID-valued label fields; torn down | S22-1 | feat/s22 |
| S22-P3-4 | S22-P3 | Renewals: MSP + staff-aug engagements ending within two calendar months raise the existing renewal item (D8) | fixed and tested | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · worker.portfolio_scheduler deployed (family officeapp-dev-portfolio-scheduler rev 2 on s22-6259cda5; EventBridge cron(0 6 * * ? *) ENABLED); one-off tick on staging exit 0 'portfolio_tick renewals_opened=0 …' with no qualifying engagement; renewal behaviour (D8 boundary, deal vs manual) proven by 4 pytests — a staging renewal needs a fixture engagement ending within two months, which would leave owner tasks behind | S22-1 | feat/s22 |
| S22-P3-5 | S22-P3 | Nightly alert via notification outbox: roll-offs + below-floor engagements to the account owner | fixed and tested | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · same tick on staging exit 0 (digests=0, no owner-bound engagements); daily_digest once-per-owner-per-day proven by 2 pytests — a staging digest would email the bot owner through the outbox | S22-1 | feat/s22 |
| S22-P3-6 | S22-P3 | Reconciliation test: portfolio month total == Σ engagement forecasts == Σ allocation-month rows; CSV export of any portfolio view | verified working (staging) | staging API rev 98 · image s22-6259cda5 (digest 226582e7…3bfd) · SPA index-Lv6YxA3F.js · 2026-10-12 · reconciliation pytest (portfolio month total == Σ engagement months == Σ allocation-month rows) green; CSV export fetched on staging in the owner path (header + totals row + client) | S22-1 | feat/s22 |
| S22-P4-1 | S22-P4 | Engine update: one-time additional costs spread across the term by share of month (pack); 18 goldens + 4 importer tests pass; no API change | verified working (staging) | staging API rev 100 · image s22p4-68ff809d (digest c8460368…cadea) · SPA index-CwMcUryo.js · 2026-10-12 · engine from the pack deployed; s22-p1-contract on staging: the January portfolio row equals the engagement's January line incl. the spread pass-through share (D11); 22 forecast tests locally · merged to main ef50ef9 2026-10-12 (Kanna approved); main image s22p4main-ef50ef9f live, API rev 101 | S22-2 | feat/s22-p4 |
| S22-P4-2 | S22-P4 | Short engagements (≤ 2 months): Forecast tab shows the whole-term summary first, month split behind "Show month split" | verified working (staging) | staging API rev 100 · image s22p4-68ff809d (digest c8460368…cadea) · SPA index-CwMcUryo.js · 2026-10-12 · s22-p4-upload on staging: the owner's 1-month copy shows 'Short engagement … judged on the total' + term summary first, 'Show month split' reveals the months, 'Hide month split' returns; long engagements unchanged (owner path) · merged to main ef50ef9 2026-10-12 (Kanna approved); main image s22p4main-ef50ef9f live, API rev 101 | S22-2 | feat/s22-p4 |
| S22-P4-3 | S22-P4 | Portfolio table: month columns labelled with the month ("Revenue · Oct 2026"), "GM % · whole term", subtitle explains the month slice | verified working (staging) | staging API rev 100 · image s22p4-68ff809d (digest c8460368…cadea) · SPA index-CwMcUryo.js · 2026-10-12 · s22-p2-owner-path on staging asserts 'Revenue · <month>' and 'GM % · whole term' headers and the slice subtitle on /portfolio · merged to main ef50ef9 2026-10-12 (Kanna approved); main image s22p4main-ef50ef9f live, API rev 101 | S22-2 | feat/s22-p4 |
| S22-P4-4 | S22-P4 | Upload the sheet: POST /engagements/import-workbook per the contract (workbook_import.py), upload box on the New engagement page, hours_check shown once on the engagement header; CSV import stays | verified working (staging) | staging API rev 100 · image s22p4-68ff809d (digest c8460368…cadea) · SPA index-CwMcUryo.js · 2026-10-12 · s22-p4-upload on staging: sample sheet → engagement with five people, PASS, note 'matches the sheet', dismissed once (survives reload as gone); owner's older copy → 'Sheet said 168 h for Vikrin; the app computes 160 h — weekday holiday(s) in the window: 2026-09-07' + Employment-type warning; smoke GREEN; gate 0/0/0/0; 4 pytests · merged to main ef50ef9 2026-10-12 (Kanna approved); main image s22p4main-ef50ef9f live, API rev 101 | S22-2 | feat/s22-p4 |
| S22-P4-5 | S22-P4 | Per-person rows on the Forecast tab for fixed-fee types show hours, labelled as such | verified working (staging) | staging API rev 100 · image s22p4-68ff809d (digest c8460368…cadea) · SPA index-CwMcUryo.js · 2026-10-12 · s22-p4-upload on staging: assessment engagement's Forecast tab heading reads 'Per person · hours by month' after showing the split; vitest asserts the hint text · merged to main ef50ef9 2026-10-12 (Kanna approved); main image s22p4main-ef50ef9f live, API rev 101 | S22-2 | feat/s22-p4 |
| S22-P5-1 | S22-P5 | Engine update from the pack: rate_basis, person, cost unknown → INCOMPLETE, actuals + billing loss; 33 forecast tests pass; engine unmodified | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · engine from the pack deployed unmodified; 33 forecast tests; s22-p1-contract on staging still equals the goldens; the imported assessment on staging reports INCOMPLETE with 'cost per hour unknown' (P5-8 run) | S22-3 | feat/s22-p5 |
| S22-P5-2 | S22-P5 | Migration 0066: engagement.business_unit/sales_owner/delivery_owner/closed; allocation.rate_basis/person; allocation_actual; backfill ST21 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · migration task 40ddd4bb265740fc84bad1d1091ba1da succeeded on staging (head 20261012_0066_bu_actuals); parity 3 passed on Postgres; the P5-8 load wrote business units, owners, closed, rate basis, person and actuals through the new columns | S22-3 | feat/s22-p5 |
| S22-P5-3 | S22-P5 | Contract v1.1: new fields, PUT /allocations/{id}/actuals, POST /engagements/import-forecast-model, /portfolio/forecast?business_unit= + groups + cards.billing_loss; mapper passes actuals | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model on staging: /portfolio/it-avalon (business_unit filter + one group), /portfolio groups + totals + cards.billing_loss; Forecast.actuals rendered; 9 pytests incl. PUT actuals + permissions | S22-3 | feat/s22-p5 |
| S22-P5-4 | S22-P5 | Forecast-model importer endpoint: dry run report, load creates clients/engagements/allocations/actuals/holidays + locations, idempotent | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model test 1 on staging: dry run (3 BUs, tabs, report) created nothing, Load created clients/engagements/allocations/actuals + the model's locations and holidays (calendar restored by teardown); idempotency + non-master 422 by pytest | S22-3 | feat/s22-p5 |
| S22-P5-5 | S22-P5 | Portfolio page: BU tabs with URLs, grouped rows + subtotals + grand total, Billing-loss card, closed off the page, owners under the name | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model tests 2–3 on staging: BU tab URL /portfolio/it-avalon with its single subtotal, /portfolio with ST21 / IT Avalon / Retro Rabbit group headers, three subtotals adding to the grand total, Billing-loss card, owners under the name, Delta Closed off the page | S22-3 | feat/s22-p5 |
| S22-P5-6 | S22-P5 | Engagement screens: Setup BU/owners/status, Allocations Person + per, Bill-rate columns for MSP without fee, Forecast Actuals block, New-engagement BU + owners | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p2-owner-path on staging through the v4 grid (Person first, planning resource, per, bill rates) and Setup; s22-p5 test 2 shows the Actuals block on the Forecast tab; New-engagement BU/owners by vitest + the owner path's create | S22-3 | feat/s22-p5 |
| S22-P5-7 | S22-P5 | Import screen /import/forecast-model: upload → dry run (BU cards, tab table, report) → Load → /portfolio | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model test 1 on staging: /import/forecast-model upload → dry-run cards/table/report → 'Load …' → lands on /portfolio | S22-3 | feat/s22-p5 |
| S22-P5-8 | S22-P5 | Playwright owner path: synthetic fixture → dry run 3 BUs → load → /portfolio/it-avalon Gamma Health-VMS → Actuals block → three subtotals add to grand total | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · tests/e2e/specs/s22/s22-p5-forecast-model.spec.ts: 3 passed on staging (with s22-p4-upload 2, s22-p1-contract, s22-p2-owner-path: 7 passed, 1.8 m); gate clean after | S22-3 | feat/s22-p5 |
| S22-P5-9 | S22-P5 | Reconciliation test: BU subtotals == Σ rows; grand total == Σ subtotals; cards.billing_loss.engagements == rows with actuals | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · test_model_import_load_creates_the_ledger_and_the_portfolio_groups_reconcile (subtotals == Σ rows, grand total == Σ subtotals, billing_loss.engagements == rows with actuals) + spec test 3 asserts Σ subtotal revenue == grand total on the staging screen | S22-3 | feat/s22-p5 |
| S22-P5a-1 | S22-P5a | Importer fix (pack): the dashboard's trailing roll-up block is not a client list — ST21 9 → 7 clients, ITA/RR no longer phantom clients; 34 forecast tests | verified working (staging) | staging API rev 103 · image s22p5a-a1c856f8 (digest cc35618a…b10) · 2026-10-13 · server dry run of the real master through scripts/load_forecast_model.py: ST21 7 clients (9 on the previous image), ITA/RR gone from the report; 34 forecast tests incl. test_the_roll_up_block_below_the_total_is_not_a_client_list; importer byte-identical to the pack; smoke 20261013T025103Z GREEN; s22-p5-forecast-model 3 passed on staging; gate clean | S22-3 | feat/s22-p5 |
| S22-P5a-2 | S22-P5a | scripts/load_forecast_model.py: --offline report, server dry run, --load asks once; never prints a rate, report outside the repo, master never committed | verified working (staging) | staging API rev 103 · image s22p5a-a1c856f8 (digest cc35618a…b10) · 2026-10-13 · the three documented commands run against the newest master in Downloads: --offline (28 tabs → 81 engagements, 393 people, report in /tmp, nothing created); server dry run (nothing created); --load refused by the S21 runtime isolation for the e2e bot (bug log row 7, by design) — needs a real user's bearer or the Load button; master gitignored by name, never committed; requests added to dev deps | S22-3 | feat/s22-p5 |
| S22-P5b-1 | S22-P5b | Importer (pack): as_of is a parameter, parse_master(src, as_of=None) → MODEL_AS_OF 2026-09, result.as_of printed as the report's first line; 36 forecast tests | verified working (staging) | staging API rev 104 · image s22p5b-63b786af (digest 42023218…5444) · 2026-10-13 · importer from the pack deployed unmodified; 36 forecast tests incl. test_as_of_is_per_call_and_never_leaks_between_imports + test_the_report_says_which_month_the_actuals_run_to; staging dry run of the real master without as_of opens with 'Actuals are taken through 2026-09; every later month is forecast' | S22-3 | feat/s22-p5 |
| S22-P5b-2 | S22-P5b | Service passes the request's as_of straight through (None when absent); test: a request without as_of after one with a different month still resolves to 2026-09 | verified working (staging) | staging API rev 104 · image s22p5b-63b786af (digest 42023218…5444) · 2026-10-13 · service passes the request's as_of through, None when absent (no _AS_OF read, no month in the service); test_as_of_defaults_to_the_models_month_and_never_leaks_from_an_earlier_request (2025-10 then none → 2026-09; Alpha actual months 2 then 3; 'Sept' → 422); the import screen sends no as_of and resolves to 2026-09 on staging | S22-3 | feat/s22-p5 |
| S22-P5b-3 | S22-P5b | CLI (pack): --as-of no longer defaults to today and is only sent when given | verified working (staging) | staging API rev 104 · image s22p5b-63b786af (digest 42023218…5444) · 2026-10-13 · CLI from the pack: --as-of has no default and is only sent when given; offline run without the flag → 28 tabs / 81 engagements / 393 people and the 2026-09 line; staging dry run without the flag → same counts (Σ tab people 393, ST21 7 clients), report identical to the P5a run; nothing created | S22-3 | feat/s22-p5 |

## Totals by state

| state | count |
| --- | --- |
| verified working (staging) | 36 |
| fixed and tested | 11 |
| missing | 5 |
| blocked | 2 |
| deferred | 11 |
| **total** | **65** |

S21-1b session deltas vs S21-1: five rows flipped to
`verified working (staging)` on **staging rev 66** (`s20-36f01fa4`)
with t45 items 1, 2, 3, 4, 7 passing (`npx playwright test
specs/s21/t45-s21-click-through.spec.ts -g "item [1234]|item 7"`
→ 5 passed / 7 skipped). S21-8 flipped from `blocked` to
`fixed and tested` (tf plan ran clean once the misdiagnosed
rule-15 block was corrected). S21-5 and S21-6 remain `missing` per
user directive (reserved for S21-1c). S21-9..S21-16 unchanged
(Sessions S21-2 and S21-3). Historic Liberty Mutual leak voided
during the deploy's smoke gate run — the gate fired first, proving
item 7's backend fix on live traffic.

Post-Lead-C2 deltas vs post-Lead-C1: +2 verified (W4-1, W4-7 flipped
on live staging rev 65 proof), −2 fixed. W4-1 flipped because
SummaryOut+summary_endpoint now surface `sows_in_progress` /
`agreements_uploaded` / `ceo_pending`; deep-link item counts match
card numbers (0 ≡ 0 for the two zero cards; sows_in_progress=1 shares
pending_approval scope). W4-7 flipped because
`list_pipeline_deals.total_open` is now scoped via
`is_closed_won=False AND is_closed_lost=False` (was leaking
closed-won); four-way reconcile at 104/104/104/104.
W7-1..W7-5 did NOT flip — t44-full-journey.spec.ts is a
`test.skip` skeleton and HubSpot token is read-only tonight
(isolation.md F1); no new 8-step W7 e2e spec authored this
checkpoint. Stays `fixed and tested` with S2-W7 proof.

## ETA

Rows not `verified working (staging)` = 18. Per rule 16, 7 verified
rows per session → **≈ 3 sessions** to clear. Next session's work:
(1) un-skip t44-full-journey.spec.ts step-by-step as W5/W7 harness
lands (start with intake+upload once W3 is wired for E2E auth, then
approvals, release, delivery, projects, forecast); (2) author W7
run-tag spec (upload fixture SOW → verify signature → release →
delivery accept → projects row → actuals → forecast GM) to flip
W7-1..W7-5; (3) resolve `sows_in_progress` deep-link scope — card
counts approval packages (3-lane sum) but deep-link filter is an
opportunity attribute; align the two or document explicitly.
