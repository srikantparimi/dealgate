# Independent Commercial QA

Run `QA-S21F-commercial-20261001-2`; budget approximately 25 minutes.
Worktree `dealgate-s21-qa`, branch `s21/qa`; clean before starting. Calendar
`e041387` was already an ancestor and was not duplicated. Lead-authorized
baseline cherry-picks: `44a3396 -> 6c1a68c`, `83950f6 -> a6e6011`,
`69542fb -> d496541`, `2862285 -> dc91e44`. Exact reviewed source:
`dc91e44454f52fa805626137e91f6502829f8116`.

Only new QA additions: `api/tests/test_s21_commercial_independent.py` and this
report. No production edits, migrations, deployment, shared runtime, cloud calls
or additional agents. Expectations are literal independent amounts or stdlib
date/Decimal arithmetic; no production helper calculates the expected answer.

## Findings

1. **P1: hybrid children double-count the same identified revenue source.**
   `api/app/gm/commercial.py:651` checks child cost sources only; revenue at
   line 710 is added without cross-child source validation. The local source
   sets at lines 587 and 758 protect only one component. Copying a pricing
   source with the same accepted-usage row ID into two differently named
   components produces a complete, assessed USD 2,000 total from one USD 1,000
   source. Reproduced independently for unit quantities, T&M estimates and MSP
   usage. Expected: targeted unresolved duplicate-source result, not an
   arbitrary choice of which copy wins. Renaming a component cannot authorize
   counting the same economic source twice.
2. **P2: ordinary partial-month amounts fail the precision guard.**
   `_prorate` at `api/app/gm/commercial.py:527` intentionally rounds repeating
   ratios to 28 digits. Subsequent sums trap `Inexact` at lines 339-346
   (`assess`) or line 568 (calendar price aggregation under `calculate_component`).
   A USD 100/month MSP from October 1 through November 1 yields rows 100 and
   3.333..., then becomes unassessable. Independent pre-display total at the
   existing precision is `103.3333333333333333333333333`, with confirmed zero
   cost and GM 1. Four one-day USD 100/month assignments independently total
   `12.90322580645161290322580645` revenue and 160 cost, but the schedule itself
   is incomplete. Neither case contains an oversized source amount.
   These tests do not invent a cents-rounding policy: these profile inputs have
   no confirmed minor-unit field. The separate fixed-fee conservation test does
   explicitly confirm USD 0.01. Implementation must distinguish supported
   ratio precision from lost input money, without globally disabling guards.
3. **P2: calendar cost precision loss happens before the commercial guard.**
   `api/app/gm/calendar.py:192` installs a fresh nontrapping Decimal context;
   line 242 rounds paid-hours times loaded cost. Commercial `_calendar_rows`
   at `api/app/gm/commercial.py:513` consumes that rounded result, so its own
   outer guard cannot detect the loss. An adversarial loaded rate
   `1000000000000000000000000000000.01` for eight paid hours has independent
   exact cost `8000000000000000000000000000000.08`. The output loses 0.08 yet
   both the commercial schedule and its assessment say `ok`. Expected for
   unsupported source precision: unresolved/incomplete, as for direct costs.
   This is an extreme input validation boundary, not a claim that normal rates
   lose eight cents.

## Passing Evidence

All seven profiles match independent literal revenue/cost totals. Every profile
keeps a missing cost unresolved and prevents Finance assessment. Company X now
uses the production fixed schedule and matches six 70,000/35,000 months, GM 50%,
and independently specified weighted quarter totals 122,000/147,000/49,000.
The quarter aggregation here is test arithmetic, not a production Forecast test.

USD 100.01 split 2:1 conserves cents as 66.67/33.34, regardless of input order.
Partial staffing October 16-31 has independently enumerated 11 paid weekdays
and one paid nonbillable holiday. Three people at 25% yield 60 billable/66 paid
hours. Hourly/daily revenue is 7,200; monthly revenue is 1,200; paid cost 2,178.
Changing billing cadence does not change any profile's service economics.

Explicit EUR-to-USD conversion gives 1,025 revenue and 190 cost while retaining
native child money. A child's US floor breach still requires CEO despite the
passing blended margin. Missing FX rate/version/date stays unresolved; duplicate
cost sources are rejected. Hybrid shared direct costs are counted once.

## Execution

Existing QA-owned Python 3.14 venv, synthetic in-memory inputs. Postgres URL
unset; pytest's SQLite configuration is local and no migration is invoked.

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/test_s21_commercial_independent.py \
  api/tests/test_s21_commercial_profiles.py \
  api/tests/test_s21_calendar_schedule.py -o addopts=-ra -q
```

Final expected/collected/executed **115**, passed **109**, failed **6**, skipped
**0**, xfailed **0**, not-run **0** within this selection; exit 1, 5.88 seconds.
The new QA file contributes 31 cases: 25 pass, six fail. The existing 53 profile
and 31 calendar cases all pass. Initial independent-only run was 25 pass/six
fail in 1.28 seconds; the final run followed an extra literal expected-total
assertion and a variable rename, without weakening any failing assertion.
Ruff passes. No retries, skips, xfails or production fault injection were used.

Collected QA node prefix (rootdir `api`): `tests/test_s21_commercial_independent.py::`.
Parameterized names below expand only across the explicitly listed collected IDs:

- `test_seven_profiles_match_independent_literal_economics[profile]`: fixed_assignment, recurring_msp, calendar_staff_aug, tm, milestone, unit, hybrid.
- `test_unknown_cost_never_passes_finance_for_any_profile[profile]`: the same seven collected profile IDs.
- `test_company_x_fee_cost_and_weighted_quarters_use_independent_expectations`
- `test_fixed_fee_largest_remainders_conserve_confirmed_cents_and_order`
- `test_partial_calendar_dates_holiday_and_allocation_apply_once[hourly-120-7200]`
- `test_partial_calendar_dates_holiday_and_allocation_apply_once[daily-960-7200]`
- `test_partial_calendar_dates_holiday_and_allocation_apply_once[monthly-3100-1200]`
- `test_hybrid_child_floor_cannot_be_hidden_by_aggregate_or_fx`
- `test_hybrid_unknown_fx_never_becomes_parity[fx0]`, `[fx1]`, `[fx2]`, `[fx3]`
- `test_hybrid_duplicate_cost_sources_are_rejected`
- `test_hybrid_does_not_count_same_identified_revenue_source_twice[unit]` (failed)
- `test_hybrid_does_not_count_same_identified_revenue_source_twice[tm]` (failed)
- `test_hybrid_does_not_count_same_identified_revenue_source_twice[recurring_msp]` (failed)
- `test_normal_partial_month_msp_remains_assessable_before_display_rounding` (failed)
- `test_partial_month_calendar_lines_remain_assessable_when_aggregated` (failed)
- `test_calendar_cost_does_not_silently_discard_minor_units_before_commercial_guard` (failed)

## Scope Status

| Requirement | State | Evidence / Boundary |
| --- | --- | --- |
| S21-15 | missing | Calendar pricing/precision defects above; passing hour/holiday tests do not close T13. |
| S21-17 | missing | Seven-profile local economics exercised; six red checks remain. |
| S21-18 | deferred | No extraction, schema migration or UI/lifecycle verification in this QA task. |
| FC-02 / FC-04 / FC-05 | deferred | Independent Company X arithmetic only; production Forecast reconciliation was not run. |

S21F:T13/T15/T16/T19/T21 are not accepted by this local run. Untested boundaries
include persisted source identity and policy resolution, uploaded evidence,
effective amendments, permissions, approved actuals versus forecast replacement,
all currencies/minor units, recurring credits beyond revenue, shared allocations
across disjoint child terms, nested hybrid support, API/browser flows, deployed
workers and staging acceptance. The lead/commercial owner must fix the preserved
red tests; QA has not approved those future fixes.

## Reverification and Consumer Handoff

Run `QA-S21F-commercial-20261001-3`, bounded recheck plus approved T19 oracle
artifact. The worktree was clean. Authorized source updates only:
`faa797d -> f746490`, `178f93f -> dec2312`, `e37bd6b -> c77b7f4`,
`98242b8 -> ac96f9f`. Reviewed baseline is
`ac96f9f522628b662b1413a19a4b5cd1719c20a6`. The original 31 tests and assertions
were unchanged and all passed in 1.31 seconds, including the prior six failures.
This independently verifies those specific fixes locally, not full acceptance.

The adapter preserves child outcomes, null GM and incomplete/exception state.
Two additional passing cases verify a missing-cost child and zero-revenue child
do not become a passing parent. Actual existing consumers expose three remaining
issues, preserved as ten new failing cases:

1. **P1: consumers drop child floor authority.** `api/app/gm/policy.py:98` and
   `api/app/services/delivery_model.py:1074` derive CEO routing only from aggregate
   margins. `api/app/services/gm_sandbox.py:494` reconstructs `TemplateResult`
   without `gm_outcome`/`commercial_schedule`, then its custom policy path at
   line 413 also tests only aggregate values. Independent fixture: aggregate US
   GM 83%, child GM 20%, explicit US floor 60%; adapter authority correctly
   requires CEO, all three consumers incorrectly return false.
2. **P2: unassessed placeholders become visible zero money.** Builder response
   at `api/app/services/delivery_model.py:1082` and sandbox response at
   `api/app/services/gm_sandbox.py:520` serialize the adapter's compatibility
   defaults as string `0`. Missing cost, unsupported pricing and zero-revenue
   exception cases each reproduce this for both consumers. Expected unassessed
   placeholder fields are null with missing/status metadata preserved.
3. **P2: ratio flag permits losing whole currency units.** The new
   `api/app/gm/commercial.py:539` disables the addition's entire `Inexact` trap
   once a value has a derived ratio, not only rounding of insignificant ratio
   tails. One-day USD 100/31 base revenue plus exact USD 1E30 overage returns
   complete/assessed 1E30, silently losing over USD 3.22 of revenue. Independent
   50-digit arithmetic establishes a total greater than
   `1000000000000000000000000000003`. Expected unsupported aggregate precision
   is incomplete. This is a new extreme-magnitude failure, separate from the
   six previously fixed cases; original oracle assertions remain intact.

New failing nodes use prefix `tests/test_s21_commercial_independent.py::`:

- `test_commercial_consumer_retains_child_floor_authority[policy]`
- `test_commercial_consumer_retains_child_floor_authority[builder]`
- `test_commercial_consumer_retains_child_floor_authority[sandbox]`
- `test_commercial_unassessed_response_never_serializes_placeholder_zero[builder-missing_cost]`
- `test_commercial_unassessed_response_never_serializes_placeholder_zero[builder-unsupported]`
- `test_commercial_unassessed_response_never_serializes_placeholder_zero[builder-zero_revenue]`
- `test_commercial_unassessed_response_never_serializes_placeholder_zero[sandbox-missing_cost]`
- `test_commercial_unassessed_response_never_serializes_placeholder_zero[sandbox-unsupported]`
- `test_commercial_unassessed_response_never_serializes_placeholder_zero[sandbox-zero_revenue]`
- `test_derived_ratio_does_not_allow_losing_entire_currency_units`

## Company X Expectation Artifact

The lead approved `api/tests/s21_acceptance/test_company_x_forecast_oracle.py`.
The lead's initial T28/T29 reference was corrected to authoritative **T19 /
Oracle A**: T28 is recovery and T29 is migration. No such operational coverage
is claimed. This file uses only stdlib date/Decimal/zoneinfo and pytest; no
feature mocks or implementation outputs supply its expectations.

Eighteen passing expectation cases establish monthly Committed/Expected/Upside;
quarter and future-only money; 1/2/4 full-quarter selections; Los Angeles rollover
at 2026-10-01 07:00 UTC; December-May date slip preserving the fee; once-weighted
revenue/cost; zero/50%/100% probability; missing probability; and unknown signed
assessment cost. The signed assessment's USD 24,000 revenue does not establish
a cost, so current-quarter GM cannot be invented from the proposal's 50% margin.

Future two-quarter Expected revenue/cost is 196,000/98,000, Upside is
280,000/140,000, and Committed is 0/0. After the December slip, Expected future
money is 245,000/122,500 while full proposed revenue/cost stays 420,000/210,000.
These are reusable expectation artifacts, not proof of the production Forecast
projection, persisted account totals, People publishing or deployed UI.

Final exact command:

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/test_s21_commercial_independent.py \
  api/tests/s21_acceptance/test_company_x_forecast_oracle.py -o addopts=-ra -q
```

Expected/collected/executed **61**, passed **51**, failed **10**, skipped **0**,
xfailed **0**, not-run **0** in the selected run; exit 1, 2.42 seconds. Breakdown:
43 commercial cases, 33 pass/10 fail; 18 oracle cases all pass. The standalone
oracle run passed 18/18 in 0.74 seconds. Ruff passes for both test files.
Local QA venv only; no migration, cloud, shared runtime, deployment or production
edits. No retries, assertion weakening, skips or xfails. Lead owns consumer fixes;
commercial owner owns the remaining precision guard. S21-15/S21-17 remain
**missing** as integrated functionality; previous six local defect reproductions
are now **fixed and tested**. S21-18 and FC-02/04/05 remain **deferred** in this
bounded QA lane; no full T13/T15/T19/T21 acceptance is claimed.
