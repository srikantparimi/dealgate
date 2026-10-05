# Commercial Lane: Calendar Increment

Session C-S21F-20261001-1. Budget: 60 minutes. Branch `s21/commercial`, base
`4544bfc`. Owned changes: `api/app/gm/calendar.py`,
`api/tests/test_s21_calendar_schedule.py`, and this handoff. No shared schema,
service, UI, dependencies, existing tests, cloud actions or deployment changed.

## Requirement State

- S21-15: **fixed and tested** for the bounded calendar/hourly engine increment
  only. Full T13 remains unverified: no persisted calendars, roster UI or staging
  journey is claimed.
- S21-17: **missing** as an integrated commercial component registry and pricing
  workflow. This increment supplies reusable calendar quantities and a guarded
  adapter to the existing GM engine; it does not implement all pricing profiles.

## Interface

Import from `app.gm.calendar`:

- `DayHours(scheduled, billable, paid)` holds explicit per-person Decimal hours
  for a local service date. Values are finite, nonnegative and at most 24.
- `CalendarOverride(day, hours, reason)` replaces all three quantities on that
  date. A paid nonbillable holiday is explicitly `0 / 0 / 8`; holiday or weekend
  service coverage may instead have positive scheduled/billable hours.
- `WorkCalendar(calendar_id, version, timezone, coverage_start, coverage_end,
  week, overrides=())` has seven Monday-first DayHours entries and dated
  exceptions. Coverage is explicit, inclusive and may span any supported year.
  Duplicate override dates, invalid IANA timezones and out-of-coverage overrides
  are rejected. Input sequences are copied to tuples.
- `StaffingAssignment` requires source/component/profile/policy identity and
  versions, role/location/timezone/currency, integer quantity, Decimal allocation,
  calendar, hourly bill/cost rates and their versions. Rates, location, currency
  and calendar can be unresolved. Optional assignment dates default to term
  bounds; their inclusive intersection with the term controls each row.
- `monthly_staffing_schedule(assignment, *, term_start, term_end)` returns a tuple
  of frozen `MonthlyStaffing` values, ordered by month. Each contains month and
  overlap dates, scheduled/billable/paid hours, hourly revenue and loaded hourly
  paid cost, daily calculation details/reasons, missing inputs, calculation
  version, and the full immutable assignment/calendar assumptions.
- `MonthlyStaffing.as_resource_input()` refuses incomplete rows and returns the
  existing engine `ResourceInput` with `utilization=1`. Quantity and allocation
  have already been applied. Use the existing `compute_gm(SowSpec(...))` for
  margin/floor assessment. Callers retain component scope and pass the correct
  currency/FX/policy inputs; the adapter performs no currency conversion.

No overlap yields no rows. Any uncovered date leaves that month's hour totals
and money as `None`, never an apparent complete partial sum. Missing costs stay
`None` while known revenue/quantities remain available. Missing currency leaves
money unknown. No hours are inferred from 160-hour months or national holidays.
Calculations use an isolated Decimal context at the existing engine precision.
Scheduled hours mean service coverage, so a nonworking paid holiday contributes
paid hours but zero scheduled hours. Overnight shifts must supply explicit
hours attributed to each local service date; no elapsed-time or DST conversion
is guessed.

## Proof

Lane-owned Python 3.14.5 environment: `python3 -m venv api/.venv`, then
`api/.venv/bin/pip install -e 'api[dev]'`. No shared environment or database used.
Tests unset `DEALGATE_POSTGRES_URL`; existing database tests use isolated SQLite.

Test-first evidence: initial focused run exited 2 with `ModuleNotFoundError:
app.gm.calendar` before implementation. A later validation test-first run had
27 passed / 4 failed for whitespace-only financial metadata and invalid IANA
timezones; those validation failures were fixed without weakening assertions.
Focused suite: 31 tests, all passed, zero failed/skipped/xfailed.

Independent standard-library `calendar.Calendar().itermonthdates` enumeration
(without importing production code) confirmed October-July paid weekdays
`22,21,23,21,20,23,22,21,22,22` and billable days
`21,19,22,19,19,23,22,20,21,21`. Tests retain literal expected constants. Oracle B
proves 16,560 scheduled/billable hours, 17,360 paid hours, USD 1,656,000 revenue,
USD 1,041,600 cost and Decimal GM `0.3710144927536231884057971014` via the existing
engine, plus exact monthly amounts and GM. Partial dates, changing dated
quantity/allocation, mixed locations, weekend shifts, holiday service, leap year,
zero revenue, missing coverage/costs, invalid inputs and immutable replay are
also covered.

Static checks: Ruff passes for both new Python files; mypy passes for the module
with `--follow-imports=silent`. Final regression: expected/collected/executed 154,
passed 142, failed 0, skipped 0, xfailed 12, not-run 0 within the selected suite;
40.32 seconds. All 31 new calendar tests passed in that run. The 12 unchanged
S20 skeleton xfails are seven incomplete-input/Finance/Command Center cases in
`test_s20_gm_incomplete_inputs.py` and five floor/Decimal cases in
`test_s20_gm_thresholds.py`; they deliberately raise assertions and provide no
behavioral evidence. Three existing FastAPI/Starlette deprecation warnings were
reported. No retries or new xfail/skip markers were used.

Reproduce from the worktree root:

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/test_gm_{core,engine_properties,goldens,rules_doc,model_templates,staff_aug,managed_service,tm,fixed_price,single_resource,assessment,policy,policy_versioning,properties}.py \
  api/tests/test_s20_gm_incomplete_inputs.py api/tests/test_s20_gm_thresholds.py \
  api/tests/test_s21_calendar_schedule.py -o addopts=-ra
```

## Integration Work

Lead must persist/version confirmed calendars and assignments, retain source
evidence and override author history, supply effective rate/cost intervals, and
validate overlapping assignments/components before aggregation. This function
schedules one assignment; it cannot decide whether two independently supplied
assignments duplicate the same people or economic scope.

The hourly adapter is deliberately limited to hourly economics. Recurring/fixed
fees, day/month rates, salary allocation, caps/minimums, billing versus recognized
revenue, FX revision storage and amendments require the typed pricing component
layer. Cost/quantity fields are available for MSP coverage but monthly fee
proration and MSP margin integration are not supplied here. Bind outputs to
immutable approval versions, connect the roster/how-calculated UI, then have QA
run the complete T13/T15 paths on the integrated revision. No staging proof or
whole S21-15 verification is claimed by this engine increment.

`MonthlyStaffing.complete` and `as_resource_input()` require both `bill_rate` and
`rate_version`. Fixed-fee/MSP consumers must assess cost completeness separately;
the hourly adapter's revenue requirements must not become their approval rules.
Pure dataclasses expect validated `date`/`Decimal` inputs. API/extraction adapters
must validate strings/floats before construction rather than pass raw fields.

## Session 2, Checkpoint 1: Registry and Fixed Assignment

User-authorized S21 window: three hours; first coherent checkpoint within 30
minutes. New owned files: `api/app/gm/commercial.py` and
`api/tests/test_s21_commercial_profiles.py`; this handoff is updated. Existing
calendar implementation/tests are unchanged.

The immutable `PRICING_PROFILES` registry describes all seven version-1 profiles
and exposes `calculation_available` truthfully. This checkpoint provides the
fixed-assignment calculator only; the remaining six calculations are subsequent
increments, not claims of completed profile coverage.

`PricingComponent` preserves component/source/workstream/profile/policy identity
and versions, evidence, local service term, currency, independent billing cadence,
typed pricing and an explicitly confirmed cost plan. `FixedFee` contains the
total fee, confirmed `FeeAllocation` month/location weights, allocation basis and
currency minor unit. `PeriodCost` identifies a distinct allocated cost line with
month, location and amount (or `None`). Empty costs mean zero only when the caller
explicitly confirms the cost plan and names its basis.

`calculate_component(component)` returns a frozen `ComponentSchedule` retaining
the original input, monthly/location rows, completeness, missing reasons and
calculation version. Unknown profile/version preserves the input and returns
`unsupported`. Invalid or unresolved material inputs return `incomplete`.
`schedule.assess(us_floor=..., india_floor=...)` delegates to existing `compute_gm`
using exact recorded revenue allocations and direct costs; callers must resolve
the stored policy version and supply its floors. Amounts remain in the component
currency; no FX conversion or cross-currency aggregation is performed.

Fixed-fee allocation uses largest remainders with stable month/location tie order.
It conserves the confirmed fee in currency minor units; cadence changes do not
alter service economics. Literal independent tests include Company X's six
USD 70,000 revenue / USD 35,000 cost months, two cents split into three periods,
and a USD 2,000 mixed-location component whose 52.5% blended GM still exposes an
India 45% floor breach. No production formula generates expected test values.

Test-first proof: new profile tests first exited 2 at collection because
`app.gm.commercial` did not exist. Implementation then passed 14/14 focused tests
with zero skips/xfails. Ruff passed for both new Python files; module mypy passed
with `--follow-imports=silent`. Regression command:

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/test_s21_commercial_profiles.py api/tests/test_s21_calendar_schedule.py \
  api/tests/test_gm_engine_properties.py api/tests/test_gm_goldens.py \
  api/tests/test_gm_core.py api/tests/test_gm_policy.py -o addopts=-ra
```

Expected/collected/executed/passed: 102; failed/skipped/xfailed/not-run: 0 within
that selected suite. Runtime 8.93 seconds. No retries or weakened assertions.

S21-17 remains **missing** for the integrated seven-profile workflow, with this
registry/fixed-fee engine portion **fixed and tested**. S21-18 is **missing** for
extraction, preservation/editors, migration and lifecycle wiring. T15/T16 require
real uploads/UI and independent QA after the remaining calculations and lead
integration. No acceptance or staging completion is claimed.

## Session 2, Checkpoint 2: Milestones, Units and T&M

Added typed `MilestonePricing`, `UnitPricing` and `TimeAndMaterials` payloads to
the same `PricingComponent`/`calculate_component` interface. These three registry
calculations are now available alongside fixed assignment. MSP, calendar pricing
and hybrid remain disabled pending their tested increments.

Milestones preserve ID, planned date, amount, location, acceptance conditions and
separate invoice/recognized-revenue references. Service revenue lands on the
planned date's month; cost stays on its own delivery dates. Invoice references do
not convert planned service revenue into recognized actuals. Missing conditions,
dates or amounts and duplicate milestone IDs remain unresolved.

Unit pricing multiplies only confirmed billable-unit, sprint-fee or capacity-fee
quantities by the explicit rate. Delivery-estimate points are not a pricing basis,
and no point-to-hours conversion or derived delivery cost exists. T&M stores
estimates and approved usage separately; service forecasts use estimates only.
Each quantity record has its own source ID. Duplicate sources, missing quantities
and out-of-term locations/months do not produce a completed schedule.

T&M caps/minimums change estimated revenue only with the confirmed
`proportional_estimate` allocation basis and explicit currency minor unit. A
positive minimum with a zero estimate remains unresolved because that basis
cannot determine an allocation; no flat allocation is invented. Minimum above
cap is also unresolved. Independent test constants: USD 30,000 estimate capped
at 20,000 yields 6,666.67 / 13,333.33; an agreed minimum raises a 200 estimate to
500; 80 billable points at 125 yield 10,000 revenue with an independent 4,000 cost.

Apportionment now uses exact integer minor-unit counts and rational dimensionless
weights before returning Decimal money. Even an extreme fee retains every cent.
Commercial multiplication/addition and the GM adapter report `precision` when the
existing 28-digit engine precision cannot represent the amounts without loss.
No silently rounded result is presented as complete. The existing GM engine
still performs every margin/floor calculation.

Test-first proof: newly imported terms failed at collection before implementation.
Two subsequent extreme-magnitude tests failed (22 passed / 2 failed), showing
lost cents in cost addition and quantity multiplication before the precision
guard was added. Final checkpoint counts are recorded after verification below.

The Checkpoint 1 regression command now collects and executes 112 tests: 112
passed, zero failed/skipped/xfailed/not-run, in 8.86 seconds. The profile file
contains 24 passing cases. Ruff and module mypy (`--follow-imports=silent`) pass.
Existing calendar/GM files and tests are unchanged by this checkpoint.

Remaining scope includes calendar-derived T&M estimates, MSP/calendar pricing,
hybrid/shared-cost allocation, and all persisted extraction/UI/lifecycle and
migration work. S21-17/18 and T15/T16 are not accepted by these pure tests.

## Session 2, Checkpoint 3: Calendar Pricing and MSP

`PricingComponent.staffing` now accepts immutable calendar assignments for any
profile's cost plan. Component/source/profile/policy versions, currency and
timezone must match. Calendar quantities/costs remain unresolved when coverage or
cost inputs are missing. Only the legacy hourly `bill_rate`/`rate_version` gaps
are excluded from cost completeness; fixed-fee/MSP revenue does not require them.
Daily calendar traces are retained in `ComponentSchedule.calendar_rows`, and
monthly output includes scheduled/billable/paid hours. Calendar cost source IDs
are reserved as `calendar:<assignment_id>` so an explicitly supplied cost with
that ID cannot count the same assignment twice.

`CalendarPricing` requires one versioned `StaffingRate` per assignment. Hourly
rates multiply billable hours; daily rates require an explicit hours-per-billing-
day divisor; monthly rates require explicit `calendar_days` or `full_month`
proration. Headcount/allocation apply once. The original assignment hourly bill
rate is not reused as a daily/monthly rate. A 3,100 monthly per-person rate for
October 16-31 at effective headcount one yields 1,600. A paid nonbillable holiday
costs money while hourly/daily service revenue excludes it.

`RecurringMSP` stores per-location recurring fees, confirmed included scope,
explicit proration and separately identified contractual overage/credit amounts.
Setup fees must be separate components. Billing cadence does not alter service
revenue. Usage-based derivation of overage amounts remains an additional typed
extension; this checkpoint supports source-confirmed monetary adjustments.
Literal test: October 16-31 base 1,600 plus 200 overage minus 50 credit is 1,750;
November is 3,100. Costs follow the staffing calendar independently.

`TimeAndMaterials(calendar_estimates=True)` obtains hourly estimates from the
same staffing calendars. It rejects simultaneous manual estimates and preserves
approved usage separately. Rate units other than hours still require explicit
quantity input. The fixture yields 16,800 revenue and 10,560 paid-hour cost for
October with one effective person and a paid nonbillable holiday.

MSP and calendar registry calculators are now enabled; hybrid is still disabled.
The new test-first import failed before `CalendarPricing` existed; the resulting
profile suite has 33 passing cases. No calendar source/test file was changed.
Full T13/T15/T16 acceptance, persisted model migration, extraction, UI and
approval binding remain integration work rather than claims of this checkpoint.

The same regression command collected/executed 121 tests: 121 passed,
failed/skipped/xfailed/not-run 0, in 7.91 seconds. Ruff passed for both owned
Python files; mypy passed for the module with `--follow-imports=silent`.

## Session 2, Checkpoint 4: Hybrid and Included Units

All seven registry calculations are now enabled for their supported typed inputs.
`HybridPricing` retains child component snapshots and explicit
`SharedCostAllocation(source_id, component_id, weight)` records. Every shared
direct/calendar source needs a confirmed allocation basis, positive total weight
and currency minor unit. Splits conserve each source amount once, with stable
component-ID ties. Parent and child cost/source IDs cannot overlap, and repeated
components are rejected. Derived child cost plans preserve the original inputs.
The full shared roster remains visible once, rather than duplicating headcount
when its cost is divided across components.

Child schedules retain native currency. Mixed-currency totals require an explicit
`FxRate(currency, rate, version, as_of)` targeting the parent currency. Missing FX
stays unresolved. Flat hybrid components may have independent effective service
dates inside the package; source/policy versions must match. Nested hybrids and
cross-currency shared-cost allocation remain unresolved with targeted reasons;
no flattening, conversion/rounding allocation or policy choice is invented.

Every child is assessed with the existing GM authority before package assessment.
An 80% aggregate margin cannot hide a child at 7.5%. The existing engine now
includes child breaches in `GmOutcome.requires_ceo` and propagates zero-revenue or
unsupported child exceptions instead of returning an apparently assessed hybrid.
These are the only existing-engine changes in this lane.

`MSPUsage` now supplies identified unit, usage quantity, included quantity and
overage rate per month/location. Usage above the included amount is priced;
unknown included units stay unknown. Monetary adjustments and derived usage
cannot reuse a source ID. Literal oracle: 125 tickets with 100 included at 4 per
excess ticket adds 100 to a 3,000 fee; 80 tickets adds zero.

Test-first evidence: hybrid/FX types initially failed import. The child-floor
test then reproduced `requires_ceo=False` despite a failing child. Two direct
engine tests separately reproduced `status=ok` for zero-revenue and unsupported
children before the engine guards were added. One fixture aggregate constant was
corrected transparently: 900 + 1,000 + 100 shared cost is 2,000 (child costs 925
and 1,075), not 2,100; the corrected test subsequently failed specifically on
the CEO-routing bug. No behavioral assertion was weakened.

Requested adversarial checks cover assignment currency/timezone/source/profile/
policy version mismatches, calendar cost-plan confirmation, duplicate shared
calendar sources and missing FX. Final regression used the same six-file command:
expected/collected/executed/passed 141; failed/skipped/xfailed/not-run 0; 10.34
seconds. Profile cases: 53. Ruff passed for both implementation files and the
profile test; module mypy (`--follow-imports=silent`) passed.

The bounded registry/economics portion of S21-17 is **fixed and tested**. S21-17
and S21-18 remain **missing** as integrated extraction/editing/migration and
approval/signature/forecast workflows. T15/T16 and complete S21-15/T13 still need
independent QA and deployed user journeys. No full acceptance or staging proof
is claimed. Lead persistence must store typed inputs, source and policy versions,
FX versions, calendar snapshots, shared allocation provenance and effective-date
activation, and enforce permission/optimistic-version rules before these pure
functions are called.

## Independent QA Remediation: Revenue Sources

Starting HEAD `2862285` was clean. Lead-authorized QA evidence commit
`2f7e494862c91db7a094e6b148540faef5e8ae7b` was cherry-picked as `df20456` with
only its two additions. The independent test and QA report are unchanged.
The exact independent suite reproduced 25 passed / 6 failed before production
changes: three cross-child source duplicates, two normal-proration precision
failures and one loaded calendar cost truncation failure.

Hybrid source validation now rejects the same identified contributing revenue
row across child unit quantities, T&M estimates and MSP usage/adjustments. IDs
are compared across pricing types as well as within one type. Approved-usage
metadata is excluded because it does not contribute to forecast economics.
No child is silently selected as the winner of a duplicate conflict.

Test-first extension: a cross-profile source duplicate reproduced the defect;
distinct forecast estimates with repeated noncontributing approved-usage metadata
remain valid. The three unchanged independent duplicate-source tests plus these
two owned tests pass (5 selected; no failures/skips/xfails). Precision findings
remain open at this checkpoint. Full acceptance remains unclaimed.

## Independent QA Remediation: Calendar Precision

Calendar arithmetic now traps precision loss at the originating quantity/rate
operation. A monetary multiplication that cannot preserve its input value leaves
that amount `None` with a `precision` reason while retaining exact hours. If the
quantities themselves exceed supported precision, the affected month remains
unresolved. Unsupported paid cost cannot become a rounded apparently complete
cost before the commercial layer sees it.

Four owned extreme-rate cases first failed for both bill and loaded-cost rates,
then passed after the guard. The complete calendar suite plus the unchanged QA
loaded-cost assertion passes: 36 selected, zero failures/skips/xfails. The two
ordinary-proration QA findings remain open for the next fix; no rounding policy
or independent QA assertion has changed.

## Independent QA Remediation: Derived Ratio Precision

`CommercialMonth.revenue_uses_ratio` records whether calendar proration or daily
rate division produced a nonterminating result at the authority's existing
28-digit precision. Only subsequent addition/conversion of that derived revenue
uses normal calculation precision. Source operands, exact-revenue operations,
calendar quantities, loaded costs and direct-cost aggregation retain precision
guards. No currency quantization or new monetary rounding unit was introduced.
Ratio provenance follows monthly/location aggregation and hybrid FX/children.

The two unchanged independent ordinary-proration tests were red before this fix.
Two additional owned cases first failed for prorated fees plus credits/usage and
hybrid prorated FX aggregation; a third retains the adversarial direct-cost
minor-unit guard when ratio revenue is present. All pass with literal expected
values. Independent QA test/report content is byte-identical to `df20456`.

Full targeted regression command:

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/test_s21_commercial_independent.py \
  api/tests/test_s21_commercial_profiles.py api/tests/test_s21_calendar_schedule.py \
  api/tests/test_gm_engine_properties.py api/tests/test_gm_goldens.py \
  api/tests/test_gm_core.py api/tests/test_gm_policy.py -o addopts=-ra
```

Expected/collected/executed/passed: 181. Failed/skipped/xfailed/not-run: 0.
Breakdown: independent QA 31, commercial 58, calendar 35, engine properties 19,
goldens 16, core 15, policy 7. Ruff and module mypy pass. The six independent
findings are **fixed and tested** locally. Integration, immutable persistence,
consumer adapters and deployed user journeys remain outside this proof; complete
S21-15/17/18 and T13/T15/T16 acceptance is not claimed.

## Persistence Consumer Adapter

`app.gm.commercial_adapter.to_template_result(schedule, *, us_floor, india_floor)`
returns the existing `TemplateResult` with two additive optional metadata fields:
`gm_outcome` retains the existing authority's status, reasons, location passes,
and recursive child outcomes; `commercial_schedule` retains the exact schedule,
component/calendar/source/policy/calculation versions and monthly rows.
`compute_commercial(component, *, us_floor, india_floor)` is the convenience
entrypoint for confirmed typed inputs. Neither adapter performs margin math.
Default floors remain the existing authority defaults; callers pass the immutable
resolved policy floors when they differ.

For an assessed result, legacy amount/GM fields copy the authority values without
rounding. `complete` is true only for an `ok` outcome; a tested child breach still
keeps `complete=True` but `gm_outcome.requires_ceo=True`. For incomplete/exception
results, GM fields remain `None`, `complete=False`, and reasons survive. The old
numeric zero defaults are compatibility placeholders, NOT financial truth.
Consumers must branch on `gm_outcome.status`, emit unassessed amounts as null,
and prevent auto-pass for non-`ok` outcomes. `requires_ceo` alone does not indicate
whether assessment was possible. Incomplete parent schedules now also retain
their available child assessments rather than dropping the tree.

Lead integration contract: store canonical typed `PricingComponent` inputs and
immutable schedule/outcome snapshots on the existing GM version; Decimal JSON
values are strings. Permission/source/version checks and typed parsing precede
`compute_commercial`. Route existing payload/live paths through that entrypoint;
format policy from the outcome rather than rechecking aggregate margins. These
service/schema/model/UI changes remain lead-owned and are not present here.
Legacy noncommercial results keep both metadata fields `None`.

Test-first: eight adapter cases initially failed collection because the adapter
module did not exist. They now pass, covering exact copied economics, child
policy breaches, custom floors, unknown cost, unsupported draft, zero revenue,
unassessed children and legacy defaults. Full targeted regression includes the
previous seven files plus `test_gm_policy_versioning.py` and all six template
test modules: 231 collected/executed/passed (17.10 seconds), zero failures/skips/
xfails. `test_gm_properties.py` separately passes 3 tests (4.12 seconds); separation
avoids that unchanged file's global Decimal-context mutation, already corrected
by the lead in integration. Ruff and module mypy pass. Independent QA evidence
files remain unchanged. This adapter is **fixed and tested** locally only; no
end-to-end or staging acceptance is claimed.

## Independent QA Follow-Up: Whole-Unit Ratio Loss

Bounded 30-minute commercial increment, starting from clean `98242b8`.
Lead-authorized QA commit `7778691b71795ec36202f5c3168b8304acb7c4ac` was
cherry-picked as `d33a6e8`; all three evidence files remain unchanged. The new
independent `test_derived_ratio_does_not_allow_losing_entire_currency_units`
first reproduced the silent loss of the entire 100/31 fee beside a 1E30 overage.
Both ordinary-proration independent tests passed in that same pre-fix run.

Ratio approximation now requires the existing 28-digit context to retain
fractional places at the result's magnitude. A derived approximation whose
least representable place is whole units or coarser remains unresolved. The
check applies to initial division, later revenue addition and hybrid FX scaling;
scaling already approximated input must be checked even when multiplication
itself is exact. Source-amount and cost precision guards are unchanged. No
currency quantization, minor-unit choice or replacement margin calculation was
added. Exactly representable large amounts and terminating large prorations
remain supported; normal recurring/calendar ratios are not blanket failures.

Five owned adversarial cases first failed for complete/partial base-fee loss,
division and two FX scaling variants. Two exact-large controls pass. Final full
targeted command (no filtering/skips/xfails):

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/test_s21_commercial_independent.py \
  api/tests/test_s21_commercial_profiles.py api/tests/test_s21_calendar_schedule.py \
  api/tests/test_gm_engine_properties.py api/tests/test_gm_goldens.py \
  api/tests/test_gm_core.py api/tests/test_gm_policy.py -o addopts=-ra --tb=line
```

Expected/collected/executed: 208. Passed: 199. Failed: 9. Skipped/xfailed/not-run:
0. All 34 independent engine/adapter cases pass, including the unchanged original
31 and the new precision case; commercial 73, calendar 35 and existing GM 57
also pass. The nine failures are the unchanged, lead-owned consumer regressions:
three child-floor authority consumers and six unassessed-placeholder response
cases. They are not hidden or represented as passing here. `gm/types.py`,
`gm/policy.py` and services were not edited. Ruff and module mypy pass.

This specific precision finding is **fixed and tested** locally. Lead consumer
integration, independent re-review, persistence workflows and staging acceptance
remain outside this increment. No complete S21-15/17/18 or T13/T15/T16 acceptance
is claimed.
