# Projection Independent QA Repairs

Isolated branch `s21/demand-projection-fix`, baseline `656b0ac`. Owned only
`api/app/gm/demand_source.py`, new repair tests and this report. Independent QA
tests and all existing tests are unchanged.

## Changes

- Every hybrid child must match its enclosing source ID, source version and
  policy version. This applies recursively, not just assignment-to-leaf.
- Confirmed child bounds must fit within confirmed parent bounds. A narrower
  child period remains valid; dates are not forced equal. Unknown component
  dates stay explicit missing fields and are not inherited from parents.
- Differing child currency/timezone remain allowed: only the child and its own
  assignment must match. No FX or pricing completeness is required to count
  people. Well-bound nested staffing can still be traversed independently of
  the commercial calculator's flattened-hybrid requirement.
- Source evidence is checked independently of enrichment evidence. Empty or
  invalid source evidence stays missing at component and line level, even
  with manual HR capability evidence. Invalid blank references are not copied
  into the output; known headcount is retained.
- Duplicate skill keys reject. Registered profile version is required, not
  just a recognized profile name. Wrong/missing typed hybrid structure rejects;
  an empty typed hybrid has explicit `components` missing, including when it
  contains parent staffing. Non-hybrids cannot hide a hybrid child container.

No financial values, money calculations or probability multipliers were added.
All immutable source inputs remain unchanged. Missing component-level date
reasons are additive to existing line-level reasons.

## Evidence

Before production edits: **20 failed, 15 passed in 2.90s**. This reproduced all
11 unchanged independent QA failures plus nine repair-edge failures. One newly
authored blank-version fixture initially failed canonical assignment
construction; it was corrected to exercise an unstaffed component's unsupported
version directly, without altering the rejection assertion.

After edits: **162 passed in 6.21s**, no skips or xfails. This includes all 25
independent QA cases, 10 new repair cases, 38 prior projection cases and existing
allocation/commercial-profile coverage. Exact command:

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-demand-projection-fix/api
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_demand_source_independent.py tests/test_s21_demand_source_fix.py tests/test_s21_demand_source.py tests/test_s21_demand_allocation.py tests/test_s21_commercial_profiles.py -q -o addopts= -p no:cacheprovider --tb=short
```

Runtime slot released after the run; no processes remain. Publication, database
constraints, routing, connected UI, sourcing and staging remain separate
lead-owned verification. These pure tests do not establish FC-07 completion.
