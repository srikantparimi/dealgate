"""T24 · baseline / forecast / actuals kept distinct (S20 · W5).

Per review:
> Enter forecast, partial actuals and duplicate imports; keep original
> baseline, period actuals and forecast distinct; trigger recovery on
> deterioration.

**Skeleton, xfail until W7 lands the projects/actuals/forecast surfaces.**

Test cases:
  1. Baseline is set on release; NEVER updated. A subsequent
     "baseline import" is a NEW baseline version with a superseded_by
     link, not an UPDATE (rule 4 for records that carry approval
     evidence).
  2. Forecast can be revised; forecast history is preserved.
  3. Actuals for period P override the previous P entry only via a
     NEW actuals row; the old row is kept for audit.
  4. Duplicate import of the same period + same total is rejected
     with reason "duplicate_import"; the source event id (D7) is used
     as dedup key.
  5. Deterioration (actuals below baseline by threshold) triggers a
     `recovery_required` flag; that flag routes to the delivery owner
     for the accountable next action.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W7 baseline snapshot on release", strict=False)
@pytest.mark.asyncio
async def test_baseline_is_immutable(session):
    """
    Given: released package with baseline_value = 100000, gm = 45%.
    When:  a "baseline update" import runs.
    Then:  the original baseline row remains at 100000/45%;
           a NEW baseline row is created marked `superseded_by`
           the new one.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 forecast versioning")
@pytest.mark.asyncio
async def test_forecast_history_preserved(session):
    """
    Given: forecast v1 = 100k; a revision sets v2 = 95k.
    Then:  both rows exist; v1.superseded_by == v2.id.
           Reporting reads v2 by default; audit-viewer sees both.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 actuals import path")
@pytest.mark.asyncio
async def test_actuals_new_row_never_updates_old(session):
    """
    Given: actuals for period 2026-08 = 30000.
    When:  a re-import for the same period arrives with 32000.
    Then:  the 30000 row stays; a NEW row for 2026-08 = 32000 is
           inserted with `supersedes` pointing at the previous row.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 + W7 dedupe key (D7)")
@pytest.mark.asyncio
async def test_duplicate_import_rejected_by_source_event_id(session):
    """
    Given: actuals import event_id "evt-42" already applied.
    When:  a duplicate delivery of "evt-42" arrives.
    Then:  server returns 200 with `deduped=true`; NO new actuals row;
           NO duplicate audit event. Uses D7 source event id, not the
           SQS message id.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 recovery-flag emitter")
@pytest.mark.asyncio
async def test_deterioration_triggers_recovery_flag(session):
    """
    Given: baseline gm = 45%; latest actuals compute to gm = 33%.
    Then:  package.recovery_required is True; a task appears in the
           delivery owner's My work queue; the flag surfaces on the
           projects listing.
    """
    raise AssertionError("skeleton")
