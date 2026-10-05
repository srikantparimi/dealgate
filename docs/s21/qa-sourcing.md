# Independent Sourcing QA

Baseline: `3504a65e47a813a0917d412e2e5f031dc3cb612f`.
Branch: `s21/qa-sourcing`. Budget: approximately 15 minutes of bounded review
and authoring, followed by the lead-authorized serialized pure test run.
Only this report and `api/tests/test_s21_sourcing_independent.py` changed.
No application changes, existing-test edits, skips, retries or assertion
relaxation. No database, browser, migration, cloud or installation was used.

## Results

From this worktree root, using the existing QA venv read-only:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_sourcing_independent.py api/tests/test_s21_sourcing_dates.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-sourcing-independent
```

Observed: **6 failed, 54 passed in 3.20s**, exit 1. The 31 independent cases
contributed 25 passes and six failures; all 29 existing worker cases passed.
Zero skips or xfails. The runtime slot was released immediately after exit.

All expectations are literal dates, integer headcounts and exact Decimal
constants. Tests call the real pure `prepare_sourcing`, with no mocked feature
responses and no production result used to generate expected results.

## Findings

### 1. An Uninterrupted Gap Gets A Later Deadline Each Month

`api/app/gm/sourcing.py:138` subtracts lead days from each allocation interval
start. `prepare_sourcing` carries only the previous interval end (`:153-168`),
not the beginning of an ongoing gap. An unchanged two-slot shortfall starting
1 November and continuing through December and January produces sourcing-by
dates **17 September, 17 October, 17 November**. The independent expectation is
**17 September for all three**, because the gap never closes.

This contradicts the actual-first-gap-date rule in
`docs/s21/contracts.md:322`. It is reachable from ordinary valid allocation
output because allocation splits at month boundaries (`api/app/gm/demand.py:152-155`).
It risks making an overdue sourcing need look progressively less overdue.
Controls prove a fully filled interval followed by a reopened shortfall gets
a new deadline, and a hole with no input coverage is not assumed continuous.

Red node: `test_continuous_monthly_gap_keeps_its_actual_first_gap_deadline`.

### 2. One Named Person Can Fill Two Concurrent Full-Time Demands

The match identity set is local to one row (`api/app/gm/sourcing.py:96-108`);
the interval loop checks only duplicate demand IDs (`:161-166`). Two distinct
demand rows can each claim the same person at allocation 1 and both emerge with
zero gap and no sourcing date. Expected: reject the internally contradictory
global allocation. Two allocation-0.5 slots using that same person remain valid,
and the independent half-time control passes.

This is pure-input validation, not a demonstrated bypass of the actual global
allocator or a claim that a public endpoint accepts raw matches. The valid
allocator normally prevents this case; validation is needed before treating
a malformed snapshot as a valid sourcing proposal.

Red node: `test_one_person_cannot_fill_two_full_time_demands_in_one_interval`.

### 3. A Stable Demand ID Can Change Its Owner Between Intervals

`api/app/gm/sourcing.py:65` accepts each row's account/plan identities independently,
and `:161` resets demand identity tracking for every interval. The same demand ID
can move from account X to a different account, or from plan X to a different
plan, on 1 December without rejection. Expected: reject inconsistent ownership
for one stable source identity in a single input snapshot. Stable production
demand IDs derive from publication identity plus line key, not mutable display
labels (`docs/s21/contracts.md:302-304`). No rule is imposed on changes between
separate source snapshots.

These are malformed-input provenance guards, not evidence of an externally
reachable authorization flaw. Within-interval duplicate IDs already reject and
remain covered by a passing control.

Red nodes:
- `test_stable_demand_identity_cannot_change_owning_source_between_intervals[account_id-other-account]`
- `test_stable_demand_identity_cannot_change_owning_source_between_intervals[plan_id-other-plan]`

### 4. Invalid Nonempty Timezones Are Treated As Complete

`api/app/gm/sourcing.py:67-70` checks normalized text but never validates an IANA
timezone. Both `Mars/Olympus` and `UTC+05:30` produce a sourcing date and an empty
missing list. Expected: reject malformed nonempty timezone evidence instead of
presenting a complete date-based proposal. Explicitly blank timezone is a
different unresolved-input case and is not changed by these tests.

The upstream Demand model validates IANA timezones (`api/app/gm/demand.py:26-27`),
so these cases expose a pure sourcing validation boundary, not a proven current
API path. Valid Los Angeles, Kolkata and Kiritimati date-only inputs preserve
their local calendar day through DST/extreme offsets in passing controls.

Red nodes:
- `test_nonempty_invalid_timezone_cannot_become_complete_sourcing[Mars/Olympus]`
- `test_nonempty_invalid_timezone_cannot_become_complete_sourcing[UTC+05:30]`

All node suffixes above are prefixed by
`api/tests/test_s21_sourcing_independent.py::`. All six red assertions remain
unchanged for the production owner to fix and independently reverify.

## Passing Boundaries

Exact zero-day skill rules override longer wildcards regardless of order;
unmatched required skills use the location wildcard, with the longest applicable
lead time. No case normalization, skill equivalence or location wildcard is
invented. Moving November's start to December moves the literal 45-day deadline
from 17 September to 17 October. Leap-year and minimum/maximum supported calendar
dates work, and input objects remain unchanged.

Six retained half-time people plus two incremental half-time slots remain eight
people, with six matches and two incremental gaps totaling one FTE. An unmatched
six-person retained team is continuity risk, not six new hires. Forged display
counters are recomputed; invalid slot totals and false continuity math reject.
Nested private identity/cost fields are not echoed, and 28-place fractional
allocation stays exact under a two-digit ambient Decimal context.

## Acceptance Boundary

FC-07/T22/T23 connected acceptance remains **missing** from this pure audit.
0058 persistence, permissions, CAS, source freshness, history, UI behavior and
0059 worker/events were not tested. No production fix or full feature acceptance
is claimed. Existing lead-owned proofs are not replaced by this report.
