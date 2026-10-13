# S22-P5a — one importer fix and the command-line loader (2026-10-12)

Found during the product owner's click-through of the staging import screen: the ST21 card read **9 clients** where the model has **7**.

1. **Importer fix** (`api/app/services/forecast/forecast_model_import.py`, replaced in this pack — still do-not-modify, take it as given).
   The run-rate dashboard repeats a roll-up block below the grand total — `Client` / `ST21` / `ITA` / `RR` / `Total` (rows 68–72 of the real file). `_parse_dashboard` was reading `ST21` there as a section header and `ITA` and `RR` as two ST21 clients. The parse now stops at the first `Total` row, ignores a second `Client` header, and never treats a business-unit abbreviation as a client.
   Effect: ST21 dashboard clients 9 → 7, total 46 → 44; `ITA` and `RR` no longer appear in "on the dashboard but with no client tab". **No change to engagements, people, allocations or actuals** — those come from the client tabs, and neither phantom name has one. The import screen's cards and the report are the only things that move.
   Proof: `api/tests/forecast/test_forecast_model_import.py::test_the_roll_up_block_below_the_total_is_not_a_client_list` (the synthetic fixture now carries the same trailing block). `python -m pytest api/tests/forecast -q` → **34 passed**.

2. **Command-line loader** (`scripts/load_forecast_model.py`, new): loads the model without the browser, through the same `POST /api/engagements/import-forecast-model`. `--offline` parses locally and writes the report with no server and no auth; the default is a server dry run; `--load` dry-runs, prints the counts and asks once before creating. The workbook holds real staff names and rates: the script never prints a rate, writes its report outside the repo, and the file is never committed — add `*Forecast_Model_Master*.xlsx` to `.gitignore` if it is not there.
   Wire `DEALGATE_TOKEN` to whatever the e2e suite uses for a bearer token; nothing else is needed.

Report items 1 and 2 by number in the five-state vocabulary with proof. No session budget; anti-stuck as before; heartbeat. This rides on `feat/s22-p5` — do not open a new branch, and do not merge until the product owner's click.
