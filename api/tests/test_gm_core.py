from decimal import Decimal

import pytest

from app.gm import gross_margin, min_price

US_FLOOR = Decimal("0.35")
INDIA_FLOOR = Decimal("0.50")


class TestGrossMargin:
    def test_at_policy_us(self) -> None:
        assert gross_margin(Decimal("100000"), Decimal("65000")) == Decimal("0.35")

    def test_at_policy_india(self) -> None:
        assert gross_margin(Decimal("60000"), Decimal("30000")) == Decimal("0.50")

    def test_discounted_us_fails_floor(self) -> None:
        gm = gross_margin(Decimal("90000"), Decimal("65000"))
        assert gm < US_FLOOR
        assert round(gm, 4) == Decimal("0.2778")

    def test_discounted_india_fails_floor(self) -> None:
        gm = gross_margin(Decimal("55000"), Decimal("30000"))
        assert gm < INDIA_FLOOR
        assert round(gm, 4) == Decimal("0.4545")

    def test_zero_revenue_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            gross_margin(Decimal("0"), Decimal("1"))


class TestMinPrice:
    def test_us_min_price_65k_cost(self) -> None:
        assert min_price(Decimal("65000"), US_FLOOR) == Decimal("100000")

    def test_india_min_price_30k_cost(self) -> None:
        assert min_price(Decimal("30000"), INDIA_FLOOR) == Decimal("60000")

    def test_floor_of_one_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            min_price(Decimal("100"), Decimal("1"))


class TestWorkedExampleFromSection7:
    """Discounted case: US GM 27.78% and India GM 45.45% both fail floor.
    Route to CEO. The brief shows two numbers:
      - price must rise by $15,000 to meet policy,
      - gross-profit shortfall at proposed price is $9,000 ($6,500 US + $2,500 India).
    """

    def test_us_component_gm(self) -> None:
        assert gross_margin(Decimal("90000"), Decimal("65000")) < US_FLOOR

    def test_india_component_gm(self) -> None:
        assert gross_margin(Decimal("55000"), Decimal("30000")) < INDIA_FLOOR

    def test_us_price_uplift_to_reach_policy(self) -> None:
        required = min_price(Decimal("65000"), US_FLOOR)
        assert required - Decimal("90000") == Decimal("10000")

    def test_india_price_uplift_to_reach_policy(self) -> None:
        required = min_price(Decimal("30000"), INDIA_FLOOR)
        assert required - Decimal("55000") == Decimal("5000")

    def test_total_price_uplift_is_15000(self) -> None:
        us_uplift = min_price(Decimal("65000"), US_FLOOR) - Decimal("90000")
        india_uplift = min_price(Decimal("30000"), INDIA_FLOOR) - Decimal("55000")
        assert us_uplift + india_uplift == Decimal("15000")

    def test_us_gp_shortfall_is_6500(self) -> None:
        proposed_gp = Decimal("90000") - Decimal("65000")
        policy_gp = Decimal("90000") * US_FLOOR
        assert policy_gp - proposed_gp == Decimal("6500")

    def test_india_gp_shortfall_is_2500(self) -> None:
        proposed_gp = Decimal("55000") - Decimal("30000")
        policy_gp = Decimal("55000") * INDIA_FLOOR
        assert policy_gp - proposed_gp == Decimal("2500")
