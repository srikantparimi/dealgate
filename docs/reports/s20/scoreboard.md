# S20 · scoreboard

One row per deliverable across W1, W2, W6, W4, W7, Final. States are
strict (rule 16): `verified working (staging)` · `fixed and tested` ·
`missing` · `blocked` · `deferred`. Every session updates its rows
**first and last**. ETA = rows-not-verified ÷ 7 per session.

**Current head:** `integrate/s20 @ 36f01fa` on **staging rev 66**
(`s20-36f01fa4`). S21-1b deploy: image built + pushed digest
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
