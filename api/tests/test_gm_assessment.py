from datetime import date
from decimal import Decimal

from app.gm.policy import check_floors
from app.gm.templates.assessment import AssessmentInputs, AssessmentTemplate
from app.gm.types import ResourceLine


def _res(location, hours, cost):
    return ResourceLine(
        role="Consultant",
        seniority="Principal",
        location=location,
        allocation_pct=Decimal("1"),
        start=date(2026, 1, 1),
        end=date(2026, 2, 15),
        hours_billable=Decimal(str(hours)),
        hourly_bill_rate=Decimal("0"),
        hourly_cost=cost if cost is None else Decimal(str(cost)),
    )


class TestAssessment:
    def test_meets_policy(self) -> None:
        inp = AssessmentInputs(
            deliverable="Discovery report",
            total_price=Decimal("50000"),
            revenue_us=Decimal("50000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 500, 65)],  # 50k - 32.5k = 17.5k → 35%
        )
        result = AssessmentTemplate.compute(inp)
        assert result.complete is True
        assert result.gm_us == Decimal("0.35")
        assert check_floors(result)["requires_ceo"] is False

    def test_below_floor(self) -> None:
        inp = AssessmentInputs(
            deliverable="Discovery",
            total_price=Decimal("40000"),
            revenue_us=Decimal("40000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 500, 65)],
        )
        result = AssessmentTemplate.compute(inp)
        out = check_floors(result)
        assert out["failing"] == ["US"]
        assert out["requires_ceo"] is True

    def test_missing_cost(self) -> None:
        inp = AssessmentInputs(
            deliverable="Discovery",
            total_price=Decimal("50000"),
            revenue_us=Decimal("50000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 500, None)],
        )
        result = AssessmentTemplate.compute(inp)
        assert result.complete is False
        assert "resources[0].hourly_cost" in result.missing

    def test_mixed_geography(self) -> None:
        inp = AssessmentInputs(
            deliverable="Discovery",
            total_price=Decimal("110000"),
            revenue_us=Decimal("50000"),
            revenue_india=Decimal("60000"),
            resources=[
                _res("US", 500, 65),  # 50k rev, 32.5k cost → 35% (pass)
                _res("India", 600, 60),  # 60k rev, 36k cost → 40% (fails 50%)
            ],
        )
        result = AssessmentTemplate.compute(inp)
        out = check_floors(result)
        assert out["us_pass"] is True
        assert out["india_pass"] is False
        assert out["failing"] == ["India"]
        # Blended could look OK — verify it doesn't override the component fail.
        assert result.gm_blended is not None
        assert result.gm_india is not None and result.gm_india < Decimal("0.5")

    def test_missing_deliverable(self) -> None:
        inp = AssessmentInputs(
            deliverable="",
            total_price=Decimal("50000"),
            revenue_us=Decimal("50000"),
            revenue_india=Decimal("0"),
            resources=[_res("US", 500, 65)],
        )
        result = AssessmentTemplate.compute(inp)
        assert "deliverable" in result.missing
        assert result.complete is False
