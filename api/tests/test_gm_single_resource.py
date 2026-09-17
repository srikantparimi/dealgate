from datetime import date
from decimal import Decimal

from app.gm.policy import check_floors
from app.gm.templates.single_resource import SingleResourceInputs, SingleResourceTemplate
from app.gm.types import ResourceLine


def _resource(bill: str, cost, location="US") -> ResourceLine:
    return ResourceLine(
        role="Consultant",
        seniority="Principal",
        location=location,
        allocation_pct=Decimal("1"),
        start=date(2026, 1, 1),
        end=date(2026, 3, 31),
        hours_billable=Decimal("500"),
        hourly_bill_rate=Decimal(bill),
        hourly_cost=cost if cost is None else Decimal(cost),
    )


class TestSingleResource:
    def test_meets_policy_us(self) -> None:
        result = SingleResourceTemplate.compute(SingleResourceInputs(resource=_resource("200", "130")))
        assert result.gm_us == Decimal("0.35")
        assert check_floors(result)["requires_ceo"] is False

    def test_below_floor(self) -> None:
        result = SingleResourceTemplate.compute(SingleResourceInputs(resource=_resource("150", "130")))
        out = check_floors(result)
        assert out["us_pass"] is False
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_missing_cost(self) -> None:
        result = SingleResourceTemplate.compute(SingleResourceInputs(resource=_resource("200", None)))
        assert result.complete is False
        assert "resources[0].hourly_cost" in result.missing
        assert check_floors(result)["requires_ceo"] is True

    def test_mixed_geography_via_two_calls(self) -> None:
        # Single-resource is one location by definition; "mixed" here means
        # a US-priced resource meets policy while an India-priced one under
        # the same rate would fail its floor.
        us_ok = SingleResourceTemplate.compute(SingleResourceInputs(resource=_resource("200", "130", "US")))
        india_fail = SingleResourceTemplate.compute(
            SingleResourceInputs(resource=_resource("100", "70", "India"))
        )
        assert check_floors(us_ok)["requires_ceo"] is False
        assert check_floors(india_fail)["requires_ceo"] is True
        assert check_floors(india_fail)["failing"] == ["India"]

    def test_missing_resource(self) -> None:
        result = SingleResourceTemplate.compute(SingleResourceInputs(resource=None))
        assert result.complete is False
        assert "resource" in result.missing
