# Independent Forecast Engine QA

Run `QA-S21F-forecast-1`; bounded budget 25 minutes. Clean `s21/qa` worktree at
start. Authorized source commits: `47119a9 -> 7754fe9`, `fad62b3 -> 4986dc7`,
`ac47883 -> 885f75c`. Exact reviewed baseline:
`885f75c13a7e42c61509d5a86fadefee572a087d`. The missing session-02 document and
journey script caused modify/delete cherry-pick conflicts; the lead authorized
retaining their exact source-commit versions. Neither was executed or edited.

QA additions are limited to `api/tests/test_s21_forecast_independent.py` and this
report. No production edits, feature mocks, API calls, database use, migration
execution, deployment, cloud calls or subagents. Existing QA oracles were not
changed. Tests use literal Company X expectations and independent Decimal math.

## Findings

1. **P1: exact residual commercial money is excluded after partial conversion.**
   `api/app/gm/forecast.py:160` rounds the residual scope ratio before multiplying
   money at line 172. The subsequent precision trap treats its repeating tail
   as invalid input, dropping a legitimate unsigned remainder. For a 0.3-scope
   proposal of 300 revenue/150 cost at 50% probability, conversion of 0.1 scope
   to signed 100/50 leaves full unsigned 200/100. Expected combined money is
   **200/100**; actual is **100/50**, with the proposal excluded for precision.
   A 0.7-scope proposal of 700/350 and signed 0.2 scope of 200/100 similarly
   produces **200/100 instead of 450/225**. Both final expected amounts are
   exact; the half-scope control passes. Preserve exact fractions through the
   financial operations rather than rounding the dimensionless ratio first.
2. **P1: changing only a row ID duplicates the same source economics.**
   `api/app/gm/forecast.py:133` rejects duplicate row IDs, but has no equivalent
   identity check for account/source/version/scope/month. Replaying an otherwise
   identical row under a new row ID passes. With a 1,000-revenue tentative row
   at 50%, Expected doubles from 500 to 1,000. A signed row with 0.5 scope
   doubles from 1,000 to 2,000; the summed scope becomes one, so line 153's
   over-coverage guard misses the duplicate. Both tests require rejection of
   repeated economic input, consistent with the existing duplicate-row contract.
3. **P2: aggregate sums silently discard currency units below engine precision.**
   `api/app/gm/forecast.py:96` and line 99 sum revenue and cost in the default
   nontrapping context created at line 121. Exact individual rows containing
   `1E30` and `0.01` pass the per-row money checks, but the company total becomes
   `1E30`, with no precision reason. The independent 50-digit total is
   `1000000000000000000000000000000.01`. Both revenue and cost reproduce this;
   the aggregate can still claim complete cost and publish GM. Tests allow an
   exact result or explicit precision rejection/exclusion, not silent loss.
   This is an extreme-magnitude validation boundary, not a normal-scale claim.
4. **P2: blank FX/planning evidence is accepted as confirmed.**
   `_reasons` at `api/app/gm/forecast.py:80`, line 85 and line 87 uses truthiness
   for FX version, probability provenance and assumptions. Whitespace-only FX
   version, whitespace-only probability source, and an assumption tuple holding
   an empty string all contribute 625 reporting-currency revenue with no
   exclusion. Expected: zero contribution with an explicit missing-input reason.
   The None FX version/date controls are correctly excluded.

## Passing Evidence

The independent Company X fixture matches Committed, Expected and Upside.
Current-quarter revenue is 24,000/122,000/164,000; future two-quarter revenue is
0/196,000/280,000 and cost is 0/98,000/140,000. Current assessment cost remains
unknown; no current-quarter GM is fabricated. One/two/four future-quarter
selections expose six/nine/fifteen monthly buckets and exclude current-quarter
revenue from the future total. Los Angeles rollover at 2026-10-01 07:00 UTC
changes future Expected revenue from 269,000 to 196,000 as independently expected.

Signed unknown costs preserve known revenue and known-cost subtotal without
complete GM. Unsigned missing cost is excluded visibly. Unavoidable cost is
retained once while avoidable cost alone is probability-weighted. In the
1,000-revenue/600-cost fixture with 100 unavoidable and 25% probability, Expected
money is 250/225, Upside is 1,000/600, and Committed retains the separately
identified 100 unavoidable cost. Valid EUR conversion preserves source currency,
FX version and unweighted unavoidable cost. Lost/unselected alternatives do not
contribute; multiple selected sources and mixed source versions are rejected.
Full conversion affects only the matching account, scope and month.

## Execution

Existing lane-owned Python 3.14 venv; deterministic pure inputs. Postgres URL
unset so the repository's autouse migration fixture cannot access a database.

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/test_s21_forecast_independent.py \
  api/tests/test_s21_forecast_projection.py -o addopts=-ra -q
```

Expected/collected/executed **42**, passed **33**, failed **9**, skipped **0**,
xfailed **0**, not-run **0** within this selection; exit 1, 1.55 seconds.
All 11 existing projection cases pass. New independent cases: 31 collected,
22 passed/nine failed; initial standalone run 1.28 seconds. All original
assertions remain unchanged after their red result. No retries, skips, xfails
or assertions based on production-generated expectations. Ruff passes.

Failing collected node prefix: `tests/test_s21_forecast_independent.py::`:

- `test_partial_conversion_uses_exact_fraction_before_weighting[0.3-0.1-300-100-200-100]`
- `test_partial_conversion_uses_exact_fraction_before_weighting[0.7-0.2-700-200-450-225]`
- `test_duplicate_source_scope_month_cannot_be_reintroduced_with_new_row_id[tentative]`
- `test_duplicate_source_scope_month_cannot_be_reintroduced_with_new_row_id[signed]`
- `test_aggregate_money_preserves_cents_or_explicitly_reports_precision[revenue]`
- `test_aggregate_money_preserves_cents_or_explicitly_reports_precision[cost]`
- `test_unresolved_fx_or_planning_provenance_does_not_become_confirmed_money[changes2]`
- `test_unresolved_fx_or_planning_provenance_does_not_become_confirmed_money[changes3]`
- `test_unresolved_fx_or_planning_provenance_does_not_become_confirmed_money[changes4]`

## Scope Status

| Requirement | State | Evidence / Boundary |
| --- | --- | --- |
| FC-02 / FC-04 | fixed and tested | Bounded pure scenario/horizon/Company X checks only; no deployed view acceptance. |
| FC-05 | missing | Partial conversion, duplicate economic input, precision and missing provenance regressions above. |
| FC-06 | deferred | Actual import, recognized/billed basis and coverage replacement were not exercised. |
| FC-12 | deferred | Authorization, persisted outbox/jobs, stale snapshots and operational recovery were not exercised. |

No full S21F:T18/T19/T20/T21/T25 acceptance is claimed. Untested boundaries include
canonical conversion-link ownership, tenant/account permission filters, report
currency configuration, import corrections, full FX revision consistency,
persisted source uniqueness, concurrent writes, queue retries, all malformed
types, load, API/UI/export parity, migration/restore and staging journeys.
Lead owns the production fixes and persistence. QA has not approved future fixes.
