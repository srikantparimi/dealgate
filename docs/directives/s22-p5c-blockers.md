# S22-P5c — the import refuses rather than guessing (2026-10-12)

The agent found that the service files an engagement with no dashboard business unit under ST21 (`engagement_forecast.py:2253`), following the prototype's `bu || "ST21"`. Both are mine. It is the worst kind of wrong: ST21 silently absorbs 8 engagements, 46 people and ~3.0M of forecast, the subtotals still add to the grand total, and nothing on screen says anything happened. The same is true of a blank Location — the row lands on US burden and the US floor, and only the margin underneath is wrong.

A blank cell in the workbook is not a judgement call, so the tool stops and names it. **No default, no override.** If a client genuinely belongs somewhere, the dashboard is where that is said, and it is two cells.

1. **Importer** (`api/app/services/forecast/forecast_model_import.py`, replaced; still do-not-modify).
   `MasterImport.blockers` is a list of `Blocker(kind, tab, detail, rows)` with a `.fix` sentence naming the cells and the people. Two kinds: `business_unit` (the tab has engagements but no run-rate dashboard row) and `location` (people with no Location). `dry_run_markdown` leads with them, above the as-of line. On the current master: 7 blockers — UEBIZ and Children's Hospital-VMS with no BU, and 26 people with no location across Liberty Mutual, UEBIZ, Caesars, Caesers Entertainment and First Citizens.
   Proof: `test_a_workbook_that_does_not_say_where_people_belong_blocks_the_load`, `test_a_complete_workbook_has_no_blockers`, `test_the_report_leads_with_the_blockers` (the synthetic fixture gained a "Zeta Unlisted" tab that is on no dashboard and has one blank-location row). `python -m pytest api/tests/forecast -q` → **39 passed**.

2. **Service** (`engagement_forecast.py`, yours).
   - Delete the `|| "ST21"` default. Nothing assigns a business unit the workbook did not state.
   - Dry run: return `blockers` alongside the report (`[{kind, tab, detail, rows, fix}]`); it still creates nothing and still returns 200 — a dry run is how you find out.
   - Load (`dry_run=false`) with any blocker: **422**, body `{blockers: [...]}`, nothing created, no partial write. Add it to the contract as the second 422 case on `POST /engagements/import-forecast-model`.
   - The CLI already surfaces a 422 body; check it prints each blocker's `fix` on its own line.
3. **Import screen** — as the prototype (v5, in this pack). When `blockers` is non-empty the Load button is replaced by the panel "Fix these in the workbook before loading": one row per blocker, the detail, the fix beneath it in small type, and a disabled Load button with "N things to fix · re-upload when the workbook carries them". The panel renders the API's blockers verbatim; the prototype's own browser-side parse is approximate and is **not** the source of the list.
4. **Playwright**: upload the synthetic fixture (it now carries Zeta Unlisted) → the panel lists both blockers and Load is disabled → a `dry_run=false` call made directly returns 422 and creates nothing.

Report items 1–4 by number in the five states with proof. No budget; anti-stuck; heartbeat. Rides on `feat/s22-p5`; no merge until the product owner's click.
