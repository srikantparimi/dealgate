# Directive S22 — Portfolio & Forecast: wire the approved screens to the finished engine

From: Kanna Parimi, product owner. The thinking is done and approved; this is integration. Three artefacts are the spec, in this order of authority:

1. `api/app/services/forecast/__init__.py` — the engine. Finished, pure, Decimal. **Do not modify.** `api/tests/forecast/` proves it against `docs/reference/forecast-goldens.json` (14 scenarios, totals and month-by-assignment, to the cent). If an integration test disagrees with the engine, the integration is wrong.
2. `docs/reference/prototype/dealgate-portfolio.html` — the approved screens, clicked through by the product owner. Copy the layout, columns, labels, states and interactions exactly; restyle only to the existing DealGate design tokens. Its JavaScript `compute()` is a mirror of the engine for the browser; the real pages call the API.
3. `docs/reference/openapi-forecast.yaml` — the contract. Every forecast response is a serialisation of `Forecast`; nothing is computed outside the engine.

The cost-margin workbook (`docs/reference/DealGate_Cost_Margin_Sheet.xlsx`) is the base all three came from: every field on it exists in the screens and the contract. Where any of the three is silent, the workbook decides.

Process: branches off `main` (`feat/s22-p1` … `feat/s22-p3`), one 90-minute session each with a hard stop; **deploy via D5 starts at minute 55 regardless**; staging tests; scoreboard; report every numbered item by number in one of the five states with proof (rule 16); heartbeat (rule 19); merge after staging proof and the product owner's click (rule 14). Scoreboard rows S22-P1-1 … S22-P3-6 added in the first commit of P1.

## P1 — engine in, data in, API out

1. Commit this pack. `python -m pytest api/tests/forecast -q` → 18 passed, on CI Postgres, before anything else.
2. Migrations: `engagement`, `resource`, `allocation` (with `superseded_by`), `engagement_cost`, `calendar_location`, `holiday`, `cost_rate_card`, `forecast_policy`, `forecast_run` — columns as in the OpenAPI schemas; indexes on (engagement_id, start, end), (resource_id, start, end), (superseded_by). Seed `calendar_*` from the workbook's Settings tab (US W-2 36 %, US 1099 5 %, India 8 %, floors 35/50, project floor 35, hours/day 8, rate card placeholders, holidays). Clients come from the HubSpot company mirror plus `POST /clients` for manual ones.
3. A thin mapper: DB rows → engine dataclasses → `compute()` → `Forecast` → JSON per the contract. No arithmetic in the mapper. `forecast_run` stores the JSON with a hash of its inputs; a changed allocation or calendar invalidates it.
4. Endpoints exactly as the contract: engagements, clients, allocations (incl. `/close`, `/rehire`, supersede-on-rate-change), costs, `/engagements/{id}/forecast`, `/portfolio/forecast`, `/settings/forecast` GET/PUT. Validation messages are the engine's `missing` strings, verbatim.
5. Contract test: the Client A golden seeded under the e2e run tag, `GET /engagements/{id}/forecast` equals the goldens' expected totals and month-by-assignment rows; teardown; leak gate 0.
6. Importer: `POST /allocations/import` accepting the workbook's staffing table as CSV (its column headers), so current spreadsheets load without retyping.

## P2 — the engagement screens

1. `/engagements/{id}` with tabs Allocations · Forecast · Setup & costs, as the prototype. Allocations grid: same columns, yellow editable cells, cost/hour pre-filled from the rate card, dates pre-filled from the engagement, row actions Leaves / Re-hire / remove, totals row, Row GM red under the resource floor.
2. Forecast tab: status line (PASS / BELOW FLOOR / INCOMPLETE with the numbers), location-check pills, all-resources block, one block per assignment, per-person revenue by month; "monthly required" text by duration.
3. Setup & costs: the project block (client, name, owner, currency, type, dates, price or fee, additional-costs Y/N, same-dates Y/N) with type-driven greying; additional costs with frequency and billed-to-client required.
4. New engagement page with "+ New client…"; a Closed-Won HubSpot deal offers "Create engagement from deal" pre-filled.
5. Settings page: hours/day, project floor, burden and resource floor per location, add location, rate card, holidays — `PUT /settings/forecast`.
6. Playwright on the product owner's path: new engagement → five people → one leaves → re-hire → Forecast shows the gap month at zero → Settings change to burden moves the numbers.

## P3 — portfolio

1. `/portfolio` page as the prototype: month picker, type and client filters, the table, totals before pagination.
2. The four cards through the single query service — portfolio GM for the month, below floor, roll-offs in 60 days, bench — each deep-linking to the list that produces it, count equal to the list.
3. Roll-offs and bench panels with names, never ids.
4. Renewals: MSP and staff-aug engagements ending within two calendar months raise the existing renewal item (D8).
5. Nightly alert through the notification outbox: roll-offs and below-floor engagements to the account owner.
6. Reconciliation test: portfolio month total == Σ engagement forecasts == Σ allocation-month rows; CSV export of any portfolio view.

## P4 — fixes from the product owner's first click-through (2026-10-12)

1. Engine update in this pack: one-time additional costs now spread across the term by share of month, like a fixed price (was: all in month 1). Pull the new `api/app/services/forecast/__init__.py`; the 18 goldens still pass; no API change.
2. Short engagements (duration ≤ 2 months): the Forecast tab shows the whole-term summary first and hides the month split behind "Show month split". The prototype has it.
3. Portfolio table: month columns are labelled with the month ("Revenue · Oct 2026"), "GM % · whole term" for the term figure; subtitle explains that month columns are that month's slice.
4. **Upload the sheet.** `POST /engagements/import-workbook` per the contract, using `api/app/services/forecast/workbook_import.py` (finished; `api/tests/forecast/test_workbook_import.py` proves it on the sample, the blank template and the product owner's own older copy in `fixtures/`). New-engagement page gets the upload box above the form, as the prototype. The response's `hours_check` is shown on the engagement header once ("Sheet said 168 h for Vikrin; app computes 160 — Labor Day"). CSV import stays.
5. Per-person rows on the Forecast tab for fixed-fee types show hours (they do), labelled as such.

## P5 — business units, the forecast-model master, actuals (2026-10-12)

The company reports across three business units (ST21, IT Avalon, Retro Rabbit) and today runs its forecast in `ST21_FY2526_Forecast_Model_Master` (one tab per client, one row per person, month blocks). P5 brings that model into DealGate so the Portfolio page replaces the master. Everything that needed thinking is finished in this pack; this is plumbing.

1. **Engine update** (`api/app/services/forecast/__init__.py`, finished, do not modify): `Allocation.rate_basis` (hourly | daily | monthly), `Allocation.person`, `cost_per_hour=None` → "cost per hour unknown" → INCOMPLETE; `Actual(allocation_id, month, hours, revenue)` passed as `compute(..., actuals=[...])` → `MonthLine.actual_hours / actual_revenue / billing_loss`, `Forecast.actual_revenue / forecast_in_actual_months / billing_loss`; MSP with no fee bills the people's monthly rates. `python -m pytest api/tests/forecast -q` → **33 passed** before anything else.
2. **Migrations**: `engagement.business_unit` (not null, enum ST21 / IT Avalon / Retro Rabbit), `engagement.sales_owner`, `engagement.delivery_owner` (text), `engagement.closed` (bool, default false); `allocation.rate_basis` (default hourly), `allocation.person`; new `allocation_actual` (allocation_id, month, hours, revenue; unique on allocation_id+month). Existing engagements backfill `business_unit='ST21'`.
3. **Contract v1.1** (`docs/reference/openapi-forecast.yaml`): the fields above on Engagement/Allocation; `PUT /allocations/{id}/actuals`; `POST /engagements/import-forecast-model` (multipart; `dry_run` default true); `GET /portfolio/forecast?business_unit=` and the `groups` block + `cards.billing_loss`. Mapper passes actuals into `compute()`; no arithmetic outside the engine.
4. **Importer** (`api/app/services/forecast/forecast_model_import.py`, finished): `parse_master(file, as_of)` → `MasterImport`; `to_engine(engagement, cal)` → engine inputs + actuals; `dry_run_markdown(imp, cal)` → the report. `api/tests/forecast/test_forecast_model_import.py` (synthetic fixture built in the test, same layouts as the real model) proves it. The endpoint: dry run returns the report and creates nothing; load creates clients (manual), engagements (closed flagged), allocations (`cost_per_hour` null, `rate_basis` and `person` from the importer), actuals, and holidays for locations the calendar lacks; idempotent on (client, assignment_key, person, segment). Locations arrive as "US", "India - Pune", "India - Chennai", "South Africa" — add these to `calendar_location` on first import (burden: US W-2 36 %, India 8 %, South Africa 8 % placeholder; floors 35/50/50/35) and say so in the report.
5. **Portfolio page**: BU tabs above the cards — All business units / ST21 / IT Avalon / Retro Rabbit — with URLs `/portfolio`, `/portfolio/st21`, `/portfolio/it-avalon`, `/portfolio/retro-rabbit`. "All" groups rows by BU with a subtotal row per BU and a grand total; a BU tab shows its rows and subtotal only. Cards follow the selected tab. Fifth card "Billing loss · months with actuals". Closed engagements are off the page (visible in the engagement list marked closed). Owners under the engagement name. As the prototype (v4).
6. **Engagement screens**: Setup gets Business unit, Sales owner, Delivery owner, Status (Active / Closed). Allocations grid gets Person (first column) and "per" (hourly / daily / monthly) next to Bill rate; the Bill-rate columns also show for MSP engagements with no monthly fee. Forecast tab gets the Actuals block (Billed, Actual hours, Billing loss) when any month has actuals. New-engagement page gets Business unit and owners.
7. **Import screen** at `/import/forecast-model` (nav: "Import the forecast model"): upload → dry run (the BU cards, the per-tab table, the report markdown rendered) → "Load …" button → load → lands on `/portfolio`. As the prototype.
8. **Playwright**, product owner's path: upload the synthetic fixture (`api/tests/forecast/fixtures/forecast_model_synthetic.xlsx`, generated by the test) → dry run shows 3 BUs → load → `/portfolio/it-avalon` shows Gamma Health-VMS → its Forecast tab shows the Actuals block → `/portfolio` shows three subtotal rows that add to the grand total.
9. **Reconciliation test** extended: BU subtotals == Σ their rows; grand total == Σ subtotals; `cards.billing_loss.engagements` == count of rows with actuals.

Rules for the agent (every prompt restates them): no session budget; anti-stuck — one bounded attempt per issue, then log it in `docs/bugs/s22-p5.md` and move on; code-complete first, then test and fix the logged bugs one by one; report items 1–9 by number in one of the five states (verified working on staging / fixed and tested / missing / blocked / deferred) with proof; heartbeat at every step and at least every 15 minutes.

Later, not now: what-if scenarios (clone, edit, compare, promote), AI adviser "what rate clears the floor", timesheet/invoice feeds that write actuals automatically. Each is a short directive against the same engine.
