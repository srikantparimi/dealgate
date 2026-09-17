from datetime import date
from decimal import Decimal

from app.gm.policy import check_floors
from app.gm.templates.fixed_price import FixedPriceInputs, FixedPriceTemplate
from app.gm.types import CostLine, ResourceLine


def _res(location, hours, cost):
    return ResourceLine(
        role="Eng",
        seniority="Sr",
        location=location,
        allocation_pct=Decimal("1"),
        start=date(2026, 1, 1),
        end=date(2026, 6, 30),
        hours_billable=Decimal(str(hours)),
        hourly_bill_rate=Decimal("0"),  # fixed-price: no hourly revenue
        hourly_cost=cost if cost is None else Decimal(str(cost)),
    )


class TestFixedPrice:
    def test_meets_policy_us_only(self) -> None:
        # $100k US price, $65k cost → 35%.
        inp = FixedPriceInputs(
            total_price=Decimal("100000"),
            revenue_us=Decimal("100000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 1000, 65)],
        )
        result = FixedPriceTemplate.compute(inp)
        assert result.complete is True
        assert result.gm_us == Decimal("0.35")
        assert check_floors(result)["requires_ceo"] is False

    def test_below_floor(self) -> None:
        inp = FixedPriceInputs(
            total_price=Decimal("90000"),
            revenue_us=Decimal("90000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 1000, 65)],
        )
        result = FixedPriceTemplate.compute(inp)
        out = check_floors(result)
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_missing_cost_marks_incomplete(self) -> None:
        inp = FixedPriceInputs(
            total_price=Decimal("100000"),
            revenue_us=Decimal("100000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 1000, None)],
        )
        result = FixedPriceTemplate.compute(inp)
        assert result.complete is False
        assert "resources[0].hourly_cost" in result.missing

    def test_mixed_geography_us_fails_india_passes(self) -> None:
        inp = FixedPriceInputs(
            total_price=Decimal("150000"),
            revenue_us=Decimal("90000"),  # 90k / 65k → 27.78% fails
            revenue_india=Decimal("60000"),  # 60k / 30k → 50% passes
            resources=[
                _res("US", 1000, 65),
                _res("India", 600, 50),
            ],
        )
        result = FixedPriceTemplate.compute(inp)
        out = check_floors(result)
        assert out["us_pass"] is False
        assert out["india_pass"] is True
        assert out["failing"] == ["US"]
        # Blended is informational — must not hide the US failure.
        assert result.gm_blended is not None
        assert result.gm_us is not None and result.gm_us < Decimal("0.35")

    def test_allocation_is_an_input_not_our_concern(self) -> None:
        """Changing US/India revenue allocation reshapes the components; the
        library trusts the caller's split as long as it sums to total price."""
        base = FixedPriceInputs(
            total_price=Decimal("150000"),
            revenue_us=Decimal("100000"),
            revenue_india=Decimal("50000"),
            resources=[_res("US", 1000, 65), _res("India", 600, 50)],
        )
        r1 = FixedPriceTemplate.compute(base)
        # Reallocate — still sums to 150k.
        realloc = FixedPriceInputs(
            total_price=Decimal("150000"),
            revenue_us=Decimal("120000"),
            revenue_india=Decimal("30000"),
            resources=base.resources,
        )
        r2 = FixedPriceTemplate.compute(realloc)
        assert r1.complete is True and r2.complete is True
        assert r1.revenue_us != r2.revenue_us
        # Component GMs shift — this is the caller's responsibility.
        assert r1.gm_us != r2.gm_us

    def test_unallocated_cost_keeps_incomplete(self) -> None:
        inp = FixedPriceInputs(
            total_price=Decimal("100000"),
            revenue_us=Decimal("100000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 1000, 65)],
            unallocated_cost_notes=["subcontractor_tbd"],
        )
        result = FixedPriceTemplate.compute(inp)
        assert result.complete is False
        assert any("subcontractor_tbd" in m for m in result.missing)
        assert check_floors(result)["requires_ceo"] is True

    def test_allocation_sum_mismatch_flagged(self) -> None:
        inp = FixedPriceInputs(
            total_price=Decimal("100000"),
            revenue_us=Decimal("60000"),
            revenue_india=Decimal("30000"),  # sums to 90k, not 100k
            resources=[_res("US", 500, 65)],
        )
        result = FixedPriceTemplate.compute(inp)
        assert result.complete is False
        assert "revenue_allocation" in result.missing

    def test_extra_cost_line_included(self) -> None:
        inp = FixedPriceInputs(
            total_price=Decimal("100000"),
            revenue_us=Decimal("100000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 1000, 60)],
            costs=[CostLine(category="tools", amount=Decimal("5000"), location="US")],
        )
        result = FixedPriceTemplate.compute(inp)
        assert result.cost_us == Decimal("65000")
        assert result.gm_us == Decimal("0.35")
