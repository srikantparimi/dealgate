from decimal import Decimal

from app.gm.policy import INDIA_FLOOR, US_FLOOR, check_floors, min_price_for
from app.gm.types import TemplateResult


def _result(**kw) -> TemplateResult:
    return TemplateResult(**kw)


class TestCheckFloors:
    def test_us_only_meets_policy(self) -> None:
        r = _result(revenue_us=Decimal("100000"), cost_us=Decimal("65000"), gm_us=US_FLOOR)
        out = check_floors(r)
        assert out == {
            "us_pass": True,
            "india_pass": True,
            "requires_ceo": False,
            "failing": [],
        }

    def test_india_only_meets_policy(self) -> None:
        r = _result(
            revenue_india=Decimal("60000"),
            cost_india=Decimal("30000"),
            gm_india=INDIA_FLOOR,
        )
        assert check_floors(r)["requires_ceo"] is False

    def test_us_below_floor_routes_to_ceo(self) -> None:
        r = _result(
            revenue_us=Decimal("90000"),
            cost_us=Decimal("65000"),
            gm_us=Decimal("0.2778"),
        )
        out = check_floors(r)
        assert out["us_pass"] is False
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_india_below_floor_routes_to_ceo(self) -> None:
        r = _result(
            revenue_india=Decimal("55000"),
            cost_india=Decimal("30000"),
            gm_india=Decimal("0.4545"),
        )
        out = check_floors(r)
        assert out["india_pass"] is False
        assert "India" in out["failing"]
        assert out["requires_ceo"] is True

    def test_mixed_us_fails_india_passes(self) -> None:
        r = _result(
            revenue_us=Decimal("90000"),
            cost_us=Decimal("65000"),
            gm_us=Decimal("0.2778"),
            revenue_india=Decimal("60000"),
            cost_india=Decimal("30000"),
            gm_india=INDIA_FLOOR,
        )
        out = check_floors(r)
        assert out["us_pass"] is False
        assert out["india_pass"] is True
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_incomplete_forces_ceo(self) -> None:
        r = _result(
            revenue_us=Decimal("100000"),
            cost_us=Decimal("65000"),
            gm_us=US_FLOOR,
            complete=False,
            missing=["resources[0].hourly_cost"],
        )
        assert check_floors(r)["requires_ceo"] is True

    def test_min_price_for_reexport(self) -> None:
        assert min_price_for(Decimal("65000"), US_FLOOR) == Decimal("100000")
        assert min_price_for(Decimal("30000"), INDIA_FLOOR) == Decimal("60000")
