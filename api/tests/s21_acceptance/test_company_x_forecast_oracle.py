"""T19/Oracle A expectation artifact, not production Forecast acceptance.

Only stdlib date/Decimal arithmetic derives the oracle. No feature response or
implementation is mocked. The literal matrices are authoritative fixture facts.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

D = Decimal
AS_OF = datetime.fromisoformat("2026-10-01T12:00:00-07:00")
SCENARIOS = ("committed", "expected", "upside")


@dataclass(frozen=True)
class OracleMonth:
    source: str
    month: date
    signed: bool
    revenue: Decimal
    cost: Decimal | None
    probability: Decimal | None


def company_x_rows(start=date(2026, 11, 1), probability=D("0.70")):
    # The directive does not supply assessment cost: it must remain unknown.
    signed = OracleMonth("signed-assessment", date(2026, 10, 1), True, D("24000"), None, None)
    months = []
    for offset in range(6):
        index = start.year * 12 + start.month - 1 + offset
        months.append(date(index // 12, index % 12 + 1, 1))
    return (signed,) + tuple(OracleMonth("unsigned-project", month, False,
        D("420000") / D("6"), D("210000") / D("6"), probability) for month in months)


def quarter(day):
    return day.year, (day.month - 1) // 3 + 1


def future_quarters(as_of, count, timezone="America/Los_Angeles"):
    local = as_of.astimezone(ZoneInfo(timezone))
    year, number = quarter(local.date())
    index = year * 4 + number - 1
    return tuple(((index + offset) // 4, (index + offset) % 4 + 1)
                 for offset in range(1, count + 1))


def oracle_total(rows, scenario, periods):
    revenue, cost, cost_known = D("0"), D("0"), True
    for row in rows:
        if quarter(row.month) not in periods:
            continue
        weight = D("1") if row.signed or scenario == "upside" else (
            D("0") if scenario == "committed" else row.probability)
        if weight is None:
            raise ValueError("Unsigned probability is unresolved")
        if weight == D("0"):
            continue
        revenue += row.revenue * weight
        if row.cost is None:
            cost_known = False
        else:
            cost += row.cost * weight
    return revenue, cost if cost_known else None


@pytest.mark.parametrize("scenario,monthly", [
    ("committed", ("24000", "0", "0", "0", "0", "0", "0")),
    ("expected", ("24000", "49000", "49000", "49000", "49000", "49000", "49000")),
    ("upside", ("24000", "70000", "70000", "70000", "70000", "70000", "70000")),
])
def test_company_x_independent_monthly_scenario_matrix(scenario, monthly):
    rows = company_x_rows()
    actual = tuple(oracle_total((row,), scenario, (quarter(row.month),))[0] for row in rows)
    assert actual == tuple(map(D, monthly))
    assert [row.month for row in rows] == [date(2026, 10, 1), date(2026, 11, 1),
        date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]


@pytest.mark.parametrize("scenario,quarter_revenue,future_revenue,future_cost", [
    ("committed", ("24000", "0", "0"), "0", "0"),
    ("expected", ("122000", "147000", "49000"), "196000", "98000"),
    ("upside", ("164000", "210000", "70000"), "280000", "140000"),
])
def test_company_x_quarters_and_future_exclude_current_signed_assessment(
    scenario, quarter_revenue, future_revenue, future_cost,
):
    rows = company_x_rows()
    periods = ((2026, 4), (2027, 1), (2027, 2))
    assert tuple(oracle_total(rows, scenario, (period,))[0] for period in periods) == tuple(map(D, quarter_revenue))
    future = future_quarters(AS_OF, 2)
    assert future == ((2027, 1), (2027, 2))
    assert oracle_total(rows, scenario, future) == (D(future_revenue), D(future_cost))


@pytest.mark.parametrize("count,periods,revenue,cost", [
    (1, ((2027, 1),), "147000", "73500"),
    (2, ((2027, 1), (2027, 2)), "196000", "98000"),
    (4, ((2027, 1), (2027, 2), (2027, 3), (2027, 4)), "196000", "98000"),
])
def test_company_x_future_horizon_is_full_quarters_only(count, periods, revenue, cost):
    assert future_quarters(AS_OF, count) == periods
    assert (2026, 4) not in periods
    assert oracle_total(company_x_rows(), "expected", periods) == (D(revenue), D(cost))


@pytest.mark.parametrize("instant,periods,expected", [
    ("2026-10-01T06:59:59+00:00", ((2026, 4), (2027, 1)), "269000"),
    ("2026-10-01T07:00:00+00:00", ((2027, 1), (2027, 2)), "196000"),
])
def test_company_x_quarter_rollover_uses_organization_timezone(instant, periods, expected):
    actual_periods = future_quarters(datetime.fromisoformat(instant), 2)
    assert actual_periods == periods
    assert oracle_total(company_x_rows(), "expected", actual_periods)[0] == D(expected)


def test_company_x_start_slip_preserves_fee_and_moves_future_coverage():
    rows = company_x_rows(start=date(2026, 12, 1))
    proposal = tuple(row for row in rows if not row.signed)
    assert (proposal[0].month, proposal[-1].month) == (date(2026, 12, 1), date(2027, 5, 1))
    assert sum(row.revenue for row in proposal) == D("420000")
    assert sum(row.cost for row in proposal) == D("210000")
    assert oracle_total(rows, "expected", ((2026, 4),))[0] == D("73000")
    assert oracle_total(rows, "expected", future_quarters(AS_OF, 2)) == (D("245000"), D("122500"))


def test_company_x_whole_proposal_weights_revenue_and_cost_once():
    proposal = tuple(row for row in company_x_rows() if not row.signed)
    revenue, cost = oracle_total(proposal, "expected", ((2026, 4), (2027, 1), (2027, 2)))
    assert (revenue, cost) == (D("294000"), D("147000"))
    assert (revenue - cost) / revenue == D("0.5")


def test_company_x_current_assessment_cost_is_unknown_not_invented():
    rows = company_x_rows()
    for scenario in SCENARIOS:
        assert oracle_total(rows, scenario, ((2026, 4),))[1] is None


@pytest.mark.parametrize("probability,revenue,cost", [
    ("0", "0", "0"), ("0.5", "140000", "70000"), ("1", "280000", "140000"),
])
def test_company_x_probability_change_updates_both_future_money_totals(probability, revenue, cost):
    rows = company_x_rows(probability=D(probability))
    assert oracle_total(rows, "expected", future_quarters(AS_OF, 2)) == (D(revenue), D(cost))
    assert oracle_total(rows, "upside", future_quarters(AS_OF, 2)) == (D("280000"), D("140000"))


def test_company_x_missing_probability_cannot_mean_zero_or_full_value():
    rows = tuple(replace(row, probability=None) for row in company_x_rows())
    with pytest.raises(ValueError, match="probability is unresolved"):
        oracle_total(rows, "expected", future_quarters(AS_OF, 2))
