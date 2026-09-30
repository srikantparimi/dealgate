"""T02 · stage buckets reconcile to filtered unique deals (S20 · W5).

Per review:
> At one snapshot, stage buckets reconcile to filtered unique deals;
> company and deal counts remain separate. Investigate the visible 50 vs
> 106 discrepancy.

Contract §4 (aggregate contract) requires one permission-aware base query
to serve rows, counts, chips, rollups and exports; the same snapshot +
scope is applied before pagination. Stage totals must reconcile to the
matching deal total (including an explicit unknown-stage bucket if
needed). D9 says stage aggregation is by `(pipeline_id, stage_id)`,
labels for display only; zero-count stages must render.

**Skeleton, xfail until W1 (aggregation) + W2 (chip render) land.**

When W1 exposes `summary()` that returns per-`(pipeline_id, stage_id)`
buckets and W2 wires the chip renderer to consume them, this test
un-xfails and:

  1. Seeds N deals across three pipelines and six stages, some closed,
     some without a stage id (→ unknown-stage bucket).
  2. Calls `summary()`; asserts sum(bucket counts) == total open deals.
  3. Asserts client counts stay separate — a deal counts once in the
     global total even if it has two company associations (contract §4).
  4. Asserts every configured stage is present in the response even
     with zero deals (zero-count chips must render).
  5. Asserts the unknown-stage bucket is explicit, not merged into a
     default stage.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason="depends on W1 aggregation by (pipeline_id, stage_id) — D9",
    strict=False,
)
@pytest.mark.asyncio
async def test_stage_buckets_reconcile_to_total_open(session):
    """
    Given: 106 open deals across three pipelines, some without a stage id.
    When:  we call the shared summary().
    Then:  sum(open_by_stage) + unknown_stage_bucket == total_open.
           No stage bucket ever exceeds the total.
           Zero-count stages are present (chips render zeros — L06 fix).
    """
    # TODO(W5, once W1 lands): seed via helpers mirrored from
    # test_hubspot_pipeline_query_service.py, call summary(), assert.
    raise AssertionError("skeleton: implement once W1's aggregation lands")


@pytest.mark.xfail(reason="depends on W1 aggregation by (pipeline_id, stage_id) — D9")
@pytest.mark.asyncio
async def test_client_count_never_leaks_into_deal_count(session):
    """
    Given: two deals for the same client, one for a different client.
    When:  summary() is called.
    Then:  total_open_deals == 3.
           total_open_clients == 2.
           These are two separate numbers; a client count is never a
           deal count (contract §4).
    """
    raise AssertionError("skeleton: implement once W1's summary lands")


@pytest.mark.xfail(reason="depends on W1 aggregation by (pipeline_id, stage_id) — D9")
@pytest.mark.asyncio
async def test_unknown_stage_bucket_is_explicit(session):
    """
    Given: a deal whose stage_id doesn't resolve in the HubspotStage mirror.
    When:  summary() is called.
    Then:  the response contains an `unknown_stage` bucket with count == 1;
           no other bucket claims that deal.
    """
    raise AssertionError("skeleton: implement once W1's mirror lands")
