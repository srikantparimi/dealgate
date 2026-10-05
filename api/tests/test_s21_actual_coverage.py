"""Literal Finance-certified scope replacement; never infer coverage from dates."""
from datetime import UTC, datetime
from decimal import Decimal, localcontext

import pytest

from app.gm.coverage import reconcile_actual_coverage


AS_OF = datetime(2026, 10, 20, 12, tzinfo=UTC)


def schedule(**changes):
    return dict(row_id="gm:0", account_id="account", source_id="gm", source_version="sow",
                month="2026-10-01", currency="USD", revenue="24000", cost="10000") | changes


def actual(identity="revenue", measure="recognized_revenue", amount="11000.99", **changes):
    return dict(id=identity, source_system="finance", source_id=identity, revision=1,
        account_id="account", gm_model_id="gm", period_month="2026-10-01", measure=measure,
        amount=amount, currency="USD", source_date="2026-10-15", source_detached=False,
        coverage=dict(sow_version_id="sow", schedule_row=0, fraction_start="0", fraction_end="0.5",
                      through_date="2026-10-15", basis_evidence="Finance confirms same service basis")) | changes


def run(records, schedules=None, **changes):
    return reconcile_actual_coverage(schedules or [schedule()], records,
        **(dict(as_of=AS_OF, timezone="UTC", currency="USD") | changes))


def test_literal_half_scope_replaces_not_adds_full_schedule():
    result = run([actual(), actual("cost", "delivery_cost", "6000"),
                  actual("invoice", "billed", "15000"), actual("cash", "cash_collected", "8000")])
    revenue, cost = result["rows"][0]["revenue"], result["rows"][0]["cost"]
    assert revenue == dict(scheduled=Decimal("24000"), actual_to_date=Decimal("11000.99"),
        covered_fraction=Decimal("0.5"), uncovered_forecast=Decimal("12000"),
        estimate=Decimal("23000.99"), actual_ids=["revenue"])
    assert cost["estimate"] == Decimal("11000")
    assert result["totals"]["revenue"] == Decimal("23000.99")
    assert result["totals"]["cost"] == Decimal("11000")
    assert result["totals"]["profit"] == Decimal("12000.99")
    assert {item["id"] for item in result["excluded"]} == {"invoice", "cash"}
    assert result["cutoff"] == "2026-10-20"


def test_correction_uses_latest_source_revision_without_double_coverage():
    previous = actual()
    corrected = actual("revenue-corrected", amount="10500", source_id="revenue", revision=2)
    result = run([previous, corrected, actual("cost", "delivery_cost", "6000")])
    assert result["totals"]["revenue"] == Decimal("22500")
    assert result["totals"]["profit"] == Decimal("11500")
    assert result["rows"][0]["revenue"]["actual_ids"] == ["revenue-corrected"]
    assert result["excluded"][0]["id"] == "revenue"


def test_transitive_overlaps_exclude_every_participant_but_keep_disjoint_interval():
    records = []
    for identity, left, right in (("a", "0", "0.3"), ("b", "0.2", "0.5"),
                                  ("c", "0.4", "0.6"), ("d", "0.6", "1")):
        record = actual(identity, amount="100")
        record["coverage"] |= dict(fraction_start=left, fraction_end=right)
        records.append(record)
    result = run(records)
    assert {item["id"] for item in result["excluded"]} == {"a", "b", "c"}
    assert result["rows"][0]["revenue"]["actual_ids"] == ["d"]
    assert result["totals"]["revenue"] == Decimal("14500")


@pytest.mark.parametrize("change", [
    {"account_id": "foreign"}, {"gm_model_id": "other"}, {"source_detached": True},
    {"period_month": "2026-09-01"}, {"source_date": "2026-10-21"},
    {"source_date": "2026-10-14"}, {"currency": "EUR"}, {"coverage": None},
    {"amount": 1.2}, {"amount": "NaN"},
])
def test_unmatched_and_malformed_actuals_stay_separate(change):
    result = run([actual(**change)])
    assert result["rows"][0]["revenue"]["estimate"] == Decimal("24000")
    assert len(result["excluded"]) == 1 and result["excluded"][0]["reason"]


@pytest.mark.parametrize("change", [
    {"sow_version_id": "wrong"}, {"schedule_row": True}, {"schedule_row": 1},
    {"fraction_start": "0.5", "fraction_end": "0.5"}, {"fraction_end": "1.1"},
    {"fraction_start": -0.1}, {"through_date": "2026-10-21"},
    {"through_date": "2026-09-30"}, {"basis_evidence": " "},
])
def test_invalid_coverage_does_not_replace_anything(change):
    row = actual()
    row["coverage"] |= change
    result = run([row])
    assert result["rows"][0]["revenue"]["covered_fraction"] == 0
    assert len(result["excluded"]) == 1


def test_cost_and_revenue_are_independent_unknown_cost_stays_unknown():
    result = run([actual("cost", "delivery_cost", "6000")])
    assert result["totals"]["revenue"] == Decimal("24000")
    assert result["totals"]["cost"] == Decimal("11000")
    unknown = run([actual(), actual("cost", "delivery_cost", "6000")], [schedule(cost=None)])
    assert unknown["totals"]["revenue"] == Decimal("23000.99")
    assert unknown["totals"]["cost"] is None
    assert unknown["totals"]["profit"] is None and unknown["totals"]["gm_pct"] is None
    assert unknown["rows"][0]["cost"]["actual_ids"] == []


def test_zero_revenue_and_negative_correction_are_not_unassessed_zero_margin():
    result = run([], [schedule(revenue="0")])
    assert result["totals"]["gm_pct"] is None
    row = actual(amount="-100")
    row["coverage"]["fraction_end"] = "1"
    result = run([row])
    assert result["totals"]["revenue"] == Decimal("-100")
    assert result["totals"]["gm_pct"] is None


def test_explicit_fx_converts_each_measure_without_probability():
    result = run([actual(amount="100.01", currency="EUR", fx_rate="1.25",
                         fx_version="treasury-1", fx_date="2026-10-01")])
    assert result["rows"][0]["revenue"]["actual_to_date"] == Decimal("125.0125")
    assert result["totals"]["revenue"] == Decimal("12125.0125")
    converted = run([], [schedule(currency="EUR", fx_rate="1.25", fx_version="treasury-1", fx_date="2026-10-01")])
    assert converted["totals"]["revenue"] == Decimal("30000")


def test_current_month_uses_local_cutoff_and_not_full_horizon():
    result = run([], [schedule(), schedule(row_id="gm:1", month="2026-11-01")],
        as_of=datetime(2026, 11, 1, 1, tzinfo=UTC), timezone="America/New_York")
    assert result["cutoff"] == "2026-10-31" and len(result["rows"]) == 1


def test_fraction_math_does_not_depend_on_ambient_precision():
    with localcontext() as context:
        context.prec = 3
        result = run([actual(), actual("cost", "delivery_cost", "6000")])
    assert result["totals"]["profit"] == Decimal("12000.99")


def test_duplicate_record_and_schedule_identity_never_double_count():
    result = run([actual(), actual()])
    assert result["rows"][0]["revenue"]["covered_fraction"] == 0
    ambiguous = run([actual()], [schedule(), schedule()])
    assert ambiguous["rows"] == []
    assert ambiguous["totals"]["revenue"] is None


def test_unrepresentable_aggregate_is_visible_without_losing_independent_cost():
    result = run([], [schedule(revenue="9999999999999999999999999999", cost="1"),
                      schedule(row_id="gm:1", revenue="0.1", cost="2")])
    assert len(result["rows"]) == 2
    assert result["totals"] == dict(revenue=None, cost=Decimal("3"), profit=None, gm_pct=None)
    assert result["excluded"] == [{"id": "totals:revenue",
        "reason": "Aggregate monetary precision requires review"}]


def test_unrepresentable_profit_keeps_revenue_and_cost_but_not_margin():
    result = run([], [schedule(revenue="9999999999999999999999999999", cost="0.1")])
    assert result["totals"]["revenue"] == Decimal("9999999999999999999999999999")
    assert result["totals"]["cost"] == Decimal("0.1")
    assert result["totals"]["profit"] is None and result["totals"]["gm_pct"] is None
    assert result["excluded"] == [{"id": "totals:profit",
        "reason": "Aggregate monetary precision requires review"}]
