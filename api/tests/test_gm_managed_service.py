from datetime import date
from decimal import Decimal

from app.gm.policy import check_floors
from app.gm.templates.managed_service import ManagedServiceInputs, ManagedServiceTemplate
from app.gm.types import CostLine, ResourceLine


def _res(location, hours, cost):
    return ResourceLine(
        role="Ops",
        seniority="Mid",
        location=location,
        allocation_pct=Decimal("1"),
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        hours_billable=Decimal(str(hours)),
        hourly_bill_rate=Decimal("0"),
        hourly_cost=cost if cost is None else Decimal(str(cost)),
    )


class TestManagedService:
    def test_meets_policy(self) -> None:
        # 12 months * $10k = $120k. Cost 120k * 0.65 = 78k → 35%.
        inp = ManagedServiceInputs(
            monthly_fee_us=Decimal("10000"),
            monthly_fee_india=Decimal("0"),
            term_months=Decimal("12"),
            resources=[_res("US", 1200, 65)],  # 1200 * 65 = 78000
        )
        result = ManagedServiceTemplate.compute(inp)
        assert result.revenue_us == Decimal("120000")
        assert result.cost_us == Decimal("78000")
        assert result.gm_us == Decimal("0.35")
        assert check_floors(result)["requires_ceo"] is False

    def test_below_floor(self) -> None:
        inp = ManagedServiceInputs(
            monthly_fee_us=Decimal("8000"),
            monthly_fee_india=Decimal("0"),
            term_months=Decimal("12"),
            resources=[_res("US", 1200, 65)],  # cost 78k, rev 96k → 18.75%
        )
        result = ManagedServiceTemplate.compute(inp)
        out = check_floors(result)
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_missing_cost(self) -> None:
        inp = ManagedServiceInputs(
            monthly_fee_us=Decimal("10000"),
            monthly_fee_india=Decimal("0"),
            term_months=Decimal("12"),
            resources=[_res("US", 1200, None)],
        )
        result = ManagedServiceTemplate.compute(inp)
        assert result.complete is False
        assert "resources[0].hourly_cost" in result.missing

    def test_mixed_geography(self) -> None:
        inp = ManagedServiceInputs(
            monthly_fee_us=Decimal("10000"),  # 120k → 35% (pass)
            monthly_fee_india=Decimal("5000"),  # 60k → 40% (fail)
            term_months=Decimal("12"),
            resources=[
                _res("US", 1200, 65),  # 78k
                _res("India", 600, 60),  # 36k
            ],
        )
        result = ManagedServiceTemplate.compute(inp)
        out = check_floors(result)
        assert out["us_pass"] is True
        assert out["india_pass"] is False
        assert out["failing"] == ["India"]
        assert result.gm_blended is not None

    def test_zero_term_is_incomplete(self) -> None:
        inp = ManagedServiceInputs(
            monthly_fee_us=Decimal("10000"),
            monthly_fee_india=Decimal("0"),
            term_months=Decimal("0"),
            resources=[_res("US", 1200, 65)],
        )
        result = ManagedServiceTemplate.compute(inp)
        assert result.complete is False
        assert "term_months" in result.missing

    def test_tools_cost_included(self) -> None:
        inp = ManagedServiceInputs(
            monthly_fee_us=Decimal("10000"),
            monthly_fee_india=Decimal("0"),
            term_months=Decimal("12"),
            resources=[_res("US", 1200, 60)],  # 72k
            costs=[CostLine(category="tools", amount=Decimal("6000"), location="US")],
        )
        result = ManagedServiceTemplate.compute(inp)
        assert result.cost_us == Decimal("78000")
        assert result.gm_us == Decimal("0.35")
