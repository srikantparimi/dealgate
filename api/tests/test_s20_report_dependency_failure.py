"""T39 · report dependency failure surface (S20 · W5).

Per review:
> Simulate one report/summary dependency failure. Show unavailable with
> a useful error while independent sections remain accurate. Never
> substitute zero or claim all data current.

L01 was the driver: Command center showed a "database-shape error"
while ALSO displaying zero agreement documents and $0 open pipeline;
Pipeline showed USD 21.6M / 106 open. Independent metrics MUST NOT
silently fall back to zero when one dependency fails.

**Skeleton, xfail until W4 lands the graceful-failure surface.**

Test cases:
  1. Simulate the agreements service throwing on the Command center
     summary. The agreements metric renders "Unavailable" with the
     error type; the pipeline metric renders its correct value.
  2. Never write zero for a broken metric. The response envelope for
     the broken metric carries `state: "Failed"` per contract §3.
  3. The failure surface renders a next action (retry / raise ticket)
     and links to `/settings/health`.
  4. Regression from L01: no metric may read "$0" without a proven
     zero — the underlying query must have returned 0 rows, not
     errored.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W4 command-center summary surface", strict=False)
@pytest.mark.asyncio
async def test_agreements_failure_does_not_zero_pipeline(session, monkeypatch):
    """
    Given: agreements service raises OperationalError.
    When:  GET /api/command/summary.
    Then:  response.agreements.state == "Failed";
           response.agreements.reason is a non-empty string;
           response.pipeline.open_value == the same value as
           /api/pipeline/summary would have returned unmocked.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4")
@pytest.mark.asyncio
async def test_no_zero_substitution_for_failed_metric(session, monkeypatch):
    """
    Given: any dependency in the summary path raises.
    Then:  the affected metric MUST NOT read 0/None; it reads
           `state="Failed"` with `value=None`. Zero is reserved for
           verified states (contract §1).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 health surface")
@pytest.mark.asyncio
async def test_failure_surface_links_to_health(session, monkeypatch):
    """
    Given: a report dependency failure.
    When:  the SPA renders the metric card.
    Then:  the card includes an actionable next step ("View health")
           that navigates to /settings/health with an anchor to the
           broken dependency.
    """
    raise AssertionError("skeleton")
