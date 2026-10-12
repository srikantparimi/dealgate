# Forecast engine — drop-in

`compute(engagement, allocations, costs, calendar) -> Forecast`. Pure Python, Decimal, no I/O, no framework imports.
Proven against `docs/reference/forecast-goldens.json` (14 scenarios, totals and month-by-assignment) plus edge tests:
`python -m pytest api/tests/forecast -q` → 18 passed.

Integration contract for the agent:
- Do not modify this file. Feed it rows from the `allocation`, `engagement`, `engagement_cost` tables and a `Calendar` built from `calendar`, `holiday`, `cost_rate_card`, `policy`.
- Margin arithmetic in `Forecast` is simple enough to stay here; if the S11 GM engine must be the one source, call it from the API layer with `Forecast.total_revenue` / `Forecast.total_cost` — never re-implement hours or proration.
- Every API response for a forecast is a serialisation of `Forecast` — add nothing computed elsewhere.
