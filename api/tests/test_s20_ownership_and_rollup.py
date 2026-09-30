"""T31 · separate source owner / local assignee + per-SOW rollup (S20 · W5).

Per A1:
> Add or verify a separate source owner reference and resolve it
> through the owner mirror. An optional local-user mapping serves
> tasks and access only.
>
> Keep authoritative gate/release state per SOW; define an explicit
> deal rollup so one released SOW cannot conceal another pending
> package.

**Skeleton — folds together T04 (owner mirror) and T14 (per-SOW rollup)
into a small dedicated assertion of the D1 rollup ordering headline.**

Test cases:
  1. Opportunity.source_owner_id is a HubSpot owner id (not a
     DealGate user UUID). The local assignee (task owner) lives on a
     separate `assignee_id` column.
  2. Two SOW packages per deal, each with its own gate and release
     state, produce a rollup whose headline follows D1 ordering:
     `changes requested > CEO exception > in review > awaiting
     signature > approved > draft`.
  3. Rollup includes `archived_count` separately.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W1 opportunity schema (source_owner_id + assignee_id)", strict=False)
@pytest.mark.asyncio
async def test_source_owner_and_local_assignee_are_separate_columns(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 rollup engine")
@pytest.mark.asyncio
async def test_headline_picks_worst_open_by_d1_order(session):
    """
    Given: packages in {`changes_requested`, `approved`, `draft`}.
    Then:  rollup.headline == "changes_requested".
           Then remove the changes_requested one → rollup.headline
           becomes "approved". Then remove approved → "draft".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 archive counting")
@pytest.mark.asyncio
async def test_archived_count_is_separate(session):
    raise AssertionError("skeleton")
