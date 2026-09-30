"""T05 · filter combinations OR/AND (S20 · W5).

Per review + contract §4:
> Combine owner + BU + stage + created last 30 days; verify OR/AND
> rules against independently expected records, not the same UI query.
> OR within a field, AND between different fields.

**Skeleton — the `PipelineFilters` shape already exists on
`api/app/services/hubspot_pipeline.py`; assertions expand it to the S20
filter contract (search, owner[], stage[], bu[], pipeline, open_closed,
attention[], sow_state[], group, date_field/from/to/preset, missing[]).**

Test cases:
  1. owner=[A,B] → rows owned by A OR B (OR within a field).
  2. owner=[A] AND stage=[X] → rows owned by A AND in stage X.
  3. owner=[A] AND bu=[Retail] AND created>=today-30 → the intersection.
  4. missing=[bu] → only rows whose business_unit is NULL.
  5. Independent record set: seed 10 rows with expected filter outcomes;
     compute the expected result set in Python at seed time (NOT by
     re-running the filter code under test); assert list matches.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W2 filter bar and W1 BU mirror", strict=False)
@pytest.mark.asyncio
async def test_or_within_owner_field(session):
    """
    Given: rows owned by A, B, C.
    When:  filter owner=[A, B].
    Then:  rows returned == {owned by A} ∪ {owned by B}; C's row absent.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W2 filter bar")
@pytest.mark.asyncio
async def test_and_across_fields(session):
    """
    Given: rows in {(A, X), (A, Y), (B, X)}.
    When:  filter owner=[A] AND stage=[X].
    Then:  rows returned == {(A, X)}.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 BU mirror (D10) + W2 filter bar")
@pytest.mark.asyncio
async def test_owner_and_bu_and_date_intersection(session):
    """
    Given: 10 seeded rows across owners × BU × created_at.
    When:  filter owner=[A] AND bu=[Retail] AND date_field=created,
           date_from=today-30, date_to=today.
    Then:  the returned set equals the Python-computed expected set.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W2 missing-value filter")
@pytest.mark.asyncio
async def test_missing_value_filter(session):
    """
    Given: rows with business_unit ∈ {'Retail', 'Health', None}.
    When:  filter missing=[bu].
    Then:  only the NULL row returns.
    """
    raise AssertionError("skeleton")
