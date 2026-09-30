"""T17 · GM staffing thresholds (S20 · W5).

Per review:
> US exactly 35% and India exactly 50% pass when complete. India 49.999%
> fails despite display rounding; blended GM cannot hide a failed
> component.

CLAUDE.md rule 2: money uses `Decimal` and `NUMERIC` columns; all margin
math lives in `api/app/gm`. LLMs never compute or alter a number.

**Skeleton — the gm engine already ships (`app.gm`); this test just
codifies the two-geography threshold expectations for S20 evidence.**

Test cases (skeleton):
  1. US-only role at exactly 35% → pass.
  2. India-only role at exactly 50% → pass.
  3. India role at 49.999% → fail even when blended margin ≥ 42.5%
     across the whole package.
  4. Two-role package (US 40%, India 45%): blended average >= 42.5%
     but India component < 50% → fail; the failure reason must name
     the component, not just the blended number.
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.xfail(reason="skeleton; wire to app.gm.check_thresholds()", strict=False)
def test_us_35_percent_exact_passes():
    """
    Given: single US role with computed margin == Decimal("0.35").
    When:  gm.check_thresholds(package).
    Then:  result.ok is True, result.failed_components == ().
    """
    raise AssertionError("skeleton: wire to gm.check_thresholds")


@pytest.mark.xfail(reason="skeleton; wire to app.gm.check_thresholds()")
def test_india_50_percent_exact_passes():
    """
    Given: single India role with computed margin == Decimal("0.50").
    Then:  result.ok is True.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; wire to app.gm.check_thresholds()")
def test_india_49_point_999_percent_fails():
    """
    Given: single India role with computed margin == Decimal("0.49999").
    Then:  result.ok is False; result.failed_components names "IN" +
           reason "below_floor_by=0.00001".
           Rounding for display MUST NOT round up into a pass — the
           check uses Decimal at full precision.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; wire to app.gm.check_thresholds()")
def test_blended_margin_cannot_hide_failed_india_component():
    """
    Given: package with US role at 40% and India role at 45%; blended
    across allocation weights is 42.5% (above the blended floor).
    Then:  result.ok is False.
           result.failed_components names India.
           A blended pass MUST NOT hide a failed component.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; asserts float never enters the calc")
def test_no_float_in_gm_pipeline():
    """
    Regression guard on CLAUDE.md rule 2. Import each function in
    app.gm.*; introspect its signature + return type; assert Decimal
    everywhere. If a `float` type appears, the check fails.
    """
    raise AssertionError("skeleton: implement introspection")
