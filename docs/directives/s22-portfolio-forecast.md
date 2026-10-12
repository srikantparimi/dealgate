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

Later, not now: what-if scenarios (clone, edit, compare, promote), forecast vs actuals from timesheets/invoices, AI adviser "what rate clears the floor". Each is a short directive against the same engine.
