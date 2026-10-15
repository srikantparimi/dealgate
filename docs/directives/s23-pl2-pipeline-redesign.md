# S23-PL2 — Pipeline page redesign, built on real data

Branch `feat/s23-pl2` from main (staging runs main 6a3c63f). **Start only after Kanna has clicked and approved the prototype.** PL1 (sync trust) merges first; rebase onto main after it merges.

Source of truth, in this order: (1) this file, (2) `docs/reference/openapi-pipeline.yaml`, (3) `docs/reference/prototype/dealgate-pipeline.html` (approved clickable prototype: behaviour, information and copy; open it, use both its "Work data" modes and all three "Sync" states). Build with the app's own component kit and tokens, not the prototype's CSS. Do not redesign. Any deviation goes in `docs/bugs/s23-pl2.md` with the reason.

The discovery report (S23-PL0, `/tmp/pipeline-discovery-*.md`) is the factual base. Its numbers at discovery time (PL1's first sync has refreshed 74 deals since, so re-read them before you compare): 109 open deals, USD 21,596,444.14, 0 missing amount/owner/BU/client, Hold counts as open (2 deals), 8 past their close date, 61 with no activity date, every open deal "No SOW", 0 agreements, 0 next actions.

## Rules (they apply every time)

1. **No session token or time budget. Do not get stuck.** One bounded attempt per issue; if it does not yield, log it in `docs/bugs/s23-pl2.md` with what you tried and move on. Finish ALL fundamental code first (code-complete: every B and F item), then test, then fix the logged bugs one by one, each recorded in the file. Efficient and quick.
2. **Anti-glossing.** Report **every** numbered item (B1–B15, F1–F20, T1–T12, D-items) by its number in exactly one of five states: **verified working / fixed and tested / missing / blocked / deferred**, each with proof (test name and result, request and response, screenshot path, or file:line). A "complete" or "zero deferrals" summary may not replace the list. An item missing from your report counts as not done. "Deferred" needs my agreement in the item text, so only D-items marked DEFERRED may use it.
3. **Heartbeat.** One line at every step boundary and at least every 15 minutes while a long command runs: `PL2 · item · result · next`.
4. CLAUDE.md applies: rule 12 no infra via console or CLI, rule 14 branch → staging → smoke → Kanna's click → squash merge, rule 15 never a scripted-yes terraform, rule 17 parallel lanes, rule 18 any click-through finding becomes a failing Playwright test first. Deploy exactly the way PL1 did: an image-only Terraform roll applied from a saved plan (show me the plan summary; if it contains anything other than the image, stop and ask), then run `scripts/deploy-smoke.sh`, which only smoke-tests. Never a scripted yes. HubSpot token is test-only, never printed, committed or reused. **No Terraform change is needed here. If you think one is, stop and ask.** Database migrations go through the normal release path.
5. Test data stays under run tags and the leak gate. Never render a raw id. Never invent a number: a missing value shows its reason, never a zero.

## Disposition of the discovery findings

Each line says what happens. A line marked BUILT points at the items that do it.

| # | Finding | Disposition |
|---|---|---|
| D1 | Client sector has no source | **CUT.** Not shown. |
| D2 | Per-deal alerts (stage change, overdue, 14 days quiet) have no storage, trigger or notification type | **DEFERRED to phase 2.** Prerequisites: SES sending works (23 failed, permission error) and SES production access; Kanna chose email delivery. Do not build any alert UI. |
| D3 | Deals carry HubSpot regions, not ST21 / IT Avalon / Retro Rabbit | **BUILT:** B3, F7, F18. South Africa is Retro Rabbit. Both "US - IT Avalon" values are IT Avalon. "US" is ST21. US holds two different BUs, so a BU is never shown without its region. |
| D4 | NDA / MSA states beyond "on file" have no source | **CUT.** Show "on file" or "missing" only. |
| D5 | SOW state "Scope & GM" has no source and clashes with the SOW board | **CUT.** Use the real states the code derives (nine). |
| D6 | "My opportunities" has no user ↔ owner link | **BUILT:** B4, F6. |
| D7 | "On hold" as a status | **BUILT** as a stage filter: B5. |
| D8 | Five metric parts (accounts, amount counts, closing value, unset count per stage, client total) | **BUILT:** B1, B7. |
| D9 | Agreement-gap drill-down; NDA/MSA on deal rows | **BUILT:** B6, F4, F8. |
| D10 | Search over next-action text | **BUILT:** B6. |
| D11 | Page sizes 6 and 12 are rejected by the API | **CUT.** 25 / 50 / 100 only. |
| D12 | Deal sort by name; client sort by value or close | **BUILT:** B6. |
| D13 | Clients export; seven missing deal export columns; no currency conversion | **BUILT:** B10 (a Currency column, no conversion). |
| D14 | Stored but never returned: created date, next-action text on rows, account owner and agreements on deal rows, pipeline name | **BUILT:** B6. |
| D15 | "12 days old" measures a frozen heartbeat | **PL1 + BUILT:** B15, F3. |
| D16 | Webhooks would reopen closed deals | **PL1.** Not touched here. |
| D17 | "No owner" is a Clients-tab artifact (flags 153 clients with no open deal; archived HubSpot owners on closed deals) | **BUILT:** B13. |
| D18 | Controls that do nothing today ("Missing: next action", "Action due" date field, five built-in views) | **BUILT or removed:** B7, F6, T8. Every control changes the list or is absent. |
| D19 | Same word, different numbers (overdue and pending count actions and packages; lists count deals); dates UTC while the page says Los Angeles | **BUILT:** B7, B8. |
| D20 | CSV formula injection in two exports; Sales-only users get an access error on client pages; Presales cannot export | **BUILT:** B10, B12. Presales export stays as it is (policy, Kanna's call). |
| D21 | Hold counts as open everywhere | **KEPT and labelled:** B5, F8. |
| D22 | Nightly sync fragile | **PL1.** |
| D23 | Personal-workspace backends have no UI; a second saved view fails | **BUILT:** B11, F12. |
| D24 | Leak gate sees only the bot's fixtures; one leftover test client tonight | **BUILT:** T11 (report the leftover, do not delete it). |
| D25 | Test bot sees no real deals; fixture deals have no stage or amount | **BUILT:** T12. |
| D26 | No email ever sent from staging | **DEFERRED to phase 2** with D2. |
| D27 | Page costs six requests and about 35 queries per filter change | **BUILT:** B1. |
| D28 | HubSpot portal id hard-coded in three web files | **BUILT:** B14, F19. |
| D29 | HubSpot notes not copied into the app | **DEFERRED.** Out of scope. Internal notes are not on this page. |
| D30 | The Command Center calls the Pipeline's query code directly; its tile uses a stricter definition | **BUILT:** B2. |
| D31 | Agreements, next actions, comments, watches, groups are empty on staging; every deal is "No SOW" | **Expected.** The UI must look right empty (F8) and populated (T12). |

## Backend items

**B1. One request.** Implement `GET /api/pipeline/workspace` per the contract. One response carries freshness, metrics, stage counts, focus counts and the rows for the active tab. Measure database queries and latency per call before and after on staging and report both. Target 8 queries or fewer. Leave existing endpoints that other pages use. The Pipeline page stops calling the other five.

**B2. One definition of "open", shared.** One filter function serves the workspace, the export and the Command Center. The Command Center tile "Open opportunity value" becomes the Pipeline's own open number (109 deals, USD 21,596,444.14 tonight). The stricter variant (USD only, weighted, no SOW or engagement link) stays but gets its own label, e.g. "Not yet in the SOW flow". Regression-test every Command Center tile you touch.

**B3. Business unit.** Table mapping HubSpot region value → business unit, region, note. Seed: `South Africa` → Retro Rabbit, South Africa; `US - IT Avalon (Staffing)` → IT Avalon, US, note Staffing; `US - IT Avalon` → IT Avalon, US; `US` → ST21, US. `GET/PUT /api/settings/business-units` (admin write). Deal rows return `business_unit`, `region`, `region_note`, the raw `hubspot_region` and `bu_unmapped`. The `bu` filter accepts the three BUs and `unmapped`. Editing the mapping takes effect with no resync. Report the resulting deal counts per business unit on staging and confirm each equals the SQL count of deals by HubSpot region. (At discovery time, before PL1's first sync refreshed 74 deals, they were Retro Rabbit 47, IT Avalon 40, ST21 22; staging numbers may have moved since, so they are a reference, not a target.)

**B4. User ↔ HubSpot owner.** Nullable `hubspot_owner_id` on the user. Link automatically by exact email match (at login and at owner sync); admin override at `PUT /api/users/{id}/hubspot-owner`. `mine=true` filters on it. No link → `focus.mine_available=false`.

**B5. Status semantics.** `open` = not Closed Won and not Closed Lost, so it includes Hold. `hold` = stage Hold. `metrics.open_value_usd.includes_on_hold` reports the count.

**B6. Row fields and sorts.** Deal rows: everything in `DealRow`, including created date, next action text and due date, account owner, agreements, SOW state (the real nine, labelled; a deal with several SOWs shows the state of the most recently updated one plus `sow_count`, and the row shows "+N more"; report how deals with more than one SOW are linked today), flags. Client rows: `ClientRow`. Sorts `value | close | activity | name` work on both tabs; nulls last. `q` searches deal name, client name, deal owner name and next-action text.

**B7. Metric definitions.** Exactly as the contract's `Metrics` text. Each metric returns `drill`; applying `drill` to the current filters must return a list whose length equals the metric value (deals for the deal metrics, clients for `agreement_gap_clients`). Confirm `pending_approvals` against the SOW board's meaning of pending and report any difference. Every filter and focus view in the old page either works or is removed (D18).

**B8. Dates.** `date_preset` per the contract, relative to today in America/Los_Angeles, calendar dates only, no UTC drift. Test across a month end, a quarter end and a DST change.

**B9. Paging and board.** Page sizes 25 / 50 / 100; anything else returns 422 naming the allowed sizes. `layout=board` returns per-stage totals and at most 6 deals per lane.

**B10. Export.** `GET /api/pipeline/export` per the contract: every filtered row, both tabs, listed columns, Currency column, UTF-8 with BOM. Neutralise cells starting `=`, `+`, `-`, `@`, tab or CR with a leading apostrophe, **in this export and in the two existing CSV exports** (`reports.py:803` and the other).

**B11. Personal workspace.** Saved views, groups and watches work through the canonical DealGate user id (they are keyed on the login id today, which differs from the database id for HubSpot-created users; fix it, migrate existing rows, test with a HubSpot-created user). Find and fix the root cause of the second saved view failing. Names are unique per user, case-insensitive; a duplicate returns 409. Groups and watches key on the stable deal id.

**B12. Access.** Sales-only users can read client pages and the Pipeline's client tab without an error. Presales export is unchanged; add it to the bugs file as a decision for Kanna. No BU scoping is added (Kanna's call; list as deferred in the bugs file).

**B13. Owners.** Owner objects carry `state` active | archived | none. "No deal owner" is a flag only on **open** deals. A client with no open deals is never flagged. Archived owners display as "Former HubSpot user".

**B14. Portal id.** `GET /api/config` returns `hubspot_portal_id` from the configuration Terraform already provides. No infra change.

**B15. Freshness.** `workspace.freshness` reads PL1's sync-health (PL1 is built; rebase onto main once it merges). Freshness comes from run records only, never the intake heartbeat.

## Frontend items

**F1. Replace the Pipeline page** with the prototype's structure, behaviour and copy, using the app's components and tokens. Map the prototype's colours onto existing tokens. Use the app's existing light and dark themes; build no theme toggle of your own.

**F2. One data hook.** `useWorkspace(filters)` makes one request, cancels a stale one, debounces search by 300 ms, and keeps every filter in the URL query string so a link or the back button restores the view. A saved view stores that same shape.

**F3. Freshness line.** Three states with the prototype's copy: fresh (quiet), stale (amber), failed (red, naming the last good sync). "Inspect sync" opens the details panel. Times in America/Los_Angeles. The admin "Run sync now" action returns before the sync finishes (CloudFront times out at 30 seconds while the sync completes on the server): show "Sync started", poll `sync-health`, and never show that timeout as a failure.

**F4. Metric cards.** Six cards. A click applies the card's `drill` to the current filters and opens the list. The number on the card equals the list length. Agreement gaps opens the Clients tab. When no client anywhere has a file, the card says "no agreement files uploaded yet".

**F5. Stage navigator.** Nine stages, all-status overview. Selecting a stage sets status to All and remembers the previous status; clearing the last stage restores it.

**F6. Focus views.** All open, Closing this month, My opportunities (with the unlinked hint), Needs attention, Watching. Counts come from `focus`.

**F7. Filters.** Search, status (Open includes on hold; On hold only), Deal owner on the Deals tab and Account owner on the Clients tab, Business unit (three options, each with its region; a note that US holds two BUs), Date dialog with the prototype's preset list, More filters (SOW state, attention, missing information, group, watching). Every active filter is a visible, removable chip.

**F8. Deals list and empty states.** Columns and tags as the prototype. BU always with region. Empty states exactly as the prototype shows for tonight's data: "Set next action", "No activity recorded", "No SOW", NDA / MSA "missing". Unmapped region note links to Settings. Hold labelled in the Open value card.

**F9. Clients tab.** Account owner filter, sorts, "include clients without matching deals", flags as B13.

**F10. Board.** Lanes show at most 6 cards and "Show all N in list".

**F11. Preview panel.** Deal and client previews as the prototype. The next-action editor writes to the **existing** next-action endpoint (report its route). Watch toggle. No alerts, no notes.

**F12. Collections.** Saved views, tracking groups, watching, all real and per user. Saving a second view works; a duplicate name shows the message.

**F13. Bulk selection** bar: watch selected, add to group.

**F14. Export button** calls the export endpoint for the active tab with the current filters and downloads every row.

**F15. Escaping.** Every HubSpot-sourced string renders as a text node. No `dangerouslySetInnerHTML` on this page; add a lint check or test that fails if one appears.

**F16. Phone layout.** At 375 px: no horizontal scroll; the list becomes stacked cards as in the prototype; the views panel opens from the "Views & groups" button.

**F17. Accessibility.** Dialogs trap focus and close on Escape; toggles use `aria-pressed`; every control has a label; keyboard order is sensible.

**F18. Settings screens.** Settings → Business units (edit the region mapping; shows unmapped values with deal counts). Settings → Users: HubSpot owner link with an auto-match indicator and an admin override.

**F19. Create in HubSpot** uses `hubspot_portal_id` from config. The three hard-coded copies are gone.

**F20. Not built, verify absent:** alert controls, notes on this page, client sector.

## Tests

Write them first for any bug you find (rule 18). All run in the existing Playwright and API suites.

**T1. Reconciliation.** On staging data: Pipeline open count and value = Command Center "open opportunity" tile = SQL with the page's rules (109 and USD 21,596,444.14 tonight, or the current equal numbers).
**T2. Metric = list.** For each of the six metrics, across at least 50 combinations of other filters (API level), applying `drill` returns a list whose length equals the metric. Playwright repeats it for the six cards on the page.
**T3. BU mapping.** Unit test for all four values plus an unmapped one; Settings edit changes deal rows immediately.
**T4. User link.** Email match, admin override, unlink, a HubSpot-created user; `mine=true` results.
**T5. Personal workspace.** Views, groups and watches for a HubSpot-created user; second and third view save; duplicate name 409.
**T6. Escaping and CSV.** A deal and client whose names contain `<img src=x onerror=...>` and `=HYPERLINK(...)`: nothing executes, text shows literally, all three CSV exports prefix the formula cell.
**T7. Dates.** Frozen clock at a month end, a quarter end and a DST change, in America/Los_Angeles, for every preset.
**T8. Controls.** Every control on the page either changes the list or does not exist (covers D18). Stage navigator restores status.
**T9. Cost.** Query-count and latency budget on the workspace endpoint, reported before and after.
**T10. Layouts.** Playwright at 375 px (no horizontal scroll) and 1440 px; light and dark; screenshots saved outside the repo.
**T11. Leak gate.** Extend `check-test-data-clean.sh` to cover saved views, groups and watches created by the e2e bot. Report the one leftover test client; do not delete it.
**T12. Fixtures.** Run-tagged fixture deals with stage, amount, region, owner, next action, SOW state and an agreement file, so the specs exercise populated rows. The bot still may not create real clients.

## Done means

Every numbered item above reported by number in the five states with proof; staging deployed by an image-only roll from a saved plan, then smoke green via `scripts/deploy-smoke.sh`; screenshots of the three sync states and both data situations; the before and after query counts. **Do not merge.** Kanna clicks through staging first.
