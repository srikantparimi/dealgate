"""Independent pure Forecast QA; no persisted/API/staging acceptance is claimed."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, localcontext

import pytest

from app.gm.forecast import ForecastLine, project_outlook

D = Decimal
JAN = date(2027, 1, 1)
AS_OF = datetime.fromisoformat("2026-10-01T12:00:00-07:00")


def line(**changes):
    values = dict(row_id="proposal", account_id="company-x", source_id="plan-1",
                  source_version="1", scope_id="economic-work-1", month=JAN,
                  lifecycle="tentative", currency="USD", revenue=D("1000"), cost=D("400"),
                  probability=D("0.5"), probability_source="Confirmed Sales assumption",
                  assumptions=("Confirmed service month and fee",))
    return ForecastLine(**(values | changes))


def outlook(rows, **changes):
    return project_outlook(tuple(rows), **(dict(as_of=AS_OF, timezone="America/Los_Angeles") | changes))


def company_x():
    signed = line(row_id="assessment", source_id="assessment", scope_id="assessment",
                  lifecycle="signed", month=date(2026, 10, 1), revenue=D("24000"),
                  cost=None, probability=None, probability_source=None)
    months = ((2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3), (2027, 4))
    return (signed,) + tuple(line(row_id=f"project-{year}-{month}", month=date(year, month, 1),
        revenue=D("70000"), cost=D("35000"), probability=D("0.70")) for year, month in months)


@pytest.mark.parametrize("scenario,current,revenue,cost,gm", [
    ("committed", "24000", "0", "0", None),
    ("expected", "122000", "196000", "98000", "0.5"),
    ("upside", "164000", "280000", "140000", "0.5"),
])
def test_company_x_scenarios_match_independent_fixture_constants(scenario, current, revenue, cost, gm):
    view = outlook(company_x(), scenario=scenario)
    assert view["current_quarter"]["revenue"] == D(current)
    assert view["future"]["revenue"] == D(revenue)
    assert view["future"]["cost"] == D(cost)
    assert view["future"]["gm"] == (D(gm) if gm else None)
    assert view["current_quarter"]["cost"] is None
    assert view["current_quarter"]["gm"] is None
    assert view["future"]["start"] == JAN
    assert view["future"]["end_exclusive"] == date(2027, 7, 1)
    assert view["accounts"][0]["future"] == view["future"]
    assert view["excluded"] == []


@pytest.mark.parametrize("count,revenue,months", [(1, "147000", 6), (2, "196000", 9), (4, "196000", 15)])
def test_future_full_quarters_never_include_current_quarter(count, revenue, months):
    view = outlook(company_x(), future_quarters=count)
    assert view["future"]["revenue"] == D(revenue)
    assert len(view["months"]) == months
    assert view["current_quarter"]["revenue"] == D("122000")
    assert view["future"]["start"] == JAN


@pytest.mark.parametrize("instant,start,revenue", [
    ("2026-10-01T06:59:59+00:00", date(2026, 10, 1), "269000"),
    ("2026-10-01T07:00:00+00:00", JAN, "196000"),
])
def test_timezone_boundary_uses_local_quarter(instant, start, revenue):
    view = outlook(company_x(), as_of=datetime.fromisoformat(instant))
    assert view["future"]["start"] == start
    assert view["future"]["revenue"] == D(revenue)


def test_signed_unknown_cost_preserves_known_money_without_complete_gm():
    signed = line(row_id="signed", source_id="sow", scope_id="signed-work", lifecycle="signed",
                  revenue=D("100"), cost=None)
    view = outlook((signed, line()))
    assert view["future"]["revenue"] == D("600")
    assert view["future"]["cost"] is None
    assert view["future"]["known_cost"] == D("200")
    assert view["future"]["cost_complete"] is False
    assert view["future"]["gm"] is None


def test_unsigned_unknown_cost_is_excluded_with_visible_reason():
    view = outlook((line(cost=None),))
    assert view["future"]["revenue"] == D("0")
    assert view["rows"] == []
    assert view["excluded"][0]["row_id"] == "proposal"
    assert any("cost" in reason.lower() for reason in view["excluded"][0]["reasons"])


@pytest.mark.parametrize("scenario,revenue,cost", [
    ("committed", "0", "100"), ("expected", "250", "225"), ("upside", "1000", "600"),
])
def test_unavoidable_cost_is_subset_and_only_avoidable_cost_is_weighted(scenario, revenue, cost):
    view = outlook((line(cost=D("600"), unavoidable_cost=D("100"), probability=D("0.25")),), scenario=scenario)
    assert view["future"]["revenue"] == D(revenue)
    assert view["future"]["cost"] == D(cost)
    assert view["future"]["unavoidable_cost"] == D("100")


def test_unselected_alternative_and_closed_lost_never_contribute():
    a = line(scenario_group="alternatives")
    b = replace(a, row_id="other", source_id="other", selected=False)
    lost = line(row_id="lost", source_id="lost", scope_id="lost", lifecycle="closed_lost")
    view = outlook((a, b, lost))
    assert view["future"]["revenue"] == D("500")
    assert {row["row_id"] for row in view["excluded"]} == {"other", "lost"}


def test_two_selected_alternative_sources_are_rejected():
    a = line(scenario_group="alternatives")
    with pytest.raises(ValueError, match="exclusive"):
        outlook((a, replace(a, row_id="other", source_id="other")))


def test_mixed_source_versions_cannot_produce_fresh_totals():
    with pytest.raises(ValueError, match="versions"):
        outlook((line(), line(row_id="version-2", source_version="2", month=date(2027, 2, 1))))


def test_full_conversion_replaces_only_matching_account_scope_and_month():
    proposal = line()
    signed = replace(proposal, row_id="signed", source_id="sow", lifecycle="signed")
    february = replace(proposal, row_id="february", month=date(2027, 2, 1))
    other_account = replace(proposal, row_id="other-account", account_id="company-y")
    view = outlook((proposal, signed, february, other_account))
    assert view["future"]["revenue"] == D("2000")
    assert view["future"]["cost"] == D("800")
    assert {row["row_id"] for row in view["excluded"]} == {"proposal"}
    assert [account["future"]["revenue"] for account in view["accounts"]] == [D("1500"), D("500")]


@pytest.mark.parametrize("fraction,covered,fee,signed_fee,revenue,cost", [
    ("1", "0.5", "1000", "500", "750", "375"),
    ("0.3", "0.1", "300", "100", "200", "100"),
    ("0.7", "0.2", "700", "200", "450", "225"),
])
def test_partial_conversion_uses_exact_fraction_before_weighting(
    fraction, covered, fee, signed_fee, revenue, cost,
):
    proposal = line(scope_fraction=D(fraction), revenue=D(fee), cost=D(fee) / D("2"))
    signed = replace(proposal, row_id="signed", source_id="signed-sow", lifecycle="signed",
                     scope_fraction=D(covered), revenue=D(signed_fee), cost=D(signed_fee) / D("2"))
    view = outlook((proposal, signed))
    assert view["excluded"] == [], "Exact commercial money must not fail because a scope ratio repeats"
    assert view["future"]["revenue"] == D(revenue)
    assert view["future"]["cost"] == D(cost)


@pytest.mark.parametrize("lifecycle", ["tentative", "signed"])
def test_duplicate_source_scope_month_cannot_be_reintroduced_with_new_row_id(lifecycle):
    original = line(lifecycle=lifecycle, scope_fraction=D("0.5"))
    with pytest.raises(ValueError, match="duplicate|scope"):
        outlook((original, replace(original, row_id="retry-generated-row-id")))


@pytest.mark.parametrize("field", ["revenue", "cost"])
def test_aggregate_money_preserves_cents_or_explicitly_reports_precision(field):
    large = line(row_id="large", source_id="large", scope_id="large", probability=D("1"),
                 **{field: D("1E30")})
    small = line(row_id="small", source_id="small", scope_id="small", account_id="company-y",
                 probability=D("1"), **{field: D("0.01")})
    with localcontext() as context:
        context.prec = 50
        expected = D("1E30") + D("0.01")
    try:
        view = outlook((large, small))
    except ValueError as error:
        assert "precision" in str(error).lower()
        return
    precision_reported = any("precision" in reason.lower() for row in view["excluded"] for reason in row["reasons"])
    assert precision_reported or view["future"][field] == expected, "Aggregation silently discarded a cent"


def test_fx_conversion_retains_original_currency_revision_and_unavoidable_cost():
    foreign = line(currency="EUR", fx_rate=D("1.25"), fx_version="finance-2026-10",
                   fx_date=date(2026, 10, 1), unavoidable_cost=D("100"))
    view = outlook((foreign,))
    assert view["future"]["revenue"] == D("625")
    assert view["future"]["cost"] == D("312.5")
    assert view["future"]["unavoidable_cost"] == D("125")
    assert view["rows"][0]["original_currency"] == "EUR"
    assert view["rows"][0]["fx_version"] == "finance-2026-10"


@pytest.mark.parametrize("changes", [
    {"fx_version": None}, {"fx_date": None}, {"fx_version": "   "},
    {"probability_source": "   "}, {"assumptions": ("",)},
])
def test_unresolved_fx_or_planning_provenance_does_not_become_confirmed_money(changes):
    foreign = line(currency="EUR", fx_rate=D("1.25"), fx_version="finance-1", fx_date=date(2026, 10, 1))
    view = outlook((replace(foreign, **changes),))
    assert view["future"]["revenue"] == D("0")
    assert view["rows"] == []
    assert view["excluded"][0]["reasons"]


def test_missing_currency_never_assumes_reporting_currency():
    view = outlook((line(currency=None),))
    assert view["rows"] == []
    assert view["future"]["revenue"] == D("0")
    assert any("currency" in reason.lower() for reason in view["excluded"][0]["reasons"])
