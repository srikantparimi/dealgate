"""T19 · stale-tab approval refused (S20 · W5).

Per review + T19:
> Complete all required functions; reject and request changes; assign
> rework and resubmit. A stale browser version is refused by the server.

Per contract §0.5 / §8: server enforces every state change. A disabled
button is not a control — the server MUST reject with 403 + explicit
reason if the version behind the decision has moved.

**Skeleton, xfail until W3 lands the approvals engine with version
guards.**

Test cases:
  1. Two tabs open on the same package. Tab A submits an approval.
     Tab B (which still sees the previous version) submits a
     conflicting decision → server returns 409 with
     reason "version_conflict" and evidence of the current version.
  2. After a material change creates a revision (T21), any decision
     against the previous SOW version is rejected.
  3. The rejection includes the current package version so the SPA
     can invalidate its cache and refresh.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W3 approvals with version guard", strict=False)
@pytest.mark.asyncio
async def test_stale_tab_decision_returns_409(session):
    """
    Given: package v3 in review; tab A submits an approve decision
    while tab B holds v2.
    When:  tab B posts approve with version=v2.
    Then:  server returns HTTP 409, error_code "version_conflict",
           payload includes current_version=v3.
           No decision row is created.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 material-change revision path (T21)")
@pytest.mark.asyncio
async def test_decision_against_pre_revision_version_refused(session):
    """
    Given: package v3 approved, then a material change bumps to v4.
    When:  a decision arrives claiming version=v3.
    Then:  server returns 409 with reason "version_superseded".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 approvals engine")
@pytest.mark.asyncio
async def test_rejection_payload_includes_current_version(session):
    """
    Given: any version-conflict rejection above.
    Then:  the JSON response body contains `current_version` so the
           SPA can refresh state without another round trip.
    """
    raise AssertionError("skeleton")
