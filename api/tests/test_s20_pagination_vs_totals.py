"""T35 · pagination vs global totals (S20 · W5).

Per review + A5:
> Put matching attention/SOW states beyond the first page; verify rows,
> counts, chips, groups and export use the full matching set.

Per contract §4:
> Aggregate contract: one permission-aware base query serves rows,
> counts, chips, rollups, exports. Same snapshot + scope BEFORE
> pagination.

L03 originally showed the pipeline page displayed 50 of 106 with no
next-page control; L06 flagged that stage chips summed to 50 (matches
the page size) — evidence that the aggregation was page-scoped, not
global. This test locks in the fix.

**Skeleton — the query service now uses `func.count().over()` for
total; assert it holds with rows spread across pages.**

Test cases:
  1. Seed 130 open deals with attention=`stalled` on rows 51-100.
     Page 1 (size 50) returns 50 rows and total == 130.
  2. Filter attention=stalled — total == 50, no rows on page 1
     (all stalled deals are on page 2 of the underlying seed).
  3. Stage chips for the filtered set sum to 50 (matches total, not
     page).
  4. Export endpoint returns all 50 stalled rows even when the caller
     is on page 1 of the paginated list.
  5. Query plan: rows-scanned is proportional to the filter's
     selectivity, not the whole opportunity table (A5 evidence).
     Latency budget: p95 < 200ms.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="skeleton; requires seed of 130 rows and existing query service", strict=False)
@pytest.mark.asyncio
async def test_page_1_total_is_global_not_paged(session):
    """
    Given: 130 seeded open opportunities.
    When:  list_opportunities(page=1, page_size=50).
    Then:  page.items has 50 rows; page.total == 130.
           The count column is a window function BEFORE LIMIT.
    """
    raise AssertionError("skeleton: implement seed + call")


@pytest.mark.xfail(reason="skeleton; requires stage chip aggregation from W1")
@pytest.mark.asyncio
async def test_stage_chips_reconcile_to_filtered_total_not_page(session):
    """
    Given: 130 open deals; filter stage=Proposal-17 has 40 matches
    spread across pages 1-3.
    When:  we call summary() with the same filter.
    Then:  sum(stage_chip_counts) == 40 (the total for the filter),
           NOT 50 (page-scoped) and not 130 (unfiltered).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; requires export endpoint")
@pytest.mark.asyncio
async def test_export_returns_full_filtered_set(session):
    """
    Given: filter matches 60 rows across two pages.
    When:  we hit /api/pipeline/export.csv with the same filter.
    Then:  the CSV has 60 body rows, regardless of the page the
           UI happened to be on.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="A5 query-plan evidence; postgres-only via DEALGATE_POSTGRES_URL")
@pytest.mark.asyncio
async def test_query_plan_scans_proportional_to_selectivity(session):
    """
    Given: 130 opportunities on a Postgres test DB (skip on SQLite).
    When:  we `EXPLAIN ANALYZE` list_opportunities with a selective
    filter (owner=X → matches 5 rows).
    Then:  the plan reports Rows Scanned in the same order of
           magnitude as the match count (5), NOT the full table (130).
           Use covering indexes: assert plan mentions `Index Scan`
           or `Bitmap Index Scan`, not `Seq Scan` on `opportunity`.
    Latency budget: p95 total execution < 200ms on 130 rows.
    """
    import os
    if not os.environ.get("DEALGATE_POSTGRES_URL"):
        pytest.skip("Postgres-only: set DEALGATE_POSTGRES_URL")
    raise AssertionError("skeleton: implement EXPLAIN ANALYZE assertion")
