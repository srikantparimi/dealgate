"""T28 · sync edge cases (S20 · W5).

Per review:
> Exercise duplicate/out-of-order events, property clears, owner/stage
> rename, association change, merge/delete and failed job recovery
> without data loss.

**Skeleton, xfail until W1 lands the full event handler set.**

Test cases (one per edge case):
  1. Out-of-order events: event B (t=10) arrives before event A (t=5).
     Final state reflects event B (the later timestamp wins per its
     documented rule). Audit records both.
  2. Property clear: `hubspot_owner_id = ""` clears the mirror's
     `source_owner_id` (nullable), sets display to "Unassigned".
  3. Owner rename: existing rows update to the new name; archived
     rows preserve the old + new for audit.
  4. Stage rename: labels update on next reconcile; the stage_id
     stays stable so filters keep working.
  5. Association change: adding/removing a company from a deal is
     mirrored; the global deal count doesn't double.
  6. Merge/delete: source deal deleted → mirror row `archived_at`
     set; downstream SOWs / decisions preserved.
  7. Failed job recovery: after a worker crash mid-batch, a re-run
     from the last-processed cursor picks up cleanly.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W1 sync engine", strict=False)
@pytest.mark.asyncio
async def test_out_of_order_events_final_state_correct(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 property-clear handling")
@pytest.mark.asyncio
async def test_property_clear_sets_unassigned(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 owner mirror rename")
@pytest.mark.asyncio
async def test_owner_rename_updates_label(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 stage mirror rename")
@pytest.mark.asyncio
async def test_stage_rename_updates_label_stable_id(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 association handler")
@pytest.mark.asyncio
async def test_association_change_no_double_count(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 merge/delete handler")
@pytest.mark.asyncio
async def test_deleted_deal_archives_mirror_preserves_sow(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 cursor + resume")
@pytest.mark.asyncio
async def test_worker_crash_resumes_from_cursor(session):
    raise AssertionError("skeleton")
