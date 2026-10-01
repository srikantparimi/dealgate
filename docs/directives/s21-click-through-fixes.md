# Directive S21: product owner click-through findings — fix list

From: Kanna Parimi, product owner. Commit as `docs/directives/s21-click-through-fixes.md` before any code. Work on `integrate/s20` after the Lead checkpoint has pushed. Three sessions, each 75 minutes / 8,000 output tokens, hard stop, rule 16 reporting (every numbered item below, by number, in one of the five states, with proof). No merge to main until I click through again.

## Rule 18 — a click-through finding becomes a test first

Every item below starts with a Playwright test that reproduces my exact path on staging and fails. Then the fix. Then the test passes on staging. Three of the items below were reported "verified working (staging)" in earlier sessions (Staffing & GM as an in-place tab — S19-1b item 6; next-action editor on the deal page — W6 item 1; no raw ids — T09). The tests passed because they did not look where I look. Tests for user-facing items assert on the screen the user sees — breadcrumbs, headers, tabs, buttons — not only on table cells.

## Session S21-1 — SOW workspace and approvals

**1. Delete, not archive, at every state.** Once a SOW is submitted the button becomes "Archive SOW" and does nothing. Reverse D6: a SOW can be deleted at any state, including submitted, in review, approved, signed. Delete means hard delete via `services/deletion.py`, cascading to approvals, versions, GM runs, documents, next actions, comments, renewals, projects created from it, and its row on every page (Pipeline SOW column, Command center counts, My work, Signed handoff). One confirm dialog that names what will be removed. Record the reversal in decisions.md. Archive is removed from the UI.

**2. Staffing & GM renders inside the workspace.** Clicking the tab leaves the workspace for a full page. It must render as tab content like Scope and Approvals, with the readiness panel staying on the right. Regression of S19-1b item 6; the test navigates by clicking the tab and asserts the workspace header and the other tabs are still on screen.

**3. Back navigation in the SOW studio.** From Scope → Staffing → Confirm there is no way back. Every step is revisitable with a Back button and by clicking the step in the gate strip, until Submit. After Submit, editing opens a new draft version (immutable versions — rule); the previous version stays on file; approvals restart on the new version with an audit event saying why.

**4. Overview shows no blanks.** "Owner Unassigned", "Next action Not scheduled", "Commercial type Unknown", "Term 10/12/2026 to April 12th". Rules: Owner defaults to the HubSpot deal owner, else the uploader; it is an inline editor. Commercial type comes from extraction (staff augmentation / fixed price / T&M / managed service) and is an inline editor when extraction is unsure — never "Unknown". Term renders both dates in one format (`Oct 12, 2026 – Apr 12, 2027`). Next action is an inline editor here too. The internal id line (`ID f2033a7a`) goes; the version chips stay.

**5. Approvers visible and editable before submit.** The Approvals tab shows "No reviews submitted" and nothing else before submit. It must show the routing that *will* happen — one row per function with the resolved person — and let the owner change a reviewer before submitting (within the configured group). After submit the same rows show state.

**6. Approver routing — the real people.** Seed in Settings → People & access, as data, not code:

| Function | Approver | Fallback |
| --- | --- | --- |
| Delivery | Shawnna DelHierro — shawnnad@smartek21.com | Srikanth Parimi — srikanthp@smartek21.com, only when Shawnna is marked out of office |
| Sales | Janice Krpan — janicek@smartek21.com | — |
| Legal | Seema Anil — seema@smartek21.com | — |
| Finance | Scott Pfeiffer — scottpf@smartek21.com | — |
| CEO exception (GM below floor) | Al Lalji — al@smartek21.com | — |

Add an **out of office** flag per user (Settings and on the user's own profile) with an optional delegate; routing resolves to the delegate while the flag is set. Sales becomes an approval function. HR stays as a group but is not in default routing (recommendation — flag it in the summary for the product owner to confirm). Replace "Legal: no eligible reviewer. Owner: SystemAdmin" with the seeded routing.

**7. Test users never route a real SOW.** My Liberty Mutual SOW shows "Finance · Queued for E2E Staging Bot". That is the leak gate failing on the approval path: e2e approver users must be ineligible for routing outside a tagged e2e run. Add this to `scripts/check-test-data-clean.sh` (any approval row whose approver is an e2e user and whose SOW has no run tag = failure) and fix the eligibility query. "Submitted by Unassigned" becomes the submitting user's name.

**8. Email to the real approvers.** SES is in sandbox, so mail to the five addresses above is refused until they are verified. Add the five as `aws_ses_email_identity` resources in Terraform (through `scripts/tf-init.sh`, interactive apply answered by Kanna); each person clicks the verification mail once. Report which are verified. Also raise the SES production-access request as a backlog item in `docs/backlog/prod-environment.md` — it is an AWS support request, not a resource change.

## Session S21-2 — Pipeline and deal page

**9. The Clients view ignores the filters.** With Owner = Adil Lalji and Status = Open, the stage chips show 13 deals but the Clients view lists all 187 clients with "Matching / total open 0". When any filter is active, the Clients view shows only clients with ≥ 1 matching deal, sorted by matching count; a toggle "show clients with no match" restores the rest. The tab labels read `Clients (N matching)` / `Opportunities (13)` with N computed by the same query.

**10. Account owner is "Not set" on every client and "No owner" is flagged on all 187.** Mirror the company owner (`hubspot_owner_id` on companies) in the owner mirror and show the name. The "No owner" flag is honest only when HubSpot has no company owner *and* none of the client's open deals has an owner. Report the counts after the mirror: clients with a company owner / without.

**11. Active filters are visible and removable one at a time.** "Clear 2 filters" says nothing about which two. Render a chip per active filter (`Owner: Adil Lalji ×`, `Status: Open ×`) under the bar; × removes that one; "Clear all" stays. Saved views apply the same chips.

**12. Raw identifiers on the deal page.** Breadcrumb reads `Deals › B84f543a 2d9f 4be4 Af22 6176c4646d32` — a UUID as the page title. Pipeline reads `710688094`. Business unit reads `—`. Fixes: breadcrumb = client name › deal name; Pipeline shows the pipeline's name, and the field is hidden entirely when the portal has one pipeline; Business unit is hidden when the property is not mirrored (D10), not shown as a dash; `HS #…` under client names on the Pipeline moves to a hover title, off the visible row. Extend T09 to breadcrumbs, headers, field values and any 9–12 digit token, and run it on every route in the app, not a list of five.

**13. The deal page is read-only where it should be a workspace.** Next action and Latest comment say "when one is created via My Work… it will appear here". Both are inline editors on this page: add / edit / complete a next action with owner and due date; add a comment, pin it. Regression of W6 item 1 — the Playwright test clicks the control on the deal page, not the API.

**14. Alerts per deal.** Beside the watch star: an "Alerts" control with three toggles — stage changes, close date within 14 days, next action overdue — delivered through the existing notification outbox to the watching user. Defaults off. A "Watching" deal with no alerts set is still just a star. Alert sends appear in the deal's Activity.

## Session S21-3 — Staff augmentation term model and extensions

**15. Hours are computed, not typed, for staff augmentation.** A staff-augmentation SOW is a term (6, 12 months…) with N people. Today Staffing & rates requires Hours per row and rejects the row without them. New model, driven by Commercial type:

- Per role row: start date, end date, utilization %, location (US / India), hours per day (default 8), bill rate, cost/hour (from the HR cost band, editable). Hours are **derived** = working days in [start, end] for that location's holiday calendar × hours/day × utilization. Displayed read-only on the row with a "how" tooltip showing the working-day count and holidays excluded.
- Holiday calendars per location as data in Settings (US federal + company days; India national + company days), seeded for 2026 and 2027; editable; a role row shows which calendar it used.
- Default start/end = SOW term from extraction; a row can override.
- Monthly breakdown table under the roster: hours and revenue per month per role, totals, GM per month and overall. The GM engine stays the single engine; this layer only produces the hours it is fed. Golden test: 10 people, US, Oct 1 2026 – Jul 31 2027, 100 %, 8 h/day → hours equal the working-day count for that range minus seeded holidays × 80, asserted to the hour.
- Fixed-price and T&M-by-hour SOWs keep manual hours.

**16. Contract extension.** On a signed or released SOW: **Extend** → new version with a new end date (and optional rate changes); hours, revenue and GM recompute; the version goes back through approvals from Delivery onward with the audit reason "extension to <date>"; the previous version stays signed and in force until the new one is signed; renewals recalculate from the new end date; Projects shows the extended term. Golden test: 12-month SOW extended by 6 months at the same rates → new hours equal the working days of the added months × roster, GM unchanged within rounding.

## Report per session

Scoreboard rows added for items 1–16 (lane S21). Each item by number in one of the five states with its proof (test id + staging rev). Deferred items name what stopped them in one line. Stop at budget. No merge to main.
