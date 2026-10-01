"""T14 · many SOWs per deal (S20 · W5).

Per D1 (fixed decision, contracts.md §2):
- Each SOW package has its own versions, gate, value and approval history.
- Deal rollup headline = most-blocked open package by order:
  `changes requested > CEO exception > in review > awaiting signature > approved > draft`.
- Archived/superseded excluded from headline, counted separately.
- A released SOW never hides a pending one.

**Skeleton, xfail until W3 relaxes `sow.opportunity_id` uniqueness (via
`requests.md`; Lead applies the migration).**

Assertions (skeleton, one test per contract clause):
  1. Two SOW packages under one opportunity persist independently.
  2. Each package's `status` and `version_number` history is isolated.
  3. Deal rollup headline picks the most-blocked open package.
  4. Approving package B while package A is `changes_requested` DOES
     NOT change the headline until A resolves.
  5. Archiving a package removes it from the headline calculation but
     keeps its count in `archived_count`.
  6. Releasing one package never hides a pending sibling package.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason="depends on W3 request to relax sow.opportunity_id uniqueness (D1)",
    strict=False,
)
@pytest.mark.asyncio
async def test_two_packages_persist_independently(session):
    """
    Given: opportunity O has SOW_A (in review) and SOW_B (draft).
    Then:  both persist; SOW_A.status != SOW_B.status; no unique-key
           collision on (opportunity_id).
    """
    raise AssertionError("skeleton: implement once W3's migration lands")


@pytest.mark.xfail(reason="depends on W3 multi-SOW support")
@pytest.mark.asyncio
async def test_version_history_isolated_per_package(session):
    """
    Given: SOW_A has versions v1, v2; SOW_B has versions v1, v2, v3.
    Then:  SOW_A.latest_version == v2 and SOW_B.latest_version == v3;
           bumping SOW_B does not touch SOW_A's version chain.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 rollup headline computation")
@pytest.mark.asyncio
async def test_rollup_headline_picks_most_blocked_open_package(session):
    """
    Given: SOW_A = `changes_requested`, SOW_B = `approved`,
           SOW_C = `draft`.
    Then:  rollup.headline_status == "changes_requested"
           (per D1 order).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 rollup + archive semantics (D1)")
@pytest.mark.asyncio
async def test_archived_package_excluded_from_headline_counted_separately(session):
    """
    Given: SOW_A = `archived`, SOW_B = `in_review`.
    Then:  rollup.headline_status == "in_review".
           rollup.archived_count == 1.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 rollup rules (D1)")
@pytest.mark.asyncio
async def test_released_package_never_hides_pending_sibling(session):
    """
    Given: SOW_A = `released` (signed + delivered), SOW_B = `awaiting_signature`.
    Then:  rollup.headline_status == "awaiting_signature".
           A released SOW does not conceal a pending one — the review's
           strongest wording (contracts.md §2 D1).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 approvals engine")
@pytest.mark.asyncio
async def test_decisions_do_not_cross_package_boundaries(session):
    """
    Given: SOW_A has a Legal-approve decision, SOW_B has none.
    When:  we query SOW_B's decisions.
    Then:  the Legal-approve decision does NOT appear on SOW_B.
           (Regression guard: A1 says versions must be per-SOW; a
           shared decision table cannot leak across package_id.)
    """
    raise AssertionError("skeleton")
