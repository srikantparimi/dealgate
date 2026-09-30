"""T20 · CEO exception conditional (S20 · W5).

Per review:
> Below-floor model requires a valid exception; compliant model says
> Not required. Test conditions, expiry, decline and material revision.

**Skeleton — the CEO exception service exists (`api/app/services/ceo_exception.py`);
this test asserts the exact conditional surface required by T20.**

Test cases:
  1. Compliant package → CEO exception surface reads "Not required".
     Server refuses submission of a CEO decision on that package.
  2. Below-floor package → CEO exception is required to release;
     server refuses handoff without an approved exception.
  3. Approved exception with conditions (e.g. "renewal at >= 45%") →
     conditions are enforced at release check.
  4. Approved exception with expiry → after expiry, the exception is
     `Failed` and the package returns to blocked.
  5. Declined exception → package stays blocked with reason on the row.
  6. Material change AFTER an approved exception invalidates the
     exception (T21 linkage).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W3 CEO surface + gm assessment", strict=False)
@pytest.mark.asyncio
async def test_compliant_package_reads_not_required(session):
    """
    Given: package with GM 45% (above floor).
    When:  GET /packages/{id}/ceo-exception-state
    Then:  response.state == "not_required".
           POST /ceo-exceptions with this package_id returns 400.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 CEO service + gm below-floor detection")
@pytest.mark.asyncio
async def test_below_floor_package_requires_exception(session):
    """
    Given: package with GM 30% (below 35% floor).
    Then:  state == "required";
           attempt to release without an approved exception returns 409
           with reason "ceo_exception_missing".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 CEO exception conditions engine")
@pytest.mark.asyncio
async def test_conditions_are_enforced_at_release(session):
    """
    Given: below-floor package with an approved CEO exception whose
    conditions include "renewal margin >= 45%".
    When:  release check runs.
    Then:  the check evaluates the condition against the current
           snapshot; a failing condition blocks release with a
           reason that names the failing condition.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 CEO exception expiry")
@pytest.mark.asyncio
async def test_expired_exception_blocks_release(session):
    """
    Given: an approved CEO exception with expires_at in the past.
    Then:  package.gate_state == "blocked_expired_exception".
           A retry to release returns 409.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 material-change invalidation (T21)")
@pytest.mark.asyncio
async def test_material_change_invalidates_exception(session):
    """
    Given: below-floor package with approved CEO exception; price
    changes materially (T21).
    Then:  the exception is invalidated; a new exception is required.
           Audit event names the invalidating change.
    """
    raise AssertionError("skeleton")
