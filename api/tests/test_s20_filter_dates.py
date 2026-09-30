"""T06 · date filter behavior (S20 · W5).

Per review + contract §4:
- Timezone `America/Los_Angeles` for datetime bounds.
- Date-only fields NOT shifted to previous day.
- Missing dates surfaced separately.
- Presets last 7/30/90 and next 7/30/90; this_month/this_quarter; custom.

**Skeleton — asserts against `PipelineFilters.date_field / date_preset`.**

Test cases:
  1. Preset `last90` includes rows created >= today-90d (LA midnight).
  2. Preset `next30` for close_date includes rows with close_date in the
     next 30 days.
  3. Custom range with a date-only field (close_date) does NOT shift
     inclusive boundaries into the prior day due to UTC conversion.
  4. `missing[date_field]` returns rows with the field NULL.
  5. A row exactly on the boundary (created_at == cutoff) is included
     with the documented rule (inclusive lower, exclusive upper).
  6. TZ label is emitted in `meta.filters_echo.timezone` on the
     response (contract §3).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="skeleton", strict=False)
@pytest.mark.asyncio
async def test_last_90_preset_includes_recent_only(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_next_30_preset_covers_close_dates(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_date_only_field_not_shifted_by_tz(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_missing_date_filter(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_boundary_inclusive_lower_exclusive_upper(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_response_echoes_timezone(session):
    raise AssertionError("skeleton")
