# Pure Sourcing Dates

Isolated tree `dealgate-s21-sourcing-dates`, branch `s21/sourcing-dates`, baseline
`f743320` and sourcing contract `556908f`. Own only the pure sourcing module,
new literal tests and this report. No persistence, routes, UI or infrastructure.

## API Contract

`validate_rules(list[dict])` validates and returns copied rules with exact fields
`skill`, `location`, `lead_days`. Keys are normalized nonblank strings; `*` is
the explicit skill wildcard. Lead days are nonnegative integers, not booleans
or floats. Duplicate skill/location rules reject.

`prepare_sourcing(intervals, rules)` consumes the serialized internal named
`people_allocation` interval rows and returns `rows`, `missing` and
`is_reservation=False`. Each output row is cost-free and excludes all person
IDs/matches and financial/probability fields. Source metadata is explicitly
allowlisted. Dates (`start`, `end_exclusive`, `sourcing_by`) are ISO strings;
`gap_fte` remains an exact Decimal, for the service's explicit string encoder.

Output counts: `quantity`, `retained_quantity`, `incremental_quantity`,
`matched_quantity`, `gap_quantity`, `continuity_gap_quantity`,
`incremental_gap_quantity`. Unmatched retained slots require continuity review;
they do not become incremental hiring. `sourcing_by` exists only for a positive
incremental gap and complete skill/location rule coverage. Exact skill rules
override the same-location wildcard. Across required skills, the greatest
effective lead time wins. Dates subtract calendar days from each actual gap
interval start; no suggested rule is silently activated.

Missing capability and rule coverage remain explicit. Malformed input, invalid
dates/counts/Decimal values or inconsistent allocation totals must reject, not
become zero. Named matches are needed internally to classify continuity; a
redacted match list cannot establish hiring counts. Named continuity missing
reasons are reduced to `continuity_unresolved` before output.

Implementation uses exact rational comparisons for allocation consistency,
independent of the ambient Decimal precision. The original exact Decimal gap
is preserved. Duplicate named matches, inconsistent counts/FTE, invalid
continuity booleans, malformed normalized keys, invalid/overflowing dates and
overlapping/out-of-order intervals reject. Unknown input financial fields are
ignored by the output allowlist. Missing reasons cannot echo named identities.

## Local Proof

Tests were authored before implementation. First permitted runtime reproduced
missing-module collection failure. Final run: **45 passed in 1.78s**, comprising
29 new sourcing cases and 16 unchanged allocation cases; no skips or xfails.
No processes remain; runtime released to integration lead.

Literal fixtures verify two US and five India incremental slots remain seven
people at 70% probability. November 1 starts with saved 45/30-day rules produce
September 17 / October 2 respectively. Another fixture has seven total slots,
two retained, five incremental, three matches: one continuity gap and three
incremental gaps remain separate. Leap-year, empty skills, partial rule
coverage, exact-over-wildcard precedence, longest required-skill lead time,
zero gap, zero-day rule, Decimal precision and invalid inputs are covered.

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-sourcing-dates/api
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_sourcing_dates.py tests/test_s21_demand_allocation.py -q -o addopts= -p no:cacheprovider --tb=short
```

This is not sourcing persistence, a reservation, a hire or FC-07 completion.
Immutable versions, CAS, trusted scopes, rule permissions, source-watermark
binding, idempotent drafts, API/browser and staging proof remain lead-owned.
