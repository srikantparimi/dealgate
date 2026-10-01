"""T33 · scan resume without premature archive (S20 · W5).

Per review + A3:
> Fail a scan midway, resume it, and simulate overlapping runs; no
> premature archives or lost seen-set. Preserve records created during
> the scan.

Rule: archive only after an authoritative full scan completes. Persist
the scan generation and seen-set across resumes; distinguish filtered
scans; prevent overlapping generations from archiving one another's
records. A failure after one page must archive nothing.

**Skeleton, xfail until W1 lands scan-generation semantics.**

Test cases:
  1. Scan generation N starts, processes page 1, then fails before
     page 2. No records are archived. On next tick, generation N
     resumes from the cursor; only after the full scan completes does
     archiving of not-seen records commence.
  2. A record created DURING the scan (arrived via webhook mid-scan)
     is NOT archived, even though it wasn't in generation N's seen-set.
  3. Two generations running simultaneously (rare but possible during
     rollout) do not archive each other's records. The lock is on
     `scan_generation_id`, not just "a scan is running".
  4. A filtered scan (e.g. by pipeline) does not archive records
     outside its scope; the filter is included in the scan
     generation's metadata.
  5. Rollback: after a bad scan, we can restore the archived_at column
     from the audit table.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W1 scan generation semantics (A3)", strict=False)
@pytest.mark.asyncio
async def test_partial_scan_archives_nothing(session):
    """
    Given: 100 opportunities in the mirror; a scan starts and
    processes 50, then fails.
    When:  we query the archive counts.
    Then:  archived_at IS NULL for all 100. No premature archives.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 mid-scan-record protection")
@pytest.mark.asyncio
async def test_mid_scan_record_is_not_archived(session):
    """
    Given: scan generation N starts; a webhook-created opportunity
    lands mid-scan (created_at > scan.started_at).
    When:  the scan completes.
    Then:  the new opportunity is NOT archived (it wasn't visible to
           the source listing at scan start).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 generation lock")
@pytest.mark.asyncio
async def test_overlapping_generations_do_not_archive_each_others_records(session):
    """
    Given: generation N running, we start N+1 (simulated overlap).
    Then:  the scan_generation_id lock rejects the second start OR
           both scans complete without archiving records that only
           the other saw.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 filtered-scan metadata")
@pytest.mark.asyncio
async def test_filtered_scan_does_not_archive_out_of_scope(session):
    """
    Given: a scan limited to pipeline "Renewals"; global mirror has
    opportunities in every pipeline.
    Then:  no non-Renewals opportunity is archived.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 rollback support")
@pytest.mark.asyncio
async def test_rollback_restores_archived_at(session):
    """
    Given: a bad scan archived 42 real opportunities.
    When:  we run the documented rollback (invert `archived_at` set by
    generation N from the audit table).
    Then:  those 42 rows have archived_at IS NULL again;
           audit table logs the rollback event.
    """
    raise AssertionError("skeleton")
