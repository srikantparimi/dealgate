"""A fixed-fee engagement earns the fee, not bill-rate x hours (S10-07).

Reported from the confirm screen: resources, hours and rates had been entered
and saved, and the gross margin still read "Unavailable" with revenue 0.00.

Two causes, both here:

1. Save-time revenue was always `hours x bill_rate x allocation`. That is
   right for T&M and staff aug and wrong for a fixed fee, where the revenue
   is the agreed price whatever the hours turn out to be. On a fixed-price
   SOW nobody bills by the hour, so the bill-rate column is often left blank
   — and the revenue snapshot came out as zero.
2. The fixed-price template needs `revenue_us` and `revenue_india`
   explicitly, and nothing derived that split, so revenue never reached the
   engine at all.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.delivery_model import (
    ResourceLinePayload,
    allocate_fixed_fee_revenue,
)

FEE = Decimal("50000.00")


def _line(location: str, hours: str, cost: str | None, bill: str = "0") -> ResourceLinePayload:
    return ResourceLinePayload(
        role="Consultant",
        seniority="Senior",
        location=location,
        person_name=None,
        allocation_pct=Decimal("1"),
        start_date=date(2026, 8, 25),
        end_date=date(2026, 9, 30),
        hours_billable=Decimal(hours),
        hourly_bill_rate=Decimal(bill),
        hourly_cost=Decimal(cost) if cost is not None else None,
        validated_by=None,
        phase_name=None,
    )


def test_fee_is_split_by_cost_weighted_effort():
    """sow-first §5: cost-weighted effort is the default basis."""

    us = _line("US", "100", "120")       # 12,000 of cost
    india = _line("India", "200", "30")  # 6,000 of cost
    rev_us, rev_india, notes = allocate_fixed_fee_revenue([us, india], FEE)

    # 2:1 on cost, so 2:1 on revenue.
    assert rev_us == Decimal("33333.33")
    assert rev_india == Decimal("16666.67")
    assert notes == []


def test_the_split_always_sums_to_the_fee_exactly():
    """The fixed-price template rejects an allocation that does not sum to
    the price, so losing a cent to rounding would fail the whole sheet."""

    lines = [_line("US", "333", "77"), _line("India", "667", "31")]
    for fee in ("50000.00", "1.00", "99999.99", "12345.67"):
        rev_us, rev_india, _ = allocate_fixed_fee_revenue(lines, Decimal(fee))
        assert rev_us + rev_india == Decimal(fee), fee


def test_missing_cost_rates_fall_back_to_hours_and_say_so():
    """No published cost band means cost-weighting is impossible. Hours are a
    proxy, not the policy — sow-first §7 requires the fallback to be loud."""

    lines = [_line("US", "100", None), _line("India", "200", None)]
    rev_us, rev_india, notes = allocate_fixed_fee_revenue(lines, FEE)

    assert rev_us == Decimal("16666.67")   # 1:2 on hours
    assert rev_india == Decimal("33333.33")
    assert any("not cost" in n for n in notes)


def test_bill_rates_are_irrelevant_to_a_fixed_fee():
    """The whole point of the fix: revenue does not move with the bill rate.

    This is what made the reported bug invisible — a reviewer filling in
    hours and cost on a fixed-fee SOW has no reason to enter a bill rate, and
    the old code turned that into revenue of zero.
    """

    zero_rate = [_line("US", "100", "120", bill="0")]
    high_rate = [_line("US", "100", "120", bill="400")]
    assert allocate_fixed_fee_revenue(zero_rate, FEE) == allocate_fixed_fee_revenue(
        high_rate, FEE
    )


def test_single_geography_takes_the_whole_fee():
    rev_us, rev_india, _ = allocate_fixed_fee_revenue([_line("US", "480", "150")], FEE)
    assert rev_us == FEE
    assert rev_india == Decimal("0")


def test_no_lines_or_no_hours_is_reported_not_guessed():
    _us, _india, notes = allocate_fixed_fee_revenue([], FEE)
    assert notes

    _us2, _india2, notes2 = allocate_fixed_fee_revenue(
        [_line("US", "0", "120")], FEE
    )
    assert notes2
