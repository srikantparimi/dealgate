# S20 · scoreboard

One row per deliverable across W1, W2, W6, W4, W7, Final. States are
strict (rule 16): `verified working (staging)` · `fixed and tested` ·
`missing` · `blocked` · `deferred`. Every session updates its rows
**first and last**. ETA = rows-not-verified ÷ 7 per session.

**Current head:** `integrate/s20 @ d5d6f51` · staging rev 62
(`s20-0573d19d`).

**Lead-S20-C1 checkpoint (2026-09-30):** STOPPED at step 1 (rebase).
Both lanes edited files outside their owned sets per rule 17.
No rebase, no merge, no deploy, no flips. Attempted rows W4-1,
W4-3, W4-4-CARDS, W4-6, W4-7, W7-1, W7-2, W7-3, W7-4, W7-5
remain at their lane-reported state (`fixed and tested`) pending
Lead decision on the ownership exception.

**Lead-S20-C1-resume (2026-10-01, in flight):** attempting rows
W4-1, W4-3, W4-4-CARDS, W4-6, W4-7, W7-1, W7-2, W7-3, W7-4, W7-5
after recording D-S20-17a (shared-append-only exception for
`web/src/api/client.ts` + routes/nav + main.py registration block;
adds `signed_sow.py` to Lane B owned list). Flips occur only on
step 4-6 staging proof.

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
| W4-1 | W4 | Command center numbers via summary() + deep-link filter | fixed and tested | 1 of 4 cards (Watching) deep-links; summary=list pytest; other 3 cards still in ceo_view | S5 | A |
| W4-2 | W4 | Renewals (2 calendar months, Jan 31 → Nov 30, noreply@dealgateapp.com, Renewals page) | verified working (staging) | compute_alert_date pytest; SES sender constant; T39 no-raw-ids on /renewals | S5 | integrate |
| W4-3 | W4 | Reports page (pipeline by stage/owner/BU + SOW GM + aging + CSV, totals before pagination) | missing | router has only approval-turnaround + portfolio-basis endpoints | — | A |
| W4-4-TRUTH | W4 | Integrations page truthful (sync_status reads + no static "Connected") | verified working (staging) | grep "Connected" zero hits; T39 asserts "Last sync/success/attempt" prose | S5 | A |
| W4-4-CARDS | W4 | Integrations Bedrock + SES + heartbeat cards | missing | three cards not added | — | A |
| W4-5 | W4 | Freshness alarms applied via tf-init.sh with human-answered prompt | blocked | rule 15; TF staged in W1-ALARMS | S5 | integrate |
| W4-6 | W4 | System health page (DB, SQS depth + DLQ, last reconcile, last purge, test-data gate) | fixed and tested | Page reachable (T39); per-panel liveness audit not run | S5 | A |
| W4-7 | W4 | Reporting numbers agree (CC == Reports by-stage == /pipeline) | fixed and tested | Two-way (CC ↔ Pipeline) proven; three-way needs W4-3 | S5 | A |
| W4-8 | W4 | No raw ids on W4 pages (extend T09) | verified working (staging) | T39 asserts on /command /renewals /reports /settings/integrations | S5 | A |
| W7-1 | W7 | Signature verification: signed SOW signatories match approved version; mismatch = inline editor | missing | — | — | B |
| W7-2 | W7 | Release: signed + NDA/MSA (never blocker; show gap, allow) → Released state + audit + Handoff row | missing | — | — | B |
| W7-3 | W7 | Delivery acceptance (accept with staffing baseline; reject = inline reason) | missing | — | — | B |
| W7-4 | W7 | Project creation (single staffing + GM baseline → Projects page with names) | missing | — | — | B |
| W7-5 | W7 | Forecast vs actuals (monthly actual entries; GM vs forecast; floor breach → attention flag) | missing | — | — | B |
| FINAL-T36 | Final | Deploy pipeline (D5 proven, image + migration + rollback) | verified working (staging) | S1 deploy ran rollback 53→51→53 in 3m30s | S1 | integrate |
| FINAL-T38 | Final | Security boundaries + production-claim honesty (A8) | fixed and tested | Smoke gate checks auth/caching/webhook sig; integration page labels current vs planned | S1 | integrate |
| FINAL-T44 | Final | Full multi-role journey (intake → approve → CEO → signature → handoff → delivery → renewal) | missing | T44 spec skipped — needs W7 landing | — | B |
| FINAL-U01 | Final | 5 Cognito approver test users + SES sandbox verifications | verified working (staging) | S1 U01 TF slice + 5 users verified | S1 | integrate |
| FINAL-CLICK | Final | Product-owner click-through on staging | missing | tracked in click-through.md | — | integrate |

## Totals by state

| state | count |
| --- | --- |
| verified working (staging) | 25 |
| fixed and tested | 9 |
| missing | 10 |
| blocked | 2 |
| deferred | 1 |
| **total** | **47** |

## ETA

Rows not `verified working (staging)` = 22. Per rule 16, 7 verified
rows per session → **≈ 3-4 sessions** to clear (W7 lane needs ~2
sessions for items 1-5; W4 lane needs ~1-2 for 1, 3, 4-cards, 6, 7;
plus the final Lead checkpoints and the click-through).
