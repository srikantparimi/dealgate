# Independent Forecast Plan Review

Session: 2026-10-02, bounded 15-minute QA increment. Branch `s21/qa-plans`.
Reviewed source: `dd4ac6da8a7e2205fce5d70160b12a30bc32d4e0`.
Owned additions: this report and `api/tests/test_s21_forecast_plans_independent.py`.
No production edits, existing assertion changes, migrations, external databases,
cloud calls, browser activity, deployment, or shared runtime changes.

## Findings

1. **P1: invalid fixture provenance still authorizes planning writes.**
   `api/app/services/forecast_plans.py:86` checks participants, tenant/environment
   and expiry but omits the authoritative issuer, deal ownership and CRM-link
   checks in `api/app/services/test_fixtures.py:123`.
   Four independently exercised cases begin with a real `create_fixture` grant,
   then demote its issuer, change its deal owner, attach a CRM company ID, or
   attach a CRM deal ID. Each still persists a new test-user plan rather than
   returning 403. These are stored-authority changes, not forged trusted grants.

2. **P1: mixed Sales/HR roles bypass Forecast raw-cost redaction.**
   `api/app/routers/forecast.py:94` strips aggregate cost fields for readers
   outside Forecast `ORG_READ`, but leaves `commercial_inputs` to the generic
   redactor at line 103. The generic HR entitlement retains that structure,
   exposing its explicit delivery cost to a Sales/HR portfolio reader.
   Sales-only control passes. The Forecast contract separates HR demand access
   from financial entitlement; adding HR must not bypass this narrower boundary.

3. **P1: overlapping conversion writes can poison the company projection.**
   `api/app/services/forecast_plans.py:288` checks reuse of one GM source, but
   line 293 commits another source without checking aggregate covered scope.
   Two January signed sources can each claim 0.6 of the same plan. The test
   expects the second write to return 409 without persisting another mapping.
   An additional isolated in-memory probe confirmed two persisted conversions
   followed by `ValueError: Signed economic scope is over-covered` on outlook.
   The router maps that read failure to 422; the ordinary company view is lost.

4. **P1: signed revenue disappears when only its cost is unknown.**
   `api/app/services/forecast_plans.py:381` passes every commercial completeness
   reason into signed eligibility. A real calculated January commercial schedule
   with revenue USD 400 and unknown delivery cost produces outlook revenue 0.
   Expected: known signed revenue 400, cost NULL, GM NULL. The test seeds the
   released package classification; it does not prove an incomplete GM can pass
   the actual approval/signature workflow.

5. **P2: conversion changes money without changing the source watermark.**
   `api/app/services/forecast_plans.py:321` and line 375 collect only plan/version
   and GM/package identities; line 394 hashes no conversion identity/fraction.
   After a 40% conversion, January Expected revenue changes from 900 to 700,
   but `source_watermark` is identical. A consumer cannot distinguish those
   incompatible financial projections by the advertised watermark.

## Test Evidence

Own existing QA virtualenv, Python 3.14; SQLite in-memory metadata fixture.
`DEALGATE_POSTGRES_URL` was explicitly unset, so no migration hook ran.

```sh
env -u DEALGATE_POSTGRES_URL \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest \
  api/tests/test_s21_forecast_plans_independent.py \
  api/tests/test_s21_forecast_plans.py -o addopts=-ra -q
```

Expected/collected/executed: **20**; passed **12**; failed **8**; skipped **0**;
xfail **0**; not run **0**; exit **1**, 18.37 seconds.
Independent file: 15 cases, 7 passed / 8 failed. All five existing persistence
tests pass. Ruff check of the new test file passes. No retries, skips, xfails,
production fixes, or weakened assertions were used to obtain these results.

All failing node IDs have prefix
`api/tests/test_s21_forecast_plans_independent.py::`:

```text
test_conversion_changes_the_projection_watermark
test_overlapping_conversion_cannot_persist_an_unreadable_company_outlook
test_signed_unknown_cost_preserves_known_revenue_and_incomplete_margin
test_portfolio_reader_without_forecast_financial_permission_has_no_raw_costs[groups1]
test_fixture_trust_is_revalidated_before_planning_write[issuer_demoted]
test_fixture_trust_is_revalidated_before_planning_write[deal_owner_changed]
test_fixture_trust_is_revalidated_before_planning_write[client_mirrored]
test_fixture_trust_is_revalidated_before_planning_write[deal_mirrored]
```

Passing independent controls cover same-key create replay (one version/job/audit),
changed-payload conflict, exact conversion replay, unsigned-source rejection,
Sales-only cost redaction, tenant-isolated jobs/reads, stale latest-version
exclusion, failed-job backoff and repair via a new version with obsolete old work.
Monetary expectations are literal independent arithmetic: proposed 1000/500 at
50%, signed 400/200, then a 40% conversion leaves expected 700/350. They are not
copied from production output. The worker failure case deliberately corrupts a
stored input to reach the retry boundary; production calculators are not mocked.

## Contract Status And Limits

| Item | State | Bounded evidence / remaining work |
| --- | --- | --- |
| FC-05 | missing | Partial replay works; overcoverage and signed unknown-cost defects remain. |
| FC-12 | missing | Durable isolated worker controls work; conversion watermark is incomplete. |
| FC-11 | missing | Sales-only redaction works; Sales/HR financial leak remains. |
| S21F:T20 | missing | Local conversion tests only; full signed journey and amendment activation unproved. |
| S21F:T25 | deferred | No export, historical snapshot, concurrent Postgres or browser acceptance. |
| S21F:T28 | deferred | Local repair fixture only; no restart/storage/provider recovery acceptance. |
| S21F:T32 | missing | Four fail-open planning fixture cases and mixed-role leak remain. |

SQLite does not prove PostgreSQL locks, concurrent uniqueness, triggers, numeric
round-trips, migration parity, transaction crashes, or deletion cascades. Signed
package states are unit fixture setup, not upload/review/signature/release proof.
No cloud authorization, HTTP authentication/JIT provisioning, deployed UI,
actuals, People demand, exports, amendment activation, or feature acceptance is
claimed. The lead owns production correction and subsequent integration proof.
