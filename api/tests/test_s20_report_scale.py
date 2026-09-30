"""T42 · reporting at > 100 records + approval-turnaround (S20 · W5).

Per review:
> Test more than 100 records, including closed and unknown-stage
> records. Verify chart labels, stated scope, filters, drill-through
> and complete exports. Implement and validate turnaround aggregates.

L18: approval-turnaround endpoint explicitly stated "not live". D5 says
tonight's tests must land it OR mark the row `missing` with an owner +
next action.

**Skeleton, xfail until W4 lands the aggregate.**

Test cases:
  1. Portfolio at scale: seed 120 opportunities across pipelines, some
     closed, some with unknown stage; the report reads all 120 with
     an "unknown_stage" bucket for the missing ones.
  2. Approval-turnaround aggregate: given N packages with landed
     approvals, the aggregate reports median + p90 turnaround per
     function (Delivery, HR, Finance, Legal).
  3. If the aggregate is not live tonight, the response returns
     `state: "missing"` with a next-action string, NOT a fake 0.
  4. Export of the same report contains all 120 rows.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W4 portfolio at scale", strict=False)
@pytest.mark.asyncio
async def test_report_covers_120_rows_incl_closed_and_unknown_stage(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 approval-turnaround endpoint (L18)")
@pytest.mark.asyncio
async def test_approval_turnaround_median_and_p90(session):
    """
    Given: 30 approved packages spread over 60 days.
    When:  GET /api/reports/approval-turnaround.
    Then:  response has median_hours + p90_hours per function;
           NOT `unavailable` or `not live`.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 honest-status handling")
@pytest.mark.asyncio
async def test_missing_aggregate_reads_state_missing_not_zero(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 export at scale")
@pytest.mark.asyncio
async def test_export_covers_all_rows(session):
    raise AssertionError("skeleton")
