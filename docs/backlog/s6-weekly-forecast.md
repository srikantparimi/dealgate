# S6 E9 — Weekly forecast update (remaining hours per resource line)

## User story
As Delivery lead, once a project is Released → Active, every week I update
each resource line with `remaining_hours`. The system computes forecast
cost + forecast GM from the remaining hours × loaded cost and shows the
delta vs the approved GM sheet on the Deal detail. If forecast GM drops
below the floor, a recovery task is filed and appears on the CEO view.

## Acceptance tests
- Given a released package with 5 resource lines, when I POST `/forecast/{gm_model_id}` with `{lines: [{resource_line_id, remaining_hours}]}`, then a new immutable `forecast_period` row is created with week ending today; audit `forecast.updated`.
- Given forecast_gm < policy_floor, then a `recovery` task is filed for the Delivery lead + notification queued.
- Given I try to update a project that isn't Active, then 409.
- Given a resource line missing from the update payload, then it stays at its last known remaining hours (partial updates allowed).
- Reads are Delivery/HR/Finance/CEO/SystemAdmin; writes are Delivery/SystemAdmin.

## Data
- `forecast_period` (id, gm_model_id FK, week_ending date, forecast_lines_json JSONB, forecast_revenue NUMERIC(14,2), forecast_cost_us NUMERIC(14,2), forecast_cost_india NUMERIC(14,2), forecast_gm_us NUMERIC(6,4), forecast_gm_india NUMERIC(6,4), updated_by, updated_at). Immutable per week.
- Unique (gm_model_id, week_ending).

## Notes
- Blueprint §8 (weekly forecast is a single field per line: remaining_hours).
- Uses gm library for all math.
