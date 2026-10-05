from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext

import pytest
from pydantic import TypeAdapter

from app.gm.calendar import DayHours, StaffingAssignment, WorkCalendar, monthly_staffing_schedule

D = Decimal
START = date(2026, 10, 1)
END = date(2027, 3, 31)


def assignment(**changes):
    work = DayHours(D('8'), D('8'), D('8'))
    off = DayHours(D('0'), D('0'), D('0'))
    values = dict(
        assignment_id='engineers', source_id='sow', source_version='1',
        component_id='team', profile_version='1', policy_version='1',
        role='Engineer', location='US', timezone='America/New_York', currency='USD',
        quantity=6, allocation=D('1'), bill_rate=D('100'), rate_version='hourly-bill-1',
        cost_rate=D('4800'), cost_version='monthly-confirmed-1', cost_rate_basis='monthly',
        calendar=WorkCalendar('fixture', '1', 'America/New_York', START, END,
                              (work, work, work, work, work, off, off)),
    )
    return StaffingAssignment(**(values | changes))


def schedule(item, start=START, end=END):
    return monthly_staffing_schedule(item, term_start=start, term_end=end)


def test_six_people_monthly_cost_not_hours_multiplied_and_no_ambient_precision():
    with localcontext() as context:
        context.prec = 3
        rows = schedule(assignment())
    assert all(row.complete for row in rows)
    assert [row.cost for row in rows] == [D('28800')] * 6
    assert sum(row.cost for row in rows) == D('172800')
    assert [row.paid_hours for row in rows] == list(map(D, ('1056', '1008', '1104', '1008', '960', '1104')))
    assert rows[0].revenue == D('105600')


@pytest.mark.parametrize('quantity,allocation,cost', [(2, '0.5', '4800'), (6, '0.25', '7200'), (1, '0', '0')])
def test_quantity_and_allocation_apply_exactly_once(quantity, allocation, cost):
    assert schedule(assignment(quantity=quantity, allocation=D(allocation)))[0].cost == D(cost)


@pytest.mark.parametrize('changes,start,end', [
    ({'start': date(2026, 10, 2)}, START, END),
    ({'end': date(2027, 3, 30)}, START, END),
    ({}, date(2026, 10, 2), END),
    ({}, START, date(2027, 3, 30)),
])
def test_partial_assignment_or_term_requires_own_cost_policy(changes, start, end):
    rows = schedule(assignment(**changes), start, end)
    incomplete = [row for row in rows if not row.complete]
    assert len(incomplete) == 1
    assert incomplete[0].cost is None
    assert any(gap.field == 'cost_proration' for gap in incomplete[0].missing)
    assert all(row.cost == D('28800') for row in rows if row.complete)


def test_explicit_full_month_partial_cost_and_legacy_conversion_rejected():
    row = schedule(assignment(cost_proration='full_month'), date(2026, 10, 30), date(2026, 10, 31))[0]
    assert row.complete
    assert row.cost == D('28800')
    assert row.paid_hours == D('48')
    with pytest.raises(ValueError, match='monthly'):
        row.as_resource_input()


@pytest.mark.parametrize('changes,field', [
    ({'calendar': None}, 'calendar'),
    ({'currency': None}, 'currency'),
    ({'cost_version': None}, 'cost_version'),
    ({'cost_rate': None}, 'cost_rate'),
])
def test_monthly_still_requires_confirmed_source_inputs(changes, field):
    row = schedule(assignment(**changes))[0]
    assert not row.complete
    assert any(gap.field == field for gap in row.missing)
    if field in {'calendar', 'currency', 'cost_rate'}:
        assert row.cost is None


def test_calendar_coverage_still_required():
    item = assignment()
    row = schedule(replace(item, calendar=replace(item.calendar, coverage_start=date(2026, 10, 2))))[0]
    assert row.cost is None
    assert not row.complete
    assert any(gap.field == 'calendar.coverage' for gap in row.missing)


@pytest.mark.parametrize('changes', [
    {'cost_rate_basis': 'annual'},
    {'cost_proration': 'calendar_days'}, {'cost_proration': ''},
])
def test_unsupported_basis_and_proration_rejected(changes):
    with pytest.raises(ValueError):
        assignment(**changes)


def test_typed_json_roundtrip_and_old_snapshot_default_hourly():
    adapter = TypeAdapter(StaffingAssignment)
    monthly = assignment(cost_proration='full_month')
    assert adapter.validate_json(adapter.dump_json(monthly)) == monthly
    raw = adapter.dump_python(monthly, mode='json')
    del raw['cost_rate_basis']
    del raw['cost_proration']
    raw['cost_rate'] = '60'
    old = adapter.validate_python(raw)
    assert old.cost_rate_basis == 'hourly'
    assert old.cost_proration is None
    row = schedule(old)[0]
    assert row.complete
    assert row.cost == D('63360')
    assert row.as_resource_input().cost_rate == D('60')


def test_explicit_null_basis_is_unresolved_not_legacy_hourly():
    adapter = TypeAdapter(StaffingAssignment)
    item = assignment(cost_rate_basis=None)
    assert adapter.validate_json(adapter.dump_json(item)).cost_rate_basis is None
    row = schedule(item)[0]
    assert not row.complete
    assert row.cost is None
    assert any(gap.field == 'cost_rate_basis' for gap in row.missing)


def test_commercial_typed_snapshot_monthly_billing_and_cost_are_independent():
    from app.gm.commercial import CalendarPricing, PricingComponent, StaffingRate, calculate_component
    from app.services.commercial_models import COMPONENT, SCHEDULE, parse_component

    item = assignment(bill_rate=None, rate_version=None)
    component = PricingComponent(
        component_id='team', version='1', source_id='sow', source_version='1',
        workstream_id='team', profile='calendar_staff_aug', profile_version='1',
        policy_version='1', source_evidence=('Synthetic monthly confirmed allocation',),
        service_start=START, service_end=END, timezone='America/New_York',
        currency='USD', billing_cadence='monthly', costs_confirmed=True,
        cost_basis='Confirmed monthly cost per person at full allocation', costs=(),
        staffing=(item,), pricing=CalendarPricing((StaffingRate(
            assignment_id='engineers', basis='monthly', rate=D('8000'),
            version='monthly-bill-1', proration='full_month',
        ),)),
    )
    parsed = parse_component(COMPONENT.dump_python(component, mode='json'))
    result = calculate_component(parsed)
    assert result.complete
    assert [(row.revenue, row.cost) for row in result.rows] == [(D('48000'), D('28800'))] * 6
    assert result.assess().revenue_total == D('288000')
    assert result.assess().cost_total == D('172800')
    restored = SCHEDULE.validate_json(SCHEDULE.dump_json(result))
    assert restored.component.staffing[0].cost_rate_basis == 'monthly'
    assert restored == result


@pytest.mark.parametrize('rate', [D('NaN'), D('Infinity'), D('-1')])
def test_monthly_invalid_decimal_cost_rejected(rate):
    with pytest.raises(ValueError):
        assignment(cost_rate=rate)
