# Global Allocation Static Review

Read-only review of the lead's **uncommitted** `people_allocation.py`,
`gm/demand_projection.py`, and `people_demand.py` integration changes in
`dealgate-s21-forecast`, 2026-10-02 09:52-09:56 UTC. Observed integration HEAD:
`1f37ca6132be2fc42f6c1acef207b71bb973d95d`. Locations below identify that read,
not a claim about subsequent lead edits. Budget: ten minutes. **No tests,
runtime, installation, DB access, or production changes were performed.**

These are concrete source-review findings requiring independent tests, not
executed reproductions or feature acceptance. Only this QA-owned report changes.

## Findings Requiring Tests

1. **High: current unstaffed sources lose their incompleteness.**
   `api/app/services/people_allocation.py:29` iterates `source["lines"]` before
   copying `source["missing"]` at line 31. A current publication containing no
   staffing lines has a component-level staffing missing reason, but that reason
   is never copied. With any managed supply source present, the final test at
   line 82 can return `complete=true`, empty months, and no missing reasons.
   Proposed case: publish a plan with an empty canonical staffing tuple; import
   a valid roster; read allocation. Assert incomplete and preserved source-level
   staffing reason, not an apparently complete zero-demand result.

2. **High: hidden incomplete competing demand disappears from global
   completeness.** Non-current sources are skipped at lines 25-28, with pending
   evidence added only for `visible` plans. Invalid/unknown current lines are
   similarly skipped without anonymous global missing evidence at lines 32-45.
   The remaining supply is allocated as if the hidden demand did not exist, and
   a Sales/account-filtered view can claim `complete=true`. The calculation is
   global for known valid rows, but its completeness is only display-scoped.
   Proposed cases: one visible published full-time role, one hidden pending or
   stale competing role, one person with capacity 1. Assert a generic global
   incompleteness marker and provisional, not confirmed-complete, totals. The
   response must not expose hidden plan IDs, account names, or person links.

3. **Medium: valid exact source quantities can raise an uncaught arithmetic
   exception for every allocation reader.** The call to `allocate_demand` at
   line 61 and scoped aggregation at line 64 are outside the source-construction
   exception handler. `GM_PRECISION` is **28** and both math functions trap
   `Inexact`. A canonical source with quantity 2 and allocation
   `Decimal("0." + "9" * 28)` is accepted, but its exact required FTE is
   `1.9999999999999999999999999998`, requiring 29 significant digits. The pure
   engine multiplication can therefore escape the endpoint instead of producing
   an explicit incomplete/error result. Proposed case: save/publish that exact
   source and read allocation; assert no uncaught exception/500 and no fabricated
   zero gap. The current managed-import validator rejects more than 28 fractional
   places, so a gross-1/commitment-1e-49 example is **not** a valid import-path
   repro and must not be used. No rounding or weaker arithmetic oracle is advised.

4. **Medium: inactive/unselected pending sources falsely block completeness.**
   Lines 25-28 inspect publication state before the source's selected/lifecycle
   eligibility. The pure engine excludes `closed_lost`, `dismissed`, `expired`
   and `selected=false`, but it never receives these pending sources. Thus a
   known inactive plan can remain in `pending_sources` indefinitely and keep an
   otherwise complete portfolio incomplete. Proposed parameterized case: one
   valid active publication and valid roster plus an unpublished inactive or
   unselected plan. Assert the inactive source is classified as excluded, does
   not add active headcount, and does not require publication to clear active
   population completeness. Unknown selection must remain unresolved, not be
   treated as this explicit false control.

5. **Medium: account-filtered totals are still labeled company-wide.**
   Lines 19-21 restrict visible demand by `account_id`, and `scoped_intervals`
   correctly recomputes visible monthly totals without reallocating supply.
   However, line 81 chooses `Company demand` solely from the actor's role. An
   HR/Finance account-filtered response therefore labels subset totals as company
   demand. Proposed case: two accounts with different headcounts; request one
   account as an organizational reader; assert its original global matches are
   preserved and its totals carry an explicit selected-account scope label.

## Relevant Observations

The inspected global known-demand path runs allocation before display filtering,
and non-HR/Admin responses remove candidate matches, overcommitted-person IDs,
and raw continuity-ID missing messages. No direct named-ID leak was found in
those inspected output paths. `scoped_intervals` uses explicit Decimal precision
and sums FTE; no float arithmetic or probability-weighted headcount was found.

Managed-source age is explicitly measured rather than claimed live. This review
does not invent a stale-age threshold or request an undeclared freshness policy.
Publication state remains distinct from global matching completeness. The lead
acknowledged findings 1-3 and is preparing guards; no such fix was independently
tested here. Existing allocation tests inspected cover known complete competing
plans and visible pending demand, not the falsification cases above.
