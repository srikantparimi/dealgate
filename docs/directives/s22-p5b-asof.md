# S22-P5b — as-of is a parameter, not a global (2026-10-12)

The agent found it while answering a question about defaults: `parse_master` kept `as_of` in a module global and rewrote it on every call, so one request asking for a different month changed what "actual" meant for every later request in that worker. On staging it happened to read 2026-09 because every caller so far sent that or nothing. That is luck, and luck does not belong under a forecast.

Fixed at the source rather than pinned down in the service, so the next caller of the importer cannot hit it either.

1. **Importer** (`api/app/services/forecast/forecast_model_import.py`, replaced; still do-not-modify).
   - The global is gone. `as_of` is threaded through `_parse_tab` as a parameter. `parse_master(src, as_of=None)` resolves `None` to the module constant `MODEL_AS_OF = "2026-09"`, which is never reassigned.
   - `MasterImport.as_of` carries the value, and the report's first line now states it: *"Actuals are taken through 2026-09; every later month is forecast."* No one has to ask what a load meant.
   - `MODEL_AS_OF` is the one place to bump when a newer model cut arrives (e.g. the 12.31.26 master → `"2026-12"`).
   - Proof: `test_as_of_is_per_call_and_never_leaks_between_imports` (a parse at 2025-10 followed by a default parse; the default still ends at 2026-02 on the fixture, and `MODEL_AS_OF` is untouched) and `test_the_report_says_which_month_the_actuals_run_to`. `python -m pytest api/tests/forecast -q` → **36 passed**.

2. **Service** (`engagement_forecast.py`, yours): keep passing the request's `as_of` straight through, and when it is absent pass `None` — do not read `forecast_model_import._AS_OF` (it no longer exists) and do not hard-code the month in the service. One constant, one meaning.

3. **CLI** (`scripts/load_forecast_model.py`, replaced): `--as-of` no longer defaults to today. Left out, the flag is not sent and the importer's `MODEL_AS_OF` applies, so a forgotten flag can never import an unbilled month as actuals. The flag stays for the day a model cut to a different month needs loading.

Report items 1–3 by number in the five states with proof. No budget; anti-stuck; heartbeat. Rides on `feat/s22-p5`; no merge until the product owner's click.
