# S23-PL2 · Pipeline page redesign, built on real data — report

**Branch:** `feat/s23-pl2` (worktree `/Users/srikanthparimi/OfficeApp/dealgate-s23-pl2`, off `origin/main` f79a1c7). **Not merged:** Kanna clicks first.

**Staging:**
- API `officeapp-dev-api:117` on image `s23pl2-b361a77d` (digest `sha256:02ace77d15b7d00afd920440d62fc5673c6a5f62a1cc8e78ac9a62853df92ab5`).
- Migration `20261014_0070_pl2_workspace`, applied by task `70469fa6` through the Terraform migration run.
- SPA `assets/index-dkxSd_MK.js`.
- Deploy smoke `smoke 20261015T005100Z` GREEN; leak gate clean (now including the bot's views, groups and watches).

**Written:** 2026-10-14. Companions:
- `docs/bugs/s23-pl2.md`: decisions K1–K5, deviations V1–V34, bugs G1–G15, pre-existing issues P1–P6.
- Scoreboard rows S23-PL2-B1 … S23-PL2-T12.

The commits after the deployed `b361a77` change only Playwright specs and this report; staging runs the branch's application code.

## Every item (rule 16 vocabulary)

"Staging" below means API rev 117 / image s23pl2-b361a77d / SPA index-dkxSd_MK.js, 2026-10-14. Proof sources:

- **Probe:** a read-only one-off task on rev 117 (`bde99ebe`, guard `default_transaction_read_only=on`). It ran the image's own routers in-process as a synthetic SystemAdmin.
- **Spec:** `tests/e2e/specs/s23/s23-pl2-pipeline.spec.ts`, run on staging as the e2e bot with run-tagged fixtures.
- **Screenshots:** in `/private/tmp/claude-501/-Users-srikanthparimi-OfficeApp/f18ab184-79ff-429a-b7fb-97c956d4d16b/scratchpad/pl2/staging-shots/`, outside the repo.

### Disposition of the discovery findings (D1–D31)

| Item | State | Proof |
| --- | --- | --- |
| D1 | verified working (staging) | CUT: no client sector anywhere. Spec "previews…": the deal preview has 0 matches for /alert\|notes?\|sector/; `web/src/__tests__/v2/S23PipelineAbsent.test.tsx` passed |
| D2 | deferred | DEFERRED to phase 2 by the directive (SES sending, production access). No alert UI built: the spec asserts 0 "alert" buttons on the page; S23PipelineAbsent passed |
| D3 | verified working (staging) | BUILT (B3, F7, F18). Probe: bu=ST21 22 / USD 7,740,015.00, IT Avalon 39 / 9,057,535.00, Retro Rabbit 45 / 4,611,494.14 and unmapped 0 all equal SQL by region (US 22; US - IT Avalon 12 + (Staffing) 27; South Africa 45). Rows show "IT Avalon · US · Staffing". Spec T8 Retro Rabbit filter → chip "BU: Retro Rabbit (South Africa)" |
| D4 | verified working (staging) | CUT: NDA/MSA show only "on file" or "missing" (spec tonight: "NDA missing", "MSA missing"; populated: "NDA on file") |
| D5 | verified working (staging) | CUT "Scope & GM": `options.sow_states` holds the nine derived states (labels below). Staging rows show "No SOW" and "Draft" |
| D6 | fixed and tested | BUILT (B4, F6): see B4. On staging the unlinked bot sees "My opportunities" disabled, with the hint (screenshot d1440-sync-failed.png sidebar) |
| D7 | verified working (staging) | BUILT (B5): status `hold` and the HOLD stage card. Probe `includes_on_hold` 2. Spec tonight: "On hold" tag |
| D8 | verified working (staging) | BUILT (B1, B7): accounts ("4 accounts" etc.), "includes 1 on hold", closing value, "$0 + 1 no amount" per stage, clients_total ("of 4 clients"). Probe metrics, spec, screenshots |
| D9 | verified working (staging) | BUILT (B6, F4, F8): the Agreement gaps card opens the Clients tab and its count equals the card (spec T2). NDA/MSA tags on deal rows |
| D10 | fixed and tested | BUILT (B6): q matches next-action text. `test_s23_pl2_workspace.py::test_search[next action]` passed. Staging search proven for titles only (spec T8 "Paused rollout") |
| D11 | verified working (staging) | CUT: probe page_size=12 → 422 "page_size must be one of 25, 50, 100". Rows select offers 25/50/100 (spec T8 → page_size=50) |
| D12 | verified working (staging) | BUILT (B6): spec T8 sort → `sort=name`. Deal and client sorts covered by test_deal_sorts[4] and test_client_sorts[4] |
| D13 | verified working (staging) | BUILT (B10): probe export of deals is 106 rows plus header, BOM, Currency column; clients 53 plus header. Spec "previews…" downloads DealGate_Pipeline_deals.csv starting with a BOM |
| D14 | verified working (staging) | BUILT (B6): created date, next-action text and due date, account owner, agreements and pipeline name on rows and in the preview (spec "previews…": preview fields; populated screenshot) |
| D15 | verified working (staging) | PL1 + B15/F3: freshness from run records. Spec F3 and `s23-pl1-sync-label.spec.ts` passed on staging |
| D16 | verified working (staging) | PL1 (webhooks never reopen closed deals). Not touched here; see `docs/reports/s23/pl1-report.md` items 5–6 |
| D17 | verified working (staging) | BUILT (B13): "No deal owner" only on open deals. The former owner reads "Former HubSpot user". Client flags only from open deals (test_s23_pl2_workspace owner tests). Staging populated screenshot: "Not assigned" plus "No deal owner" on the open fixture |
| D18 | verified working (staging) | BUILT or removed (B7, F6, T8): spec T8 on staging (every control changes the list or URL). "Action due" date field and the built-in views are gone |
| D19 | verified working (staging) | BUILT (B7, B8): overdue and pending count DEALS. "today" is the LA date: the probe at 00:55 UTC Oct 15 reported `today` 2026-10-14 |
| D20 | fixed and tested | BUILT (B10, B12). Formula neutralisation in all five CSV writers: test_s23_pl2_export.py 28 passed, and the staging spec T6 export (below). Sales-only client pages: test_s23_pl2_access.py. Presales export unchanged: decision K1 |
| D21 | verified working (staging) | KEPT and labelled (B5, F8): Hold counts as open ("includes 1 on hold · unweighted", "Status: Open (includes on hold)", stage "Hold (open, paused)") |
| D22 | verified working (staging) | PL1 (nightly sync robust); see the PL1 report. Run sync now on staging finished (F3 below) |
| D23 | verified working (staging) | BUILT (B11, F12): spec populated: two views saved, the case-insensitive duplicate shows "You already have a view with this name.", a group was created from the bulk bar, a deal was watched |
| D24 | verified working (staging) | BUILT (T11): the gate checks the bot's views, groups and watches; it is clean on staging after every run. Leftover test client reported, not deleted: "smoke smoke 20261003T174232Z" |
| D25 | verified working (staging) | BUILT (T12): run-tagged fixture deals with stage, amount, region, owner, next action, SOW state and NDA file (spec) |
| D26 | deferred | DEFERRED to phase 2 with D2 (no email). Nothing built |
| D27 | verified working (staging) | BUILT (B1): 1 request and 7 statements per filter change, against 7 requests and 42 statements (table below) |
| D28 | verified working (staging) | BUILT (B14, F19): GET /api/config on staging returns the portal id. "Create in HubSpot" href is `…/contacts/{config id}/deal/new` (spec). DealDetail and ClientDetail read config (S23PortalIdConfig.test.tsx) |
| D29 | deferred | DEFERRED (HubSpot notes out of scope). No notes on this page (spec and S23PipelineAbsent) |
| D30 | verified working (staging) | BUILT (B2): probe CC open_opportunity_value 21,409,044.14, count 106 = Pipeline = SQL. `command-center-redesign.spec.ts` passed on staging with "Open opportunity value" and "Not yet in the SOW flow" |
| D31 | verified working (staging) | Expected: screenshots d1440-light-tonight.png (empty work columns) and d1440-light-populated.png (populated) |

### Backend (B1–B15)

| Item | State | Proof |
| --- | --- | --- |
| B1 | verified working (staging) | `GET /api/pipeline/workspace` (`api/app/routers/pipeline.py:1139`, `api/app/services/pipeline_workspace.py`). Probe: 7 SQL statements (8 for clients with unmatched), median ~290–300 ms, against 7 requests and 42 statements before (table below). Old endpoints kept. The page makes one request per change (spec) |
| B2 | verified working (staging) | One filter function `matches()` and `is_open()` (`hubspot_pipeline.py:825-840`) serve workspace, export and CC (`open_totals`, `pipeline_workspace.py:1092`). Probe: SQL 106 / 21,409,044.14 = workspace = CC. Stricter tile labelled "Not yet in the SOW flow" (CC spec passed). test_s23_pl2_command_center.py 6 passed |
| B3 | verified working (staging) | `hubspot_region_map` (migration 0070, seeded); `GET/PUT /api/settings/business-units`. Probe BU counts equal SQL by region (D3). Settings → Business units renders on staging (spec, d1440-settings-business-units.png). The edit path is proven by test_s23_pl2_region_map.py; staging's mapping was not edited |
| B4 | fixed and tested | `user.hubspot_owner_id` and link source (0070). Auto link at sign-in (`ensure_user`) and owner sync; admin override `PUT /api/users/{id}/hubspot-owner`. Tests: test_s23_pl2_user_link.py (email match, sync, override, unlink, HubSpot-created user, mine) and test_s23_pl2_viewer.py. Staging: 0 of 28 users linked at deploy (link happens at sign-in or the nightly owner sync); the bot has no owner and sees the unlinked hint |
| B5 | verified working (staging) | status open includes Hold; hold = Hold stage. Probe includes_on_hold 2. test_status[open\|hold\|won\|lost\|all] passed |
| B6 | verified working (staging) | DealRow and ClientRow fields per contract plus additive fields (V4). Sorts, nulls last; q over title, client, owner and next action. Spec rows on staging. SOW link facts below |
| B7 | verified working (staging) | Metric value = list of current ⊕ drill. API: 106 filter combinations × 6 metrics (test_s23_pl2_metric_drill.py). Page: spec T2, all six cards on staging. Pending vs SOW board reported (K3) |
| B8 | verified working (staging) | `api/app/services/business_time.py` (LA calendar). test_s23_pl2_dates.py 84 passed (month end, quarter end, both DST changes, every preset). Staging `today` = LA date at 00:55 UTC |
| B9 | verified working (staging) | 25/50/100 else 422 (probe). Board lanes ≤ 6 with totals (spec T8 board; test_board_lanes_hold_at_most_six_deals) |
| B10 | verified working (staging) | `GET /api/pipeline/export` (BOM, CRLF, contract columns). Neutralisation in it and in `/reports/pipeline/export.csv`, `/portfolio/forecast.csv`, `/command-center/accounts.csv`, `/admin/bulk-imports/{id}/log.csv` (`api/app/services/csv_safety.py`). Staging: spec T6 export row carries `'=HYPERLINK(`; probe export headers |
| B11 | verified working (staging) | Root cause of the second-view failure: the unique key `(owner_id, key='custom', is_builtin)` (G1), replaced in 0070. Views, groups and watches key on the DealGate user id. Staging: second view saved, duplicate 409 message, group, watch (spec). HubSpot-created user path proven with FK-enforced tests (T5) |
| B12 | fixed and tested | `routers/clients.py:_access_or_forbid` lets Sales read client pages: test_s23_pl2_access.py. Presales export unchanged (K1); BU scoping deferred (K2). No Sales-only identity on staging to click it |
| B13 | verified working (staging) | Owner {name, state}; "Former HubSpot user"; no_owner only on open deals; client flags only from open deals. Staging rows (populated screenshot). test_s23_pl2_workspace owner tests |
| B14 | verified working (staging) | `GET /api/config` → hubspot_portal_id from HUBSPOT_PORTAL_ID (no infra change). Spec reads it and checks the Create in HubSpot href |
| B15 | verified working (staging) | `workspace.freshness` = compute_sync_health, now one statement (output unchanged, PL1 44 tests pass). Probe freshness fresh, last success 2026-10-14T20:08:16Z (run record) |

### Frontend (F1–F20)

| Item | State | Proof |
| --- | --- | --- |
| F1 | verified working (staging) | `web/src/pages/v2/Pipeline.tsx` + `web/src/pages/v2/pipeline/*` on the app kit and tokens, app light/dark themes, no own toggle. Screenshots d1440-light-*.png, d1440-dark-pipeline.png |
| F2 | verified working (staging) | One request per view (`useWorkspace`), stale request aborted, 300 ms search debounce, filters in the URL. Spec T8 URL assertions and goBack restoring the view. S23PipelineShellUrl.test.tsx |
| F3 | verified working (staging) | Three states with the prototype copy: spec F3 (real fresh, then stale and failed by response interception; d1440-sync-*.png and d1440-sync-panel-*.png). SystemAdmin "Run sync now" on staging showed "Sync started", rode out the CloudFront cut, polled sync-health and showed "Sync finished · Succeeded" (spec F3 run-now; d1440-sync-run-finished.png) |
| F4 | verified working (staging) | Six cards; drill → list count = card for all six on staging (spec T2). Agreement gaps opens Clients. "no agreement files uploaded yet" shown tonight |
| F5 | verified working (staging) | Nine stages; selecting 4 → `status=all&stage=4&status_before=open`; clearing restores Open (spec T8) |
| F6 | verified working (staging) | Focus views with counts from `focus` (Watching 1 after the watch); unlinked hint (staging screenshots) |
| F7 | verified working (staging) | Search, status, owner by tab, BU with regions and US note, Date dialog presets, More filters, removable chips, Reset all (spec T8; S23PipelineShellFilters) |
| F8 | verified working (staging) | Columns and tags as the prototype. Tonight: "Set next action →", "No activity recorded", "No SOW", "NDA/MSA missing". Hold labelled. Unmapped note links to Settings (unit) |
| F9 | verified working (staging) | Clients tab on staging (spec T8, Agreement gaps drill). Account owner filter, sorts, include-unmatched (S23PipelineRecordsClients; probe clients+unmatched) |
| F10 | verified working (staging) | Board on staging (spec T8 layout=board); ≤ 6 cards and "Show all N in list" (S23PipelineRecordsBoard) |
| F11 | verified working (staging) | Deal and client previews; the editor saved a next action on staging through the existing endpoint `POST /api/next-actions` (edits use `PATCH /api/next-actions/{id}`, `api/app/routers/next_actions.py:139,173`) → "Next action saved." Watch toggle. No alerts or notes (spec "previews…") |
| F12 | verified working (staging) | Saved views (second one saves; duplicate message), tracking groups, watching (spec populated) |
| F13 | verified working (staging) | Bulk bar: two deals selected → Add to group (spec). Watch selected covered in S23PipelineRecordsPanel |
| F14 | verified working (staging) | Export button downloads DealGate_Pipeline_deals.csv with BOM (spec "previews…") |
| F15 | verified working (staging) | Text nodes only; the guard test S23PipelineNoInnerHtml passes. The staging fixture labelled `<img src=x onerror=…> =HYPERLINK(…)` renders literally, nothing runs, no img element (spec tonight) |
| F16 | verified working (staging) | 375 px light and dark: scrollWidth = clientWidth; stacked cards; "Views & groups" panel (spec T10; m375-*.png) |
| F17 | verified working (staging) | Radix dialogs: focus trap, Escape closes (used on staging throughout the spec); aria-pressed on toggles; labels (S23PipelineShell*, S23PipelineRecords*) |
| F18 | verified working (staging) | Settings → Business units and Settings → People & access (HubSpot owner link, "Auto-matched by email") render on staging (spec, screenshots). Edit and override paths: S23SettingsBusinessUnits, S23SettingsUserOwnerLink |
| F19 | verified working (staging) | Portal id from /api/config; the three hard-coded copies are gone (Pipeline.tsx rewritten; DealDetail.tsx, ClientDetail.tsx). Spec checks the href |
| F20 | verified working (staging) | No alert controls, no notes, no client sector (spec and S23PipelineAbsent) |

### Tests (T1–T12)

| Item | State | Proof |
| --- | --- | --- |
| T1 | verified working (staging) | Probe: SQL with the page's rules 106 / USD 21,409,044.14 = Pipeline open_deals 106 / open_value_usd 21,409,044.14 = Command Center open_opportunity_value 21,409,044.14 / count 106 |
| T2 | verified working (staging) | API: test_s23_pl2_metric_drill.py, 106 combinations × 6 metrics, passed. Page: spec T2, six cards on staging |
| T3 | fixed and tested | test_s23_pl2_region_map.py: four seeded values plus an unmapped one; a Settings PUT changes the workspace's deal rows at once. Staging's mapping was not edited |
| T4 | fixed and tested | test_s23_pl2_user_link.py + test_s23_pl2_viewer.py (email match at sign-in and at owner sync, admin override, unlink, HubSpot-created user, mine=true) |
| T5 | fixed and tested | test_s23_pl2_personal.py with FK enforcement and on Postgres: HubSpot-created user, second and third view, 409 duplicate, groups, watches. The bot path on staging passed (spec populated) |
| T6 | verified working (staging) | Page: injection label renders literally on staging (spec tonight). CSV: staging export row prefixed `'=HYPERLINK(` (spec T6). All five writers: test_s23_pl2_export.py |
| T7 | fixed and tested | test_s23_pl2_dates.py 84 passed (frozen clock: month end, quarter end, DST start and end, every preset) |
| T8 | verified working (staging) | Spec T8 on staging |
| T9 | verified working (staging) | Before/after on staging (table below); test_s23_pl2_cost.py budget 7/7/7/8 |
| T10 | verified working (staging) | Spec T10: 1440 and 375, light and dark, no horizontal scroll; screenshots outside the repo |
| T11 | verified working (staging) | `scripts/check-test-data-clean.sh` covers the bot's views, groups and watches; clean after every staging run. Leftover reported: "smoke smoke 20261003T174232Z" (live, no grant, not deleted) |
| T12 | verified working (staging) | `POST /api/dev/test-fixtures` with `pipeline_deal` (test_s23_pl2_fixtures.py 3 passed); used by the staging spec |

## B1 / T9 · cost before and after (staging, read-only probe, in-process routers)

| | Requests per filter change | SQL statements | Server time |
|---|---|---|---|
| Before (rev 116, main f79a1c7, task 69cd3367) | 7 (clients, opportunities, summary, sync-status, facets, watching count, sync-health) | 42 | 600–692 ms back to back; slowest request 200–280 ms (clients) |
| After (rev 117, s23pl2-b361a77d, task bde99ebe) | 1 (`/pipeline/workspace`) | 7 (8 on the Clients tab with unmatched clients) | 289–351 ms median per call (board 296, page size 100 300, export 303) |

## Deploy record

- Image: `s23pl2-b361a77d`, digest `sha256:02ace77d…2ab5`. Built with buildx for amd64 from b361a77.
- Saved plan: `/tmp/s23pl2-b361a77d.tfplan`, SHA-256 `b2b14012…5bad6a1`.
  - Plan: 12 to add, 14 to change, 12 to destroy. Image-only check: YES.
  - Replaced: 11 task definitions and the migration run (`terraform_data.api_migration`).
  - Changed: the API service (task_definition only), 9 scheduler event targets (ecs_target only) and 4 run-task IAM policies (task-definition ARNs).
  - The summary was shown in chat before applying. The plan was applied from the file, with no prompt.
- Apply: 12 added, 14 changed, 12 destroyed. Migration task `70469fa6` ran 0069 → 0070. Service stable, rollout COMPLETED on rev 117.
- SPA: hashed assets with immutable cache headers; index.html no-cache; CloudFront invalidation `I8Z2T1QJS1YY6PDQD3RBWCKY7G`.
- Smoke: `scripts/deploy-smoke.sh`, run tag `smoke 20261015T005100Z`, GREEN. The gate was clean.

## Reports the directive asks for

- **SOW states (B6, contract `sow_state`).** The nine states the code derives, with their labels: none "No SOW", draft "Draft", in_review_delivery_hr "In review · delivery/hr", in_review_finance_legal "In review · finance/legal", changes_requested "Changes requested", ceo_exception "CEO exception", approved "Approved", awaiting_signature "Awaiting signature", signed "Signed". A deal with several SOWs shows its most recently updated SOW and "+N more".
- **How deals link to several SOWs today (B6).** `sow.opportunity_id` is a non-unique foreign key (S20 D1), but every SOW creation path loads the deal's SOW with `scalar_one_or_none`, so the app never creates a second SOW. Staging has 0 HubSpot deals with a SOW.
- **Pending approvals vs the SOW board (B7).** See decision K3: the card counts deals, while the board counts packages and includes local SOW-upload deals. At discovery the board showed 1 and the Pipeline 0.
- **Next-action route (F11).** `POST /api/next-actions` creates; `PATCH /api/next-actions/{id}` edits, with `expected_revision`, which the editor reads from `GET /api/next-actions?opportunity_id=`.
- **BU counts (B3).** On staging they equal the SQL count of deals by HubSpot region (table above). The discovery-time reference (47/40/22) has moved to 45/39/22 since PL1's syncs.
- **Contract differences.** Every one is listed in `docs/bugs/s23-pl2.md` V1–V18:
  - money as decimal strings;
  - `stage_id` as the stage's position;
  - the additive fields;
  - drills keep the selected stages;
  - focus counts ignore the current filters;
  - activity sort puts nulls last;
  - the extra 422s;
  - the CSV number exemption.
- **Decisions for Kanna.** Presales export (K1), BU scoping (K2), pending vs board (K3), Command Center labels (K4), where Run sync now lives (K5).

## Staging test runs

- `tests/e2e/specs/s23/s23-pl2-pipeline.spec.ts`: **9 passed (3.9 min)** on staging, 2026-10-14 ~18:15 PT.
  - Tonight's situation and T6 page escaping.
  - T2 (six cards).
  - The populated situation.
  - Previews, next-action editor, export, Create in HubSpot and settings.
  - T6 CSV.
  - F3 Run sync now: "Sync started", then "Sync finished · Succeeded"; last success Oct 14, 6:12 PM PT (d1440-sync-run-started.png, d1440-sync-run-finished.png).
  - T8.
  - F3's three states.
  - T10.
- `tests/e2e/specs/s23/s23-pl1-sync-label.spec.ts` and `tests/e2e/specs/command-center-redesign.spec.ts`: 3 passed on staging.
- `scripts/check-test-data-clean.sh`: clean after every run (0 tagged clients, approvers, people, engagements, bot views, groups or watches).
- Local:
  - API suite 2,979 passed, 2 failed: the known `test_auth.py` pair, which fails the same way on untouched main.
  - PL2 API files 314 passed plus 52 on Postgres.
  - Web suite 107 files / 771 tests.
  - Type check 0 errors; no-stubs clean; single-truth gate clean.

## Pre-merge review (before the merge to main, 2026-10-14 evening)

Four independent reviewers covered:
- security and access;
- backend integrity and regressions;
- workspace numbers;
- frontend and the kit.

Each reported only findings it had verified, with a reproduction. Every finding was fixed, with a test that fails on the old code and passes now, before the squash to main. The findings are logged as G16–G29 in `docs/bugs/s23-pl2.md`.

- **Blockers.**
  - Access-token users lost their saved views, groups, watches, preferences, "My opportunities" and next-action edit rights (G16). Fixed by migration `20261014_0071_cognito_sub` and the read path.
  - The Overdue card's denominator was counted on the wrong list (G17).
  - The Command Center open number differed from the list its link opens when filtered by a raw region (G18).
- **Should-fix.**
  - G19: the stricter tile's link.
  - G20: the revenue outlook regression.
  - G21: the owner-sync link could fail the nightly sync.
  - G22: the expired-row 500.
  - G23: the 0070 downgrade.
  - G24: the back-button trap.
  - G25: raw ids in the sync panel.
  - G26: client preview facts.
  - G27: deals with no currency shown as USD.
  - G28: the stale sync baseline.
  - G29: the drilled status.
- **Re-verified.** The reviewers' own reproductions now pass against the fixed code:
  - access-token identity (views, watches, groups, mine, can_edit, preferences);
  - Command Center tile = list for every region;
  - revenue unscheduled note = main.

## Surprises

The second saved view was not a 500 but a 409 from the global integrity handler. The cause was a unique key that treated every custom view as the same key.

HubSpot-created and invited users could not save views, groups or watches at all once foreign keys were enforced, because personal rows were keyed on the login id. SQLite tests never saw it until an FK-enforcing engine was added.

The kit's class merger silently dropped the theme's font sizes app-wide, and the dialog and drawer overlays never dimmed the page (opacity modifiers on `var()` colours). Both were fixed in the kit.

The Command Center's stricter tile and the Pipeline agree on staging today only because no open deal has a SOW or an engagement yet.
