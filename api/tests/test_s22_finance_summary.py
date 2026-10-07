"""S22 round 3 · the Confirm page's GM summary gets real numbers.

Owner finding: Contract price / Labor cost / Gross margin all showed
"Unavailable" even for an assessed commercial result, because the
commercial path returned an empty finance_summary. The summary is pure
Decimal math over the assessed outcome; an unassessed outcome stays {}.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from app.gm.commercial import (
    FeeAllocation,
    FixedFee,
    PeriodCost,
    PricingComponent,
    calculate_component,
)
from app.gm.finance_summary import commercial_finance_summary

MONTHS = [date(2026, 11 + i, 1) if 11 + i <= 12 else date(2027, i - 1, 1) for i in range(6)]


def component(**changes):
    values = dict(
        component_id="build", version="1", source_id="sow-x", source_version="2",
        workstream_id="delivery-x", profile="fixed_assignment", profile_version="1",
        policy_version="gm-1", source_evidence=("sow-x:page-2",),
        service_start=date(2026, 11, 1), service_end=date(2027, 4, 30),
        timezone="America/New_York", currency="USD", billing_cadence="quarterly",
        cost_basis="Approved monthly delivery cost", costs_confirmed=True,
        costs=tuple(PeriodCost(f"team-{i}", month, "India", D("35000"))
                    for i, month in enumerate(MONTHS)),
        pricing=FixedFee(D("420000"), tuple(FeeAllocation(m, "India", D("1"))
                                            for m in MONTHS), "even service months", D("0.01")),
    )
    return PricingComponent(**(values | changes))


def test_assessed_outcome_yields_exact_summary_rows():
    schedule = calculate_component(component())
    outcome = schedule.assess()
    summary = commercial_finance_summary(outcome, schedule.component)
    assert summary["revenue"] == "420000.00"
    assert summary["total_delivery_cost"] == "210000.00"
    assert summary["gross_profit"] == "210000.00"
    # All six period costs are explicit "other delivery expenses" here,
    # so labor is zero and direct carries the full cost.
    assert summary["direct_cost"] == "210000.00"
    assert summary["labor_cost"] == "0.00"
    assert summary["total_cost_pct"] == "0.5000"


def test_incomplete_staffing_preserves_known_fixed_fee_revenue_only():
    incomplete = calculate_component(component(costs_confirmed=False))
    summary = commercial_finance_summary(incomplete.assess(), incomplete.component)
    assert summary == {
        "revenue": "420000.00",
        "labor_cost": None,
        "direct_cost": None,
        "total_delivery_cost": None,
        "gross_profit": None,
        "labor_pct": None,
        "direct_pct": None,
        "total_cost_pct": None,
        "pass_through": "0",
    }
