# T21 Coverage Replacement

2026-10-02 23:57 UTC. Base8ec2a8efe1ee3988484773a51ac544f4f249594a.
T21.07 is missing; no scenario or parent closure until connected assertions pass.

## Contract

Optional `coverage` on an immutable financial revision binds to its existing
account, gm_model_id and period_month. Fields: `sow_version_id` (UUID),
`schedule_row` (nonnegative integer in the frozen schedule), `fraction_start`
and `fraction_end` (exact decimal strings, 0 <= start < end <= 1),
`through_date` (stated actual cutoff), and `basis_evidence` (nonblank written
Finance confirmation). Fractions identify an explicitly certified portion of
that row's service scope; they are NOT elapsed-day prorating. Manual evidence
is necessary because neither invoices nor dates establish recognition/service
equivalence. Only recognized_revenue and delivery_cost support coverage.

Match exact signed GM/SOW version, account, month, row and currency/explicit FX.
Reject unsupported measures, wrong scope, future cutoff, overlapping active
intervals for the same row/measure, detached or unsigned sources. Corrections
replace latest source revision when validating overlap, never update history.
Legacy uncovered rows stay separate with a reason. Independent revenue and cost
coverage cannot suppress or invent one another. Reject an entire invalid batch.

Keep Signed schedule unchanged. Add Finance/Admin-only `current_period_estimate`
for the current reporting month: original signed amounts, matched actuals,
covered fraction, uncovered forecast, estimated amounts and exact reconciliation
sources/reasons. No unsigned weighting or billed/cash blending. Unknown cost
and zero revenue remain unassessed. No mutation to signed GM or baseline.

## Ownership

Lead integration tree: contract/model/migration0062 (verify single head first),
import validation and locking, outlook, UI and connected proof. Only lead
integrates or owns runtime.

Worker /root/s21_governance: new separate tree
`/Users/srikanthparimi/OfficeApp/dealgate-s21-actual-coverage`, branch
`s21/actual-coverage`, base above. ONLY `api/app/gm/coverage.py`,
`api/tests/test_s21_actual_coverage.py`, `docs/s21/lanes/actual-coverage.md`.
Pure function + literal tests; no runtime/database/cloud and no shared-file edits.
One light worker; QA review after implementation, one heavy test at a time.

Pure API: `reconcile_actual_coverage(schedules, records, *, as_of, timezone,
currency)`; schedules are dictionaries with row_id (`GM:index`), account_id,
source_id (GM), source_version (SOW), month (ISO), currency, revenue, cost.
Records match financial_records JSON and optional coverage above. Return
`rows`, `excluded` (id/reason), `cutoff`, `currency`, `totals`.
Rows preserve row_id and source/account/version/month, each measure has
`scheduled`, `actual_to_date`, `covered_fraction`, `uncovered_forecast`,
`estimate`, `actual_ids`; totals expose revenue, cost, profit, gm_pct.
All money/fractions Decimal, no display rounding or floats. Invalid matching
is excluded visibly, not counted; overlapping groups exclude all participants.

Oracle: signed24000/10000, half scope recognized11000.99/cost6000 ->
estimate23000.99/11000, profit12000.99. Billed15000/cash8000 remain separate.
Correction recognized10500 ->22500/11000. Replay adds no revision.
Test mismatches/overlaps/cutoff/FX/unknown costs independently before browser.
