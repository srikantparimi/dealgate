# S20 · tests.md (W5 owned)

Per directive §8: one row per acceptance check T01–T44, with:

- `id` — the test id from the review.
- `title` — one-line action.
- `method` — `automated` (pytest / vitest / playwright with a spec path)
  or `manual` (steps given in the row).
- `result` — `pass` · `fail` · `not_run` · `blocked`. Seeded `not_run`;
  updated as W5 (and the growing-suite Lead runs) collect evidence.
- `evidence` — path to log/screenshot/report, or the specific commit + test-node id.
- `owner` — the worker who owns the underlying capability (per `contracts.md` §6).
- `notes` — dependency, xfail reason, or spec path if the test is written
  but currently skipped.

Column separator uses `|`. The table is intentionally wide so the source
of the failure and the owner are visible in one glance.

Result vocabulary (strict):
- `pass` — test executed and asserted the expected behavior on the
  matching branch/build. Evidence link required.
- `fail` — test executed and asserted the wrong behavior. Evidence link
  required, along with `docs/reports/s20/requests.md` entry addressed to
  the owner.
- `not_run` — the test exists (skeleton or full) but has not been
  executed yet against a build that includes the required capability.
- `blocked` — either the underlying capability is not yet on the branch
  (see `notes` — depends on W#), or an external system blocks the run
  (SES sandbox, HubSpot write scope, etc.).

## Coverage matrix

| id | title | method | result | evidence | owner | notes |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | Every sidebar item + KPI + stage chip navigates to its named destination (no `/pipeline` fallback) | automated · `tests/e2e/specs/s20/t01-sidebar-navigation.spec.ts` | pass (sidebar) | S3b · `integrate/s20 @ e746960e` on staging rev 57: `1 passed (15.7s)` with `/command` destinationMarker now `/command center/i` (Session 3b directive: Command-center-specific heading). CommandCenter passes `title="Command center. Every commitment in view."` to ExecutiveBanner. | W2 | KPI + stage-chip nav (T01b) still `test.skip` — depends on W2 KPI-card wiring (deferred; named in matrix.md Session 3b deferrals) |
| T02 | Stage buckets reconcile to filtered unique deals at one snapshot; company/deal counts stay separate; investigate 50 vs 106 gap | automated · `api/tests/test_s20_stage_reconciliation.py` | not_run | — | W1/W2 | pytest skeleton with `xfail(reason="depends on W1 stage aggregation by (pipeline_id, stage_id) — D9")` |
| T03 | SQL parity: BSC Staffing – UX/UI Designer (or nearest real deal) field-by-field across source, mirror, list, client, deal, export | manual+scripted · `scripts/t03-parity.sh` + `docs/reports/s20/t03-parity.md` | pass | S3 · `docs/reports/s20/t03-parity/bsc_65211153545/comparison.md` — 15/15 fields match on deal 65211153545 after L04 landed on staging rev 56. Also `docs/reports/s20/t03-parity/venetian_60275608921/comparison.md` from Session 2 (14/15 pre-L04, name-fallback documented). | W5 (harness), W1/W2 (upstream) | read-only mirror path only — HubSpot writeback stays out per D-ISO-01. |
| T04 | Test active / archived / missing / unresolved / no-local-account owners; company owner ≠ deal owner and is not overwritten | automated · `api/tests/test_s20_owner_resolution.py` | not_run | — | W1 (mirror), W2 (display) | pytest skeleton; needs owner mirror with archived-included from W1 |
| T05 | Combine owner + BU + stage + created last 30 days; verify OR-within / AND-across against independently expected rows | automated · `api/tests/test_s20_filter_combinations.py` | not_run | — | W2 | pytest skeleton; asserts on `PipelineFilters` service; W1 delivers BU mirror per D10 |
| T06 | Date filter: last 90 / next 30 / custom / missing / TZ / date-only preservation | automated · `api/tests/test_s20_filter_dates.py` | not_run | — | W2 | pytest skeleton; freeze-time fixture; TZ = America/Los_Angeles per contract §4 |
| T07 | Pagination 25/50/100; stable sort; filters reset page; Back/refresh restore; shared URL wins over localStorage; no dup/skip | automated · `tests/e2e/specs/s20/t07-pagination-url-state.spec.ts` | not_run | — | W2 | playwright skeleton; depends on W2 filter bar |
| T08 | Client with mixed open/closed deals, zero deals, multiple owners, multiple associated companies; 74 Sky consistent | automated · `tests/e2e/specs/s20/t08-client-rollups.spec.ts` + `api/tests/test_s20_client_rollups.py` | not_run | — | W2 | 74 Sky is Closed-Lost per L07; assert Open 0 with readable label |
| T09 | Names in headings, breadcrumbs, rows, owner/stage fields, search, export; known ids (11-digit deal, 10-digit stage, 8-char hash, UUID) never become labels | automated · `tests/e2e/specs/s20/t09-names-not-ids.spec.ts` | pass | S3b · staging rev 57: 5/5 tests pass (pipeline rows, stage cells, chips, deal-detail heading, client-detail heading). Regexes match 11-digit HubSpot deal id, 10-digit stage id, UUID (36-char). | W2 | Written this session; covers L02+L04+L07 name-integrity |
| T10 | Deal without a SOW shows Upload SOW, facts/actions/comments; no Delete SOW, no readiness, no fake gate | automated · `tests/e2e/specs/s20/t10-no-sow-deal.spec.ts` | not_run | — | W3 (stop auto-create) + W2 | depends on W3 stub migration (directive §6) |
| T11 | Upload with client + deal prefilled; cancel/fail/retry; exactly one linked package after successful persistence + confirmation | automated · `tests/e2e/specs/s20/t11-upload-prefill.spec.ts` | not_run | — | W3 | uses SOW upload harness in `fixtures/sow_extraction_stubs.ts` |
| T12 | Extraction failure, ambiguous fields, duplicate file, saved draft, reload/resume; preserve original file + entered corrections | automated · `api/tests/test_s20_extraction_recovery.py` | not_run | — | W3 | pytest skeleton around `sow_upload_pipeline` |
| T13 | Every SOW tab stays inside the workspace; exactly one readiness panel; Back/refresh work; no lost edits/context | automated · `tests/e2e/specs/s20/t13-sow-tabs-context.spec.ts` | not_run | — | W3 | playwright skeleton |
| T14 | One deal has two independent SOW packages with different states; versions/counts/values/decisions do not overwrite each other | automated · `api/tests/test_s20_many_sows_per_deal.py` | not_run | — | W3 | pytest skeleton; D1 rollup ordering; requires migration to relax `sow.opportunity_id` uniqueness (W3 → Lead via requests.md) |
| T15 | Separate NDA/MSA checks per S17; client + deal views refresh together; checkmark ≠ execution | automated · `api/tests/test_s20_nda_msa_rules.py` + `tests/e2e/specs/s20/t15-nda-msa-display.spec.ts` | not_run | — | W3 (SOW) + W2 (client) | D3: on-file ≠ signed/verified |
| T16 | Manual + dynamic groups with permissions; next action editable/assigned/due; latest comment + history accurate | automated · `tests/e2e/specs/s20/t16-groups-actions-comments.spec.ts` | not_run | — | W6 | playwright skeleton; awaits W6's tracking API + components |
| T17 | US exactly 35% and India exactly 50% pass when complete; India 49.999% fails despite display rounding; blended cannot hide failed component | automated · `api/tests/test_s20_gm_thresholds.py` | not_run | — | W3 (GM) | pytest skeleton; must exercise `app.gm` at full precision (CLAUDE.md rule 2) |
| T18 | Missing rate/cost/currency/allocation/revenue basis → incomplete; no false zero, no healthy risk, no Finance approval | automated · `api/tests/test_s20_gm_incomplete_inputs.py` | not_run | — | W3 | asserts `Not assessed` per contract §1 + review "Honest status language" |
| T19 | Complete all functional reviews; reject + request changes; assign rework and resubmit; server refuses stale browser version | automated · `api/tests/test_s20_stale_package_refused.py` + `tests/e2e/specs/s20/t19-approvals-e2e.spec.ts` | not_run | — | W3 (approvals) | server-side rule test + multi-role playwright; depends on multi-role fixtures (this commit) |
| T20 | CEO exception: below-floor requires valid exception; compliant model shows `Not required`; conditions/expiry/decline/material revision | automated · `api/tests/test_s20_ceo_conditional.py` | not_run | — | W3 | pytest skeleton around `ceo_exception` service |
| T21 | Post-approval change to price/scope/staffing preserves history, invalidates affected approvals, blocks signature/release until resolved | automated · `api/tests/test_s20_material_change_invalidates.py` | not_run | — | W3 | pytest skeleton; asserts revision creation + approval invalidation |
| T22 | Signature: unsigned upload, executed doc with changed terms, declined/expired, retry; no false execution, no duplicate external send | automated · `api/tests/test_s20_signature_verification.py` | not_run | — | W7 | pytest skeleton on `signature*` service; depends on W7 |
| T23 | Handoff verifies executed terms + conditions + Delivery accept; project created/linked exactly once; CRM Closed Won alone does not authorize | automated · `api/tests/test_s20_release_authorization.py` | not_run | — | W7 | pytest skeleton; asserts server 403 when CRM alone |
| T24 | Enter forecast + partial actuals + duplicate imports; keep baseline/period-actuals/forecast distinct; trigger recovery on deterioration | automated · `api/tests/test_s20_baseline_forecast_actuals.py` | not_run | — | W7 | pytest skeleton; expects idempotent import per D7 spirit |
| T25 | Renewals: month-end, leap year, earlier-notice deadline, short assessment, weekly repeat, unverified claimed extension | automated · `api/tests/test_renewals.py` (existing) + `api/tests/test_s20_renewals_calendar_months.py` (new) | not_run | — | W4 | new pytest asserts two calendar months per D8 (was 60 days per L15) |
| T26 | Filter reports by BU/owner/period; drill and export; totals reconcile; currencies/bases declared; unknown-value counts visible | automated · `api/tests/test_s20_report_totals.py` | not_run | — | W4 | pytest skeleton |
| T27 | Unauthorized direct URLs, API decisions, salary reads, downloads, exports → server denies; role change cannot self-grant CEO | automated · `api/tests/test_s20_permissions_uniform.py` | not_run | — | W3/W4/W7 | pytest skeleton covering every mutating endpoint; asserts 403 with reason |
| T28 | Duplicate/out-of-order events, property clears, owner/stage rename, association change, merge/delete, failed-job recovery — no data loss | automated · `api/tests/test_s20_sync_edge_cases.py` | pass (7/8; 1 xfail) | S3b · 5 originally-passing tests (Session 2) + 2 W2-side xfails cleared: `test_stage_rename_updates_label_stable_id` (mirror-driven label refresh, stage_id stable), `test_association_change_no_double_count` (client_id re-points, no double-insert). 1 xfail remaining: `test_worker_crash_resumes_from_cursor` — W1 Session 4 continuous-consumer scope. | W1/W2 | S3b closes the W2 handoff; W1 finishes cursor-resume when the continuous consumer lands |
| T29 | Dry-run stub classification; protect legitimate no-file work; archive rollback + legacy-link redirects; no orphaned attachments/decisions | manual+scripted · `docs/reports/s20/stub-manifest.md` + `scripts/stub-migration-dry-run.sh` | not_run | — | W3 (dry run), Lead (approval) | scripted dry-run runs read-only; execution behind Lead review per directive §6 |
| T30 | Keyboard, long names, narrow screens, 200% zoom; readable errors, unavailable data, pending actions | manual · steps in `docs/reports/s20/click-through.md` §accessibility | not_run | — | W2 | manual checklist; part of morning click-through |
| T31 | Separate source owner / local assignee; two SOWs per deal with per-SOW gates + release rollup | automated · `api/tests/test_s20_ownership_and_rollup.py` (folds into T04 + T14) | not_run | — | W1 (owner), W3 (SOW rollup) | covered by T04 + T14; a small dedicated pytest asserts D1 rollup ordering headline |
| T32 | Inject > 10 synthetic events + one immediately after a run; verify draining, measured freshness, stale banner, DLQ handling | automated · `api/tests/test_s20_freshness_injection.py` + `scripts/inject-events.py` | not_run | — | W1 | pytest with `xfail(reason="depends on W1 continuous-consumer cutover (D4, §4)")`; injection script tags every event with an `s20-` marker per isolation §7 |
| T33 | Fail a scan midway, resume, simulate overlapping runs; no premature archives, no lost seen-set; records created during scan preserved | automated · `api/tests/test_s20_scan_resume.py` | not_run | — | W1 | pytest with xfail until W1's scan-generation semantics land (A3) |
| T34 | Same source event under distinct queue ids; retry after commit / before ack; exactly one business effect + coherent audit/outbox | automated · `api/tests/test_s20_source_dedup.py` | not_run | — | W1 | pytest with xfail until W1's dedupe key on source event id lands (D7, A4) |
| T35 | Matching attention/SOW rows beyond page 1; rows/counts/chips/groups/export use the full matching set (A5) | automated · `api/tests/test_s20_pagination_vs_totals.py` | pass (5/5) | S3b Rev-2 · replaces 4 xfail skeletons with 5 real assertions on seeded 137 rows: total==137 on page 1, stable across pages 1..6, chip counts + unknown_bucket sum to total, chips carry `open_value_by_currency` per currency, page_size 25/50/100 all respected. All 5 pass locally. Server code path exercised on staging rev 58 via T40 L03 + L06 + L06b. | W2 | Chip `open_value_by_currency` field added this cycle (review L06). |
| T36 | Prove feature-branch → staging path, compatible UI+API rollout, all worker versions, migration rollback before owner click-through | manual+scripted · `docs/reports/s20/deploy.md` + `scripts/deploy-smoke.sh` | not_run | — | W4 (runbook), Lead (execution) | evidence from tonight's deploy log |
| T37 | Interrupt upload/extraction, restart workers; recover without duplicate SOWs or approved-version mutation; direct deal binding survives | automated · `api/tests/test_s20_upload_interrupt_recovery.py` | not_run | — | W3 + W1 | pytest skeleton; uses idempotent upload key |
| T38 | Token/role checks, private API responses, real notification constraints, cleanup isolation; document deferred production controls | automated · `api/tests/test_s20_security_boundaries.py` + `docs/reports/s20/isolation.md` (existing) | not_run | — | W4 (integrations page), W1 (cleanup) | pytest asserts /api not cached, Authorization forwarded, webhook signatures verified, Cognito claims validated (A8) |
| T39 | One report/summary dependency failure → unavailable + useful error; independent sections stay accurate; never substitute zero | automated · `api/tests/test_s20_report_dependency_failure.py` | not_run | — | W4 | pytest with mocked failing dep; asserts `Unavailable` + reason, sibling metrics unchanged |
| T40 | Reproduce Proposal filtering, 50-of-106 access, deal-name display, client rollups, URL state, reset, counts; 74 Sky Open 0 + readable | automated · `tests/e2e/specs/s20/t40-live-repro.spec.ts` | pass (8/8 on staging) | S3b Rev-2 · staging rev 58: L02 chip URL, L03 pagination 25/50/100, L04 name-vs-stage, L05 client owner + rollup, L06 chip counts, **L06b chip value line (S3b Rev-2)**, **Owner + BU selects present (S3b Rev-2)**, L07 74 Sky Closed Lost callout — 8/8 pass (1.2m for full S20 run). | W2 | Extended in Rev-2 with chip-value + filter-selects assertions. |
| T41 | With every other signature prerequisite met, test the exact approved on-file rule across client / workspace / signature UI / server; no conflicting note-only vs blocking state | automated · `api/tests/test_s20_signature_nda_msa_rule.py` | not_run | — | W3 + W7 | pytest asserts the D3 rule surfaces + server matches (L13 contradiction) |
| T42 | > 100 records incl. closed + unknown-stage; chart labels, scope, filters, drill-through, exports; approval-turnaround aggregate implemented | automated · `api/tests/test_s20_report_scale.py` + `tests/e2e/specs/s20/t42-report-scale.spec.ts` | not_run | — | W4 | if turnaround endpoint not implemented tonight → row remains `not_run`, matrix.md logs `missing` with W4 next-action |
| T43 | Each integration card matches actual supported config + permissions; read-only HubSpot must not claim writeback; empty events ≠ healthy | automated · `api/tests/test_s20_integrations_truthfulness.py` | not_run | — | W4 | pytest asserts card content derives from verified config; addresses L19–L20 |
| T44 | Full e2e journey: intake → rework → approvals → conditional CEO → executed evidence → release → delivery acknowledge → project/actuals → calendar-month renewal; capture build + resulting states | automated · `tests/e2e/specs/s20/t44-full-journey.spec.ts` | not_run | — | ALL | multi-role playwright, uses `fixtures/multi-role-auth.ts`; last spec of the suite |

## Growing-suite runs

The Lead pulls latest from all `s20/W*` into `integrate/s20` every ~2h;
W5 runs the growing suite (`pytest -q && cd web && npx vitest run --reporter=dot && cd ../tests/e2e && npx playwright test --reporter=list`) and logs outcomes here.

| cycle | integrate/s20 commit | pytest | vitest | playwright | notes |
| --- | --- | --- | --- | --- | --- |
| 0 · pre-integration | (s20/W5 alone) | not_run | not_run | not_run | skeletons only; execute once W2/W3/W1 land their first commits |
| S3 · W2 L04 landed | `58aa3ad8` | 953 pass / 7 skip / 155 xfail (0 fail) in 175.80s | not_run this cycle | T01 sidebar: pass (24.8s) against staging rev 56; T01b KPI/chip nav still `test.skip` awaiting W2 URL-state filter bar | L04 verified end-to-end (BSC parity 15/15). Non-critical W2 UI surfaces (filter bar, pagination controls, chip counts UI, client/deal page rebuild) deferred to W2 cycle 3. |
| S3b · W2 completion | `e746960e` | pytest exit 0 (adds 5 new + un-xfails 2 = ~960 pass) | not_run this cycle | 12 passed / 13 skipped (T01, 5×T09, 6×T40) in 36.9s on staging rev 57 | All D-W2-02 deferrals shipped: DealDetail v2 (/deals/:id), ClientDetail v2 (/clients/:id), T09 spec (5 tests), T40 assertions (6 real tests), T28 W2 xfails cleared (2 pass). New endpoints `GET /pipeline/opportunities/{id}` + `GET /pipeline/pipelines/{id}/stages`. T01 uses Command-center-specific heading. |
| S3b Rev-2 · items 1-3 completion | `c253f011` | +6 pass (T35=5, facets=1); test_s20_pagination_vs_totals.py replaces 4 xfail skeletons | not_run this cycle | 14 passed / 13 skipped in 1.2m on staging rev 58 (adds L06b + Owner/BU selects) | Chip `open_value_by_currency` (L06 · "value per chip"), `GET /pipeline/facets` + owner + BU selects in FilterBar (BU disabled with "not mirrored" label per D10), T35 pytest replaces skeletons. Rows 1-3 of the directive now `verified working (staging)`. |

## Log

- 2026-09-30 · W5 cycle 0 · initial skeleton — every T-row seeded `not_run`;
  pytest + playwright test skeletons committed on `s20/W5`.
- 2026-09-30 20:45 UTC · Session 3 W2 · T01 sidebar spec: pass on staging
  after two `destinationMarker` regex corrections (`/command` → editorial
  banner headline, `/discovery` → "AI adviser" PageHeader). T01b KPI +
  stage-chip nav stays `test.skip` — depends on W2 URL-state filter bar
  work deferred to W2 cycle 3.
- 2026-09-30 20:20 UTC · Session 3 W2 · T03 parity re-run on BSC
  Staffing - UX/UI Designer (deal 65211153545): 15/15 fields match after
  L04 landed on staging rev 56 (`s20-58aa3ad8`). The Session 2 Venetian
  deficit (name = stage_label fallback) is fixed by the new
  `opportunity.name` column mirroring `dealname` + search matching on it.
- 2026-09-30 22:00 UTC · Session 3b W2 · deploy `s20-e746960e` on rev 57.
  Smoke green. DealDetail v2 + ClientDetail v2 live at /deals/:id and
  /clients/:id. T01 asserts /command center/i heading (Command-center-
  specific per S3b directive). T09 + T40 written + green (11 new
  assertions). T28 W2-side xfails cleared (stage rename + association
  change now pass). No new migration. See matrix.md Session 3b for
  the per-review-line state.
- 2026-09-30 22:20 UTC · Session 3b Rev-2 · deploy `s20-c253f011` on
  rev 58. Smoke green (second run — first run tripped the known Bedrock
  flake). Closes the three items 1-3 of the S3b directive that were
  under-reported: stage chip value line (server aggregates
  `open_value_by_currency` per chip; UI renders under count), Owner
  select in FilterBar populated by new `GET /pipeline/facets`, BU
  select rendered disabled with "not mirrored on this portal" label
  (D10 evidence). T35 pytest replaces its 4 xfail skeletons with 5
  real assertions on seeded 137 rows — all pass. T40 gains L06b +
  Owner/BU-present blocks (both pass on rev 58). All three lines now
  `verified working (staging)` in matrix.md.
