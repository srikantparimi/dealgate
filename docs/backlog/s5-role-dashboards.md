# S5 E10 — Role dashboards + Client SOW + GM page

## User story
Every role opens a dashboard tailored to their queue. The CEO sees pipeline
value, approved-vs-forecast gross profit, below-floor deals, exceptions
pending, revenue expiring in 90 days, aged blockers. Finance sees GM by
SOW and geography, approved vs forecast vs actual, missing inputs. Sales
sees My deals. HR sees confirmed + probability-weighted demand. Legal sees
NDA/MSA coverage + packages to review. Client page shows every SOW with
approved/forecast/actual GM.

## Acceptance tests
- Given I am CEO, when I open `/dashboard`, then I see the 5 CEO widgets.
- Given I am Finance, then I see the 4 Finance widgets.
- Given I am Sales, then I see My deals + next actions.
- Given a below-floor deal is `pending_ceo_exception`, it appears on both
  CEO and Finance views.
- Given a client has 3 SOWs, `/clients/{id}/sows` shows dates/value/
  US-India cost/approved GM/forecast GM/actual GM/exception flag; client
  GM is total gross profit / total revenue over the same period (NOT a
  mean of percentages) — this is a specific test.
- Every dashboard number is computed server-side via the pure gm library.
- All role gates enforced.

## Data
- Read-only endpoints joining opportunity + package + gm_model + actuals.
- `forecast_period` and `actual_period` tables (empty for now; populated
  in Sprint 6). Dashboards degrade gracefully.

## Roles
- Per-view gates as described.

## Notes
- Blueprint §9 dashboards table.
