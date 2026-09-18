# S6 E9 — Actuals CSV import (timesheets + cost)

## User story
As Finance, at month-end I upload a CSV of actual hours + cost per resource
line. The system computes actual GM per project + component and surfaces it
on the Finance dashboard and the Client SOW+GM page.

## Acceptance tests
- Given I POST `/actuals/import` with a CSV of {sow_ref, resource_line_id, period_month, actual_hours, actual_cost, actual_revenue}, then each row becomes an `actual_period` record.
- Given an unknown resource_line_id or unparseable row, then whole-file reject with row-level errors (all-or-nothing).
- Given actual_cost missing on any row, whole-file reject (§2 hard rule).
- Given actuals for a period exist, re-import upserts (same period + line = replace).
- Actual GM = (sum revenue - sum cost) / sum revenue for the period.
- Roles: Finance/SystemAdmin.

## Data
- `actual_period` (id, gm_model_id FK, resource_line_id FK, period_month date, actual_hours NUMERIC(10,2), actual_cost NUMERIC(14,2), actual_revenue NUMERIC(14,2), imported_by, imported_at). Unique (resource_line_id, period_month).
- `actual_import_batch` (id, uploaded_by, uploaded_at, row_count, errors JSONB, status).

## Notes
- Blueprint §9 (actuals CSV pilot; integration after).
- Formula: sum(revenue) - sum(cost) / sum(revenue), not mean of pcts.
