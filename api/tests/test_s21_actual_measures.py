from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.gm.actuals import summarize_financial_actuals


def row(measure, amount, **changes):
    return {"id": measure, "period_month": "2026-10-01", "measure": measure,
            "amount": amount, "currency": "USD", "source_date": "2026-10-01", **changes}


def test_actual_bases_are_separate_not_a_second_forecast_or_probability_weighted():
    result = summarize_financial_actuals([
        row("recognized_revenue", "12000.01"), row("billed", "15000"),
        row("cash_collected", "8000"), row("delivery_cost", "6000"),
    ], as_of=datetime(2026, 10, 2, tzinfo=UTC), timezone="America/Los_Angeles", currency="USD")
    assert {r["measure"]: r["amount"] for r in result["totals"]} == {
        "recognized_revenue": Decimal("12000.01"), "billed": Decimal("15000"),
        "cash_collected": Decimal("8000"), "delivery_cost": Decimal("6000")}
    assert result["blended_with_forecast"] is False


def test_missing_fx_and_future_cutoff_are_visible_not_invented_money():
    result = summarize_financial_actuals([
        row("recognized_revenue", "100", currency="EUR"),
        row("cash_collected", "200", source_date="2026-10-03"),
    ], as_of=datetime(2026, 10, 2, tzinfo=UTC), timezone="America/Los_Angeles", currency="USD")
    assert result["totals"] == []
    assert len(result["excluded"]) == 2


def test_exact_fx_and_corrections_preserve_period_and_negative_amounts():
    result = summarize_financial_actuals([
        row("recognized_revenue", "100.01", currency="EUR", fx_rate="1.1234",
            fx_version="treasury-2026-10", fx_date="2026-10-01"),
        row("delivery_cost", "-10.12"),
    ], as_of=datetime(2026, 10, 2, tzinfo=UTC), timezone="UTC", currency="USD")
    assert {r["measure"]: r["amount"] for r in result["totals"]} == {
        "recognized_revenue": Decimal("112.351234"), "delivery_cost": Decimal("-10.12")}
    assert all(r["period_month"] == "2026-10-01" for r in result["totals"])


@pytest.mark.parametrize("changes", [
    {"amount": 1.2}, {"amount": "NaN"}, {"amount": "1" + "0" * 100 + ".01"},
    {"measure": "revenue"}, {"period_month": "2026-10-02"},
    {"currency": "EUR", "fx_rate": "1", "fx_version": "x", "fx_date": "2026-10-03"},
])
def test_invalid_or_unrepresentable_money_is_explicitly_excluded(changes):
    source = row("recognized_revenue", "100")
    source.update(changes)
    result = summarize_financial_actuals([source], as_of=datetime(2026, 10, 2, tzinfo=UTC),
                                        timezone="UTC", currency="USD")
    assert not result["totals"] and len(result["excluded"]) == 1
