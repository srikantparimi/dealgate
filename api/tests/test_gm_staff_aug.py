from datetime import date
from decimal import Decimal

from app.gm import compute
from app.gm.policy import check_floors
from app.gm.templates.staff_aug import StaffAugInputs, StaffAugTemplate
from app.gm.types import CostLine, EngagementType, ResourceLine


def _us_pass_inputs() -> StaffAugInputs:
    # 1000 hours * $100 = $100,000 revenue, cost 1000 * $65 = $65,000 → 35%.
    r = ResourceLine(
        role="Engineer",
        seniority="Senior",
        location="US",
        allocation_pct=Decimal("1"),
        start=date(2026, 1, 1),
        end=date(2026, 6, 30),
        hours_billable=Decimal("1000"),
        hourly_bill_rate=Decimal("100"),
        hourly_cost=Decimal("65"),
    )
    return StaffAugInputs(resources=[r], pbu_hours=[Decimal("0")])


class TestStaffAug:
    def test_meets_policy(self) -> None:
        result = StaffAugTemplate.compute(_us_pass_inputs())
        assert result.complete is True
        assert result.revenue_us == Decimal("100000")
        assert result.cost_us == Decimal("65000")
        assert result.gm_us == Decimal("0.35")
        out = check_floors(result)
        assert out == {
            "us_pass": True,
            "india_pass": True,
            "requires_ceo": False,
            "failing": [],
        }

    def test_below_floor_names_us(self) -> None:
        inp = _us_pass_inputs()
        # Cut price by billing at $90 instead of $100 → GM = (90-65)/90 ≈ 27.78%.
        r = inp.resources[0]
        cut = ResourceLine(
            role=r.role,
            seniority=r.seniority,
            location=r.location,
            allocation_pct=r.allocation_pct,
            start=r.start,
            end=r.end,
            hours_billable=r.hours_billable,
            hourly_bill_rate=Decimal("90"),
            hourly_cost=r.hourly_cost,
        )
        result = StaffAugTemplate.compute(
            StaffAugInputs(resources=[cut], pbu_hours=[Decimal("0")])
        )
        out = check_floors(result)
        assert out["us_pass"] is False
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_missing_cost_marks_incomplete(self) -> None:
        r = ResourceLine(
            role="Engineer",
            seniority="Senior",
            location="US",
            allocation_pct=Decimal("1"),
            start=date(2026, 1, 1),
            end=date(2026, 6, 30),
            hours_billable=Decimal("1000"),
            hourly_bill_rate=Decimal("100"),
            hourly_cost=None,  # missing
        )
        result = StaffAugTemplate.compute(
            StaffAugInputs(resources=[r], pbu_hours=[Decimal("0")])
        )
        assert result.complete is False
        assert "resources[0].hourly_cost" in result.missing
        # Cost still zero on the US side because we refuse to guess.
        assert result.cost_us == Decimal("0")
        assert check_floors(result)["requires_ceo"] is True

    def test_mixed_geography_us_fails_india_passes(self) -> None:
        us = ResourceLine(
            role="Eng",
            seniority="Sr",
            location="US",
            allocation_pct=Decimal("1"),
            start=date(2026, 1, 1),
            end=date(2026, 6, 30),
            hours_billable=Decimal("1000"),
            hourly_bill_rate=Decimal("90"),  # under floor
            hourly_cost=Decimal("65"),
        )
        india = ResourceLine(
            role="Eng",
            seniority="Sr",
            location="India",
            allocation_pct=Decimal("1"),
            start=date(2026, 1, 1),
            end=date(2026, 6, 30),
            hours_billable=Decimal("600"),
            hourly_bill_rate=Decimal("100"),
            hourly_cost=Decimal("50"),  # 50% GM
        )
        result = StaffAugTemplate.compute(
            StaffAugInputs(resources=[us, india], pbu_hours=[Decimal("0"), Decimal("0")])
        )
        out = check_floors(result)
        assert out["us_pass"] is False
        assert out["india_pass"] is True
        assert out["failing"] == ["US"]
        # Blended GM must not hide the failing component.
        assert result.gm_blended is not None
        assert result.gm_us is not None and result.gm_us < Decimal("0.35")

    def test_pbu_hours_inflate_cost_only(self) -> None:
        r = ResourceLine(
            role="Eng",
            seniority="Sr",
            location="US",
            allocation_pct=Decimal("1"),
            start=date(2026, 1, 1),
            end=date(2026, 6, 30),
            hours_billable=Decimal("1000"),
            hourly_bill_rate=Decimal("100"),
            hourly_cost=Decimal("65"),
        )
        # 100 PBU hours * $65 = $6500 extra cost. Revenue unchanged.
        result = StaffAugTemplate.compute(
            StaffAugInputs(resources=[r], pbu_hours=[Decimal("100")])
        )
        assert result.revenue_us == Decimal("100000")
        assert result.cost_us == Decimal("71500")

    def test_dispatcher_routes(self) -> None:
        # Sanity that the top-level ``compute`` finds the template.
        assert compute(EngagementType.STAFF_AUG, _us_pass_inputs()).complete is True

    def test_extra_costs_included(self) -> None:
        inp = _us_pass_inputs()
        travel = CostLine(category="travel", amount=Decimal("5000"), location="US")
        inp = StaffAugInputs(
            resources=inp.resources,
            pbu_hours=inp.pbu_hours,
            costs=[travel],
        )
        result = StaffAugTemplate.compute(inp)
        assert result.cost_us == Decimal("70000")

    def test_required_inputs_lists_pbu_and_replacement(self) -> None:
        req = StaffAugTemplate.required_inputs()
        assert "pbu_hours" in req
        assert "replacement_obligation" in req
