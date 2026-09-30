"""T26 · report totals + drill-down reconciliation (S20 · W5).

Per review:
> Filter by BU/owner/period; drill into rows and export. Totals
> reconcile, currencies/bases are declared, unknown-value counts are
> visible.

**Skeleton, xfail until W4 lands the reporting endpoints.**

Test cases:
  1. Filter Portfolio by BU=Retail; sum of the row values == the
     summary total shown at the top of the report.
  2. Drill-down from a report row lands on `/pipeline?<same filter>`;
     row counts match.
  3. Currency: mixed-currency totals declare `reporting_currency` +
     `fx_source` + `fx_date` per response envelope; NOT a silent
     conversion.
  4. Unknown-value bucket count is visible on every report; NEVER
     merged into a default bucket.
  5. Export CSV row count == list API row count for the same filter.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W4 report endpoints", strict=False)
@pytest.mark.asyncio
async def test_bu_filter_totals_reconcile(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4")
@pytest.mark.asyncio
async def test_drill_down_lands_on_matching_pipeline_filter(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 currency envelope")
@pytest.mark.asyncio
async def test_mixed_currency_declares_reporting_currency_and_fx(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 unknown-bucket surface")
@pytest.mark.asyncio
async def test_unknown_bucket_visible_in_every_report(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 export endpoint")
@pytest.mark.asyncio
async def test_export_row_count_matches_list(session):
    raise AssertionError("skeleton")
