"""Production Forecast projection checked against independent Company X constants."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, localcontext

import pytest

from app.gm.forecast import ForecastLine, project_outlook
from tests.s21_acceptance.test_company_x_forecast_oracle import AS_OF, company_x_rows

D = Decimal


def rows(start=date(2026, 11, 1), probability=D("0.70")):
    return tuple(ForecastLine(
        row_id=f"{row.source}:{row.month}", account_id="company-x", source_id=row.source,
        source_version="1", scope_id=row.source, month=row.month,
        lifecycle="signed" if row.signed else "needs_review", currency="USD",
        revenue=row.revenue, cost=row.cost, probability=row.probability,
        probability_source="Fixture assumption" if not row.signed else None,
        assumptions=("Even service month allocation",),
    ) for row in company_x_rows(start, probability))


@pytest.mark.parametrize("scenario,current,future,cost", [
    ("committed", "24000", "0", "0"),
    ("expected", "122000", "196000", "98000"),
    ("upside", "164000", "280000", "140000"),
])
def test_company_x_production_totals_match_independent_constants(scenario, current, future, cost):
    view = project_outlook(rows(), as_of=AS_OF, timezone="America/Los_Angeles", scenario=scenario)
    assert view["current_quarter"]["revenue"] == D(current)
    assert view["future"]["revenue"] == D(future)
    assert view["future"]["cost"] == D(cost)
    assert view["future"]["gm"] == (None if scenario == "committed" else D("0.5"))
    assert view["current_quarter"]["cost"] is None
    assert view["accounts"][0]["future"] == view["future"]
    assert len(view["months"]) == 9
    assert view["current_quarter"]["start"] == date(2026, 10, 1)
    assert view["future"]["start"] == date(2027, 1, 1)


@pytest.mark.parametrize("count,expected_months,revenue", [(1, 6, "147000"), (2, 9, "196000"), (4, 15, "196000")])
def test_all_selected_months_survive_drilldown(count, expected_months, revenue):
    view = project_outlook(rows(), as_of=AS_OF, timezone="America/Los_Angeles", future_quarters=count)
    assert len(view["months"]) == expected_months
    assert view["future"]["revenue"] == D(revenue)


def test_date_slip_probability_and_timezone_change_the_same_projection():
    view = project_outlook(rows(date(2026, 12, 1)), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["future"]["revenue"] == D("245000")
    assert view["future"]["cost"] == D("122500")
    view = project_outlook(rows(probability=D("0.5")), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["future"]["revenue"] == D("140000")
    boundary = datetime.fromisoformat("2026-10-01T06:59:59+00:00")
    view = project_outlook(rows(), as_of=boundary, timezone="America/Los_Angeles")
    assert view["future"]["revenue"] == D("269000")


def test_conversion_replaces_only_matching_scope_month_fraction_once():
    proposal = rows()[1]
    signed = replace(proposal, row_id="signed-new", source_id="sow-new", lifecycle="signed",
                     revenue=D("35000"), cost=D("17500"), scope_fraction=D("0.5"))
    view = project_outlook((proposal, signed), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["current_quarter"]["revenue"] == D("59500")
    assert view["current_quarter"]["cost"] == D("29750")
    with pytest.raises(ValueError, match="duplicate"):
        project_outlook((proposal, signed, signed), as_of=AS_OF, timezone="America/Los_Angeles")
    full = replace(signed, scope_fraction=D("1"), revenue=D("70000"), cost=D("35000"))
    view = project_outlook((proposal, full), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["current_quarter"]["revenue"] == D("70000")


def test_alternatives_lost_missing_probability_and_fx_do_not_silently_contribute():
    proposal = rows()[1]
    alternatives = (replace(proposal, row_id="a", source_id="a", scenario_group="option", selected=False),
                    replace(proposal, row_id="b", source_id="b", scenario_group="option", selected=True))
    view = project_outlook(alternatives, as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["current_quarter"]["revenue"] == D("49000")
    for change in ({"probability": None}, {"lifecycle": "closed_lost"}, {"currency": "EUR"}):
        view = project_outlook((replace(proposal, **change),), as_of=AS_OF, timezone="America/Los_Angeles")
        assert view["current_quarter"]["revenue"] == D("0")
        assert view["excluded"][0]["reasons"]


def test_unavoidable_cost_is_not_probability_weighted_and_accounts_reconcile():
    proposal = replace(rows()[1], unavoidable_cost=D("1000"))
    second = replace(proposal, row_id="second", source_id="second", scope_id="second", account_id="other")
    view = project_outlook((proposal, second), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["current_quarter"]["cost"] == D("49600")
    assert sum(a["current_quarter"]["revenue"] for a in view["accounts"]) == view["current_quarter"]["revenue"]


def test_mixed_currency_requires_versioned_fx_and_never_uses_float():
    line = replace(rows()[1], currency="EUR", fx_rate=D("1.2"), fx_version="finance-1", fx_date=date(2026, 10, 1))
    view = project_outlook((line,), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["current_quarter"]["revenue"] == D("58800")
    assert view["current_quarter"]["cost"] == D("29400")
    with pytest.raises(ValueError, match="Decimal"):
        project_outlook((replace(line, probability=0.7),), as_of=AS_OF, timezone="America/Los_Angeles")


def test_calendar_ratio_revenue_can_be_probability_weighted_without_false_precision_gap():
    with localcontext() as context:
        context.prec = 28
        prorated = D("100") / D("31")
        expected = prorated * D("0.7")
    line = replace(rows()[1], revenue=prorated, revenue_uses_ratio=True, cost=D("1"))
    view = project_outlook((line,), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["excluded"] == []
    assert view["current_quarter"]["revenue"] == expected
    assert view["current_quarter"]["cost"] == D("0.7")


def test_ratio_provenance_does_not_relax_exact_cost_precision():
    line = replace(rows()[1], revenue=D("100"), revenue_uses_ratio=True,
                   cost=D("1000000000000000000000000000000.01"))
    view = project_outlook((line,), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["rows"] == []
    assert "precision" in view["excluded"][0]["reasons"][0]


def test_ratio_aggregation_cannot_drop_a_whole_unit_or_cent_at_large_magnitudes():
    large = replace(rows()[1], revenue=D("1E30"), probability=D("1"))
    small = replace(large, row_id="ratio", source_id="ratio", scope_id="ratio",
                    revenue=D("0.01"), revenue_uses_ratio=True)
    with pytest.raises(ValueError, match="precision"):
        project_outlook((large, small), as_of=AS_OF, timezone="America/Los_Angeles")


def test_exact_fraction_cancellation_preserves_unavoidable_cost_and_fx():
    proposal = replace(rows()[1], scope_fraction=D("0.3"), revenue=D("300"), cost=D("150"),
                       unavoidable_cost=D("30"), currency="EUR", fx_rate=D("1.25"),
                       fx_version="finance-1", fx_date=date(2026, 10, 1), probability=D("0.5"))
    signed = replace(proposal, row_id="signed", source_id="signed", lifecycle="signed",
                     scope_fraction=D("0.1"), revenue=D("100"), cost=D("50"), unavoidable_cost=D("10"))
    view = project_outlook((proposal, signed), as_of=AS_OF, timezone="America/Los_Angeles")
    assert view["excluded"] == []
    assert view["current_quarter"]["revenue"] == D("250")
    assert view["current_quarter"]["cost"] == D("137.5")
    assert view["current_quarter"]["unavoidable_cost"] == D("37.5")
