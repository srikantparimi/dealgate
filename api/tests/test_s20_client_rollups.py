"""T08 · client rollups (S20 · W5).

Per review:
> Test client with mixed open/closed deals, zero deals, multiple owners
> and multiple associated companies. Show 74 Sky consistently.

Per contract §4:
> In Clients view, deal filters select clients with matching deals.
> Label matching versus total opportunities, and distinguish company
> owner filtering from deal owner filtering. Count each deal once in
> global totals even if it has several company associations. A client
> count is never a deal count.

**Skeleton — the query service already computes several rollups; this
test locks in the multi-scenario cases the review named.**

Test cases:
  1. Client with 3 open + 2 closed deals: `open_count=3`,
     `total_count=5`, breakdown by state present.
  2. Client with zero deals: rendered as a row with empty state
     (not filtered out).
  3. Client with deals owned by 3 different people:
     `unique_owner_count=3`; distinct owner labels shown.
  4. 74 Sky (Closed Lost): `open_count=0`; label shown as
     `Closed Lost` (readable), NOT numeric.
  5. Multi-associated deal: one deal linked to two companies is
     counted ONCE in global total (contract §4).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="skeleton; extend existing list_clients()", strict=False)
@pytest.mark.asyncio
async def test_mixed_open_closed_counts(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_zero_deal_client_renders_row(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_multiple_deal_owners_visible(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; L07 regression for 74 Sky")
@pytest.mark.asyncio
async def test_closed_lost_client_reads_open_0_with_label(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_multi_association_deal_counted_once_in_global(session):
    raise AssertionError("skeleton")
