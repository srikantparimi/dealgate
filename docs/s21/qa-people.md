# Independent People Allocation QA

Baseline: `2761da9725b895f553206684a09b76b23c8c096a`, branch
`s21/qa-people-allocation`. Only this report and
`api/tests/test_s21_people_independent.py` are owned. Production and existing
tests are unchanged. Budget: 15 minutes; runtime is serialized with the lead.

## Scope and Oracles

Read `CLAUDE.md`, the People section of `docs/s21/contracts.md`, the proposed
`docs/s21/lanes/people-demand-contract.md`, T22/T23 acceptance, and the actual
pure allocator. Authored 30 cases with literal business expectations:

- Company X: 2 US plus 5 India people, November 2026 through April 2027, each
  month exactly 7 headcount / 7 FTE / 7 gap without supply, at probability 0,
  0.70, 1, and unknown. Probability never becomes staffing quantity.
- Global allocation: four half-time roles require 4 slots / 2 FTE. Gross
  capacity 1.50 minus unrelated commitment 0.50 leaves exactly 1 FTE; committed
  demand then stable IDs receive that budget, independent of input order.
- Six retained people explicitly committed to that same source remain six
  required, six matched, zero incremental, and zero unmet FTE. The fixture uses
  demand identity `signed-a` and commitment `source_id="signed-a"` to explicitly
  identify the same obligation. This is not a blanket exemption for retention:
  unrelated commitments still block availability, and a missing retained person
  cannot be replaced by an unlinked free candidate.
- Duplicate source/person commitments with overlapping periods are rejected;
  adjacent segments remain legal and subtract exactly once per date.
- Selection, identity, capability, Decimal allocation and local-date inputs
  fail closed or remain unresolved; whitespace is not confirmed capability.
- A commitment ending 29 February 2028 releases capacity on 1 March, not
  29 February. A valid accepted 9999-12-29 through 9999-12-30 interval needs
  only the representable exclusive boundary 9999-12-31.

## Execution

One authorized bounded run: **31 passed, 13 failed in 1.71s**, with zero skips
and zero xfails. New independent cases: **17 passed / 13 failed**. All 14
existing allocation cases passed. Tests were not changed after execution; no
reruns or assertion weakening. Exact command, from this worktree:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_people_independent.py api/tests/test_s21_demand_allocation.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-people-independent
```

## Reproduced Findings

All locations refer to
`api/app/gm/demand.py` at the baseline revision.

1. **High: false unmet demand for an already staffed continuing team.**
   Same-source retained commitments are subtracted at line 158, then retained
   people must have free capacity at line 172. No commitment-to-demand matching
   recognizes the already staffed obligation. Observed `matched_fte=0`, expected
   6 for a continuing six-person team with zero incremental demand. Important
   interface limit: same-source identity is supplied through the existing demand
   and commitment keys; no explicit distinct linkage field currently exists.
   Foreign-source commitments and missing-person controls both passed.
2. **Medium: overlapping versions/segments can subtract one commitment twice.**
   The commitment uniqueness check at line 127 includes exact start/end dates.
   Overlapping segments of one source/person identity therefore bypass it and
   are accepted instead of rejected. Adjacent segments passed the independent
   control and correctly leave the remaining half-time capacity available.
3. **Medium: selection accepts ambiguous non-boolean input.**
   `Demand.selected` has no boolean validation in `__post_init__` at line 49.
   Truthiness at line 131 can silently turn the string `"false"` into included
   demand, or unknown selection into confidently excluded demand. All four
   invalid inputs (null, string, integer zero/one) were accepted.
4. **Medium: blank capability is treated as confirmed information.**
   Capability validation at line 16 checks type but not whitespace. `_missing`
   at line 99 considers whitespace a known role/level/location, so two unknown
   values match at line 104. All three cases matched 1 FTE instead of preserving
   the 1-FTE unresolved gap.
5. **Medium: stable person keys are not validated.**
   Validation at line 77 only checks truthiness; true, integer 42 and whitespace
   were all accepted. Mixed key types can also make candidate sorting unsafe;
   that secondary effect is source review, not a separate executed test claim.
6. **Low: accepted final-year dates overflow an unnecessary boundary.**
   The accepted date range only rejects `date.max` as an end (line 24), but
   `_month_after` at line 109 constructs year 10000 for December 9999 even when
   the required exclusive boundary is representable. The test raised
   `ValueError: year must be in 1..9999, not 10000` during allocation.

Exact failing node suffixes, prefixed with
`api/tests/test_s21_people_independent.py::`:

```text
test_already_committed_continuing_team_is_not_subtracted_then_requested_again
test_overlapping_segments_of_one_commitment_are_rejected_not_double_subtracted
test_scenario_selection_requires_an_explicit_boolean[None]
test_scenario_selection_requires_an_explicit_boolean[false]
test_scenario_selection_requires_an_explicit_boolean[0]
test_scenario_selection_requires_an_explicit_boolean[1]
test_blank_capability_cannot_be_matched_as_confirmed_information[role]
test_blank_capability_cannot_be_matched_as_confirmed_information[level]
test_blank_capability_cannot_be_matched_as_confirmed_information[location]
test_person_identity_must_be_a_nonblank_stable_text_key[True]
test_person_identity_must_be_a_nonblank_stable_text_key[42]
test_person_identity_must_be_a_nonblank_stable_text_key[   ]
test_accepted_final_year_interval_does_not_require_an_unrepresentable_next_month
```

Passing new controls include the four full-headcount probability cases, two
global-order cases, foreign-source and missing-person continuity, adjacent
commitments, leap-day/month boundary, four invalid allocation cases and three
invalid local-date cases. No DB engine fixture was used. Lint was not run: the
runtime authorization was narrowly for this pure bounded pytest invocation.

## Boundaries Not Claimed

These are pure calculation tests with synthetic identities and no service mocks.
No DB fixture is requested. PostgreSQL, managed imports/freshness, tenant/role
projection, publication/source conversion, API/UI, lead-day rules, sourcing
draft persistence, audit/outbox, worker replay and prevention of actual hiring
or reservation side effects are outside this run. No company-approved fairness
or maximum-cardinality matching policy is inferred from the deterministic
proposal order. T22/T23 and FC-07/FC-08 are not accepted by these unit tests.

## Lead Remediation, 08:28 UTC

All 30 independent tests are unchanged. Fixes validate identity/selection types,
treat whitespace capability as unresolved, reject overlapping same-source
commitment segments, preserve the representable last-year interval, and credit
explicit same-source retained commitments without returning them to free supply.
Overcommitted people cannot be presented as a valid continuity match. Two further
literal controls cover retained half-time plus competing demand and conflicting
authoritative commitments. Combined: **46 passed in 1.12s**, no skip/xfail.
Command: `cd api && .venv/bin/pytest -o addopts='' -q tests/test_s21_demand_allocation.py tests/test_s21_people_independent.py`.
Log `docs/s21/evidence/baseline/people-qa-fixed-v2.log`. This remains pure-engine
proof; all managed People publication/import/UI/worker requirements remain open.
