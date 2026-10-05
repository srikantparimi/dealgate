# Next Opportunities Increment

Branch `s21/next-opportunities`, baseline `a5ef409`; bounded ownership from the
integration lead. FC-01/08 planning view and assumption revision only. FC-09/10
candidate generation, rules, source continuity and People workflows remain open.

## Backend Increment

`POST /forecast/plans/{id}/assumptions` accepts only expected version,
probability/source, assumptions, lifecycle and written reason. It checks the
existing PLAN_WRITE roles, tenant/environment/account boundaries and locks the
plan. Prior versions are immutable; stale requests return 409 without duplicates.
New versions preserve scope, commercial terms, frozen policy, FX, scenario-group
and selected state. Only source-version metadata is rebound to the new immutable
version (including hybrid children/staffing). A durable existing ForecastJob and
transactional audit record are created. No CRM, signing, quoting or hiring call.

Plan list adds authoritative `can_edit_assumptions` and source-evidence fields.
Read-only roles receive no write capability; financial permissions are unchanged.
The new endpoint does not accept commercial/account/deal/FX fields from a client.

Tests were authored before production during an author-only capacity window.
Runtime became available after production authoring, so no preimplementation
red execution is claimed. Initial backend run: **19 passed**, two existing
FastAPI deprecation warnings, 18.48 seconds. This covers new assumption cases
plus existing plan tests: immutable history/economics, stale conflict, read-role
and cross-tenant denial, strict input validation, safe capabilities, real worker
recalculation and HTTP role/persistence. Independent expected future amount:
four monthly values of 70,000 at probability 0.65 = **182,000**.

Command from this worktree's `api`:

```sh
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-next-opportunities/api \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest \
  tests/test_s21_plan_assumptions.py tests/test_s21_forecast_plans.py \
  -o addopts= -q -p no:cacheprovider
```

Private SQLite only, shared dependency executable read-only, no provider/cloud
calls. Local tests are not migrated PostgreSQL or staging acceptance. Frontend
authored with tests; verification waits for the next serialized runtime slot.

## Frontend Increment

Next opportunities is the fourth Forecast view, preserving the existing
Company & accounts default, Overview, Revenue projection and chart behavior.
Rows are the real paginated scoped plan response, not generated suggestions.
Local forecast only and authoritative linked-deal destinations stay distinct;
source evidence, probability provenance, assumptions, job status, attempt count,
next retry and failure messages are visible. Pagination uses the existing server
metadata. Account, scenario, horizon and as-of URL state remain intact.

The assumption editor prefills existing values, requires a written reason and
submits only the narrow endpoint contract. Read-only rows show no edit control.
Saving refreshes persisted plans and outlook together; stale 409 leaves draft
text visible without claiming success. There are no CRM promotion, client
communication, staffing reservation or hiring actions in this view.

Frontend verification: **22 passed** (six new opportunity tests, eleven existing
Forecast tests, five Overview tests), no skips/retries, 16.86 seconds. Tests
cover real page/view filter wiring at the unit boundary, server capabilities,
explicit source states, job errors, prefill/exact request shape, stale edit
retention and empty results. Existing React Router future-flag warnings remain.
Unit API mocks are not connected-feature acceptance evidence.
`tsc --noEmit` and diff checks passed.

Own dependency directory was copied from the previous isolated worker tree;
no symlink, network install, shared dependency writes, DB or provider calls.
The lead serialized backend, copy, frontend tests and TypeScript runtime slots.

Remaining requirements are explicit: Resource demand/People integration,
authoritative source-SOW-to-follow-on relationships, generated growth candidates,
CRM promotion/link correction, automation rules, saved views, full exports and
connected staging journeys. Four visible views and passing unit counts do not
establish FC-01/08/09/10 completion. No main merge or staging claim.
