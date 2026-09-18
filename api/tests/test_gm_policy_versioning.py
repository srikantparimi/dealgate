"""S2 E4 — baseline preservation: gm.policy library still returns identical
results as before when callers use default floors (no policy_version).

Agent B ratified the current check_floors behavior; the versioning helpers
must be non-destructive. Any change here needs to be explicit and reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.gm.policy import (
    INDIA_FLOOR,
    US_FLOOR,
    check_floors,
    india_floor,
    us_floor,
)
from app.gm.types import TemplateResult


def _result(**kw) -> TemplateResult:
    return TemplateResult(**kw)


@dataclass(frozen=True)
class _FakePolicy:
    us_floor: Decimal
    india_floor: Decimal


def test_default_helpers_return_blueprint_constants():
    """None -> defaults (0.35 / 0.50), keeping the historical library API."""

    assert us_floor(None) == US_FLOOR
    assert india_floor(None) == INDIA_FLOOR
    assert us_floor() == Decimal("0.35")
    assert india_floor() == Decimal("0.50")


def test_check_floors_defaults_match_agent_b_baseline():
    """Same inputs Agent B's test suite uses; identical dict returned."""

    us_ok = _result(revenue_us=Decimal("100000"), cost_us=Decimal("65000"), gm_us=US_FLOOR)
    assert check_floors(us_ok) == {
        "us_pass": True,
        "india_pass": True,
        "requires_ceo": False,
        "failing": [],
    }

    india_low = _result(
        revenue_india=Decimal("55000"),
        cost_india=Decimal("30000"),
        gm_india=Decimal("0.4545"),
    )
    baseline = check_floors(india_low)
    assert baseline["india_pass"] is False
    assert baseline["failing"] == ["India"]
    assert baseline["requires_ceo"] is True

    us_below = _result(
        revenue_us=Decimal("90000"),
        cost_us=Decimal("65000"),
        gm_us=Decimal("0.2778"),
    )
    b2 = check_floors(us_below)
    assert b2["us_pass"] is False
    assert b2["failing"] == ["US"]


def test_check_floors_with_version_floors_overrides_default():
    """A version with higher floors flips a previously-passing sheet to fail."""

    version = _FakePolicy(us_floor=Decimal("0.40"), india_floor=Decimal("0.55"))
    # Sheet that meets the *old* 0.35 US floor but not 0.40.
    r = _result(revenue_us=Decimal("100000"), cost_us=Decimal("65000"), gm_us=Decimal("0.35"))

    default = check_floors(r)
    assert default["us_pass"] is True

    stricter = check_floors(
        r,
        us_floor_value=us_floor(version),
        india_floor_value=india_floor(version),
    )
    assert stricter["us_pass"] is False
    assert stricter["requires_ceo"] is True


def test_check_floors_with_defaults_matches_no_kwarg_call():
    """Passing the module constants explicitly = calling with defaults."""

    r = _result(
        revenue_us=Decimal("100000"),
        cost_us=Decimal("65000"),
        gm_us=Decimal("0.35"),
        revenue_india=Decimal("60000"),
        cost_india=Decimal("30000"),
        gm_india=Decimal("0.50"),
    )
    assert check_floors(r) == check_floors(
        r, us_floor_value=US_FLOOR, india_floor_value=INDIA_FLOOR
    )
