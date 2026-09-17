from datetime import date
from decimal import Decimal

from app.gm.policy import check_floors
from app.gm.templates.tm import TMInputs, TMTemplate
from app.gm.types import ResourceLine


def _res(location, hours, bill, cost):
    return ResourceLine(
        role="Eng",
        seniority="Sr",
        location=location,
        allocation_pct=Decimal("1"),
        start=date(2026, 1, 1),
        end=date(2026, 6, 30),
        hours_billable=Decimal(str(hours)),
        hourly_bill_rate=Decimal(str(bill)),
        hourly_cost=cost if cost is None else Decimal(str(cost)),
    )


class TestTM:
    def test_meets_policy(self) -> None:
        inp = TMInputs(resources=[_res("US", 1000, 100, 65)])
        result = TMTemplate.compute(inp)
        assert result.gm_us == Decimal("0.35")
        assert check_floors(result)["requires_ceo"] is False

    def test_below_floor(self) -> None:
        inp = TMInputs(resources=[_res("US", 1000, 90, 65)])
        result = TMTemplate.compute(inp)
        out = check_floors(result)
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_missing_cost(self) -> None:
        inp = TMInputs(resources=[_res("US", 1000, 100, None)])
        result = TMTemplate.compute(inp)
        assert result.complete is False
        assert "resources[0].hourly_cost" in result.missing

    def test_mixed_geography(self) -> None:
        inp = TMInputs(
            resources=[
                _res("US", 1000, 100, 65),  # 35% → pass
                _res("India", 600, 100, 60),  # 40% → fail
            ]
        )
        result = TMTemplate.compute(inp)
        out = check_floors(result)
        assert out["us_pass"] is True
        assert out["india_pass"] is False
        assert out["failing"] == ["India"]
        assert result.gm_blended is not None

    def test_cap_reduces_revenue_only(self) -> None:
        # Forecast revenue $100k US, cap $80k → GM = (80 - 65)/80 = 18.75%.
        inp = TMInputs(
            resources=[_res("US", 1000, 100, 65)],
            revenue_cap=Decimal("80000"),
        )
        result = TMTemplate.compute(inp)
        assert result.revenue_us == Decimal("80000")
        assert result.cost_us == Decimal("65000")
        assert result.gm_us is not None and result.gm_us < Decimal("0.35")
        assert check_floors(result)["failing"] == ["US"]

    def test_cap_above_forecast_is_noop(self) -> None:
        inp = TMInputs(
            resources=[_res("US", 1000, 100, 65)],
            revenue_cap=Decimal("200000"),
        )
        result = TMTemplate.compute(inp)
        assert result.revenue_us == Decimal("100000")
