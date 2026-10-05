"""Independent S21F increment evidence; these do not close T07/T13/T19."""

import calendar
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.gm.calendar import (
    CalendarOverride, DayHours, StaffingAssignment, WorkCalendar, monthly_staffing_schedule,
)
from app.gm.engine import SowSpec, compute_gm

D = Decimal
HOLIDAYS = frozenset(date.fromisoformat(day) for day in (
    "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01",
    "2027-01-18", "2027-02-15", "2027-05-31", "2027-06-18", "2027-07-05",
))


def independent_days(start, end, holidays=HOLIDAYS):
    """Enumerate ordinals, independently of the production month/day traversal."""
    buckets = defaultdict(lambda: [0, 0])
    for ordinal in range(start.toordinal(), end.toordinal() + 1):
        day = date.fromordinal(ordinal)
        bucket = buckets[day.replace(day=1)]
        if day.weekday() < 5:
            bucket[1] += 1
            bucket[0] += day not in holidays
    return dict(sorted(buckets.items()))


def staffing(start, end, quantity=10, allocation=D("1"), holidays=HOLIDAYS):
    work, off = DayHours(D("8"), D("8"), D("8")), DayHours(D("0"), D("0"), D("0"))
    cal = WorkCalendar(
        "qa-calendar", "1", "America/New_York", start, end,
        (work,) * 5 + (off,) * 2,
        tuple(CalendarOverride(day, DayHours(D("0"), D("0"), D("8")), "QA holiday")
              for day in sorted(holidays) if start <= day <= end),
    )
    return StaffingAssignment(
        assignment_id="qa-assignment", source_id="qa-source", source_version="1",
        component_id="qa-hourly", profile_version="1", policy_version="1", role="Engineer",
        location="US", timezone=cal.timezone, currency="USD", quantity=quantity,
        allocation=allocation, calendar=cal, bill_rate=D("100"), cost_rate=D("60"),
        rate_version="1", cost_version="1",
    )


def test_independent_calendar_b_monthly_money_hours_and_margin():
    start, end = date(2026, 10, 1), date(2027, 7, 31)
    expected = independent_days(start, end)
    assert [v[0] for v in expected.values()] == [21, 19, 22, 19, 19, 23, 22, 20, 21, 21]
    assert [v[1] for v in expected.values()] == [22, 21, 23, 21, 20, 23, 22, 21, 22, 22]
    rows = monthly_staffing_schedule(staffing(start, end), term_start=start, term_end=end)
    for row, (month, (billable, paid)) in zip(rows, expected.items(), strict=True):
        assert row.month == month
        assert row.complete
        assert row.scheduled_hours == row.billable_hours == D(billable) * D("80")
        assert row.paid_hours == D(paid) * D("80")
        assert row.revenue == D(billable) * D("8000")
        assert row.cost == D(paid) * D("4800")
        result = compute_gm(SowSpec("staff_aug", (row.as_resource_input(),)))
        expected_revenue, expected_cost = D(billable) * D("8000"), D(paid) * D("4800")
        assert result.gm_blended == (expected_revenue - expected_cost) / expected_revenue
    revenue = sum(D(v[0]) * D("8000") for v in expected.values())
    cost = sum(D(v[1]) * D("4800") for v in expected.values())
    assert (revenue, cost) == (D("1656000"), D("1041600"))
    assert (revenue - cost) / revenue == D("0.3710144927536231884057971014")
    assert sum(row.billable_hours for row in rows) == D("16560")
    assert sum(row.paid_hours for row in rows) == D("17360")


def test_independent_company_x_a_even_months_quarters_and_shift():
    # This is an expectation artifact, not a production forecast acceptance test.
    months = [date(2026 + (10 + offset) // 12, (10 + offset) % 12 + 1, 1)
              for offset in range(6)]
    revenue, cost, probability = D("420000"), D("210000"), D("0.70")
    monthly_revenue, monthly_cost = revenue / D(len(months)), cost / D(len(months))
    quarters = defaultdict(lambda: D("0"))
    quarters[(2026, 4)] = D("24000")
    for month in months:
        quarters[(month.year, (month.month - 1) // 3 + 1)] += monthly_revenue * probability
    assert quarters == {(2026, 4): D("122000"), (2027, 1): D("147000"), (2027, 2): D("49000")}
    assert quarters[(2027, 1)] + quarters[(2027, 2)] == D("196000")
    assert (monthly_revenue, monthly_revenue * probability) == (D("70000"), D("49000"))
    assert (revenue * probability, cost * probability) == (D("294000"), D("147000"))
    assert (monthly_revenue - monthly_cost) / monthly_revenue == D("0.5")
    shifted = [month + timedelta(days=calendar.monthrange(month.year, month.month)[1])
               for month in months]
    assert (shifted[0], shifted[-1]) == (date(2026, 12, 1), date(2027, 5, 1))
    assert sum(monthly_revenue for _ in shifted) == revenue


@pytest.mark.parametrize("start,end", [
    (date(2024, 2, 28), date(2024, 3, 1)),
    (date(2100, 2, 28), date(2100, 3, 1)),
    (date(2026, 12, 31), date(2027, 1, 1)),
    (date(2026, 10, 12), date(2026, 10, 12)),
    (date(2026, 10, 31), date(2026, 11, 1)),
    (date(9999, 12, 30), date(9999, 12, 31)),
])
def test_independent_calendar_boundaries(start, end):
    item = staffing(start, end, quantity=3, allocation=D("0.375"))
    with localcontext() as context:
        context.prec = 6
        rows = monthly_staffing_schedule(item, term_start=start, term_end=end)
    expected = independent_days(start, end)
    assert [row.month for row in rows] == list(expected)
    for row, (billable, paid) in zip(rows, expected.values(), strict=True):
        assert row.billable_hours == D(billable) * D("9")
        assert row.paid_hours == D(paid) * D("9")
        assert row.revenue == D(billable) * D("900")
        assert row.cost == D(paid) * D("540")


def test_calendar_partition_conserves_independently_counted_quantities():
    start, end = date(2026, 12, 17), date(2027, 2, 23)
    item = staffing(start, end, quantity=7, allocation=D("0.6"))
    expected = independent_days(start, end)
    totals = (sum(v[0] for v in expected.values()) * D("33.6"),
              sum(v[1] for v in expected.values()) * D("33.6"))
    for offset in (0, 1, 14, 15, 30, 45, 67):
        split = start + timedelta(days=offset)
        rows = monthly_staffing_schedule(item, term_start=start, term_end=split)
        rows += monthly_staffing_schedule(item, term_start=split + timedelta(days=1), term_end=end)
        assert (sum(row.billable_hours for row in rows), sum(row.paid_hours for row in rows)) == totals


async def business_package(session):
    from app.services import approval_routing
    from app.services.approvals import submit_package
    from tests.test_approval_routing import fixture

    owner, deal, _, _, people = await fixture(session)
    plan = await approval_routing.submission_plan(session, opportunity_id=deal.id, actor_id=owner.id)
    package = await submit_package(session, actor_id=owner.id, opportunity_id=deal.id, routing=plan)
    return owner, package, people


async def test_test_ceo_cannot_approve_business_exception(session):
    from app.models.ceo_exception import CeoException
    from app.services.ceo_exception import decide
    from app.services.test_fixtures import E2E_USER_GROUP
    from tests.test_approvals import _seed_user

    _, package, _ = await business_package(session)
    bot = await _seed_user(session, email="qa-test-ceo@isolation.test", groups=["CEO", E2E_USER_GROUP])
    package.status = "pending_ceo_exception"
    exception = CeoException(id=uuid.uuid4(), package_id=package.id, brief_json={}, rationale_text="Fixture")
    session.add(exception)
    await session.commit()
    with pytest.raises(HTTPException) as denied:
        await decide(session, actor_id=bot.id, actor_groups=tuple(bot.groups),
                     exception_id=exception.id, decision="approve")
    assert denied.value.status_code == 403
    assert exception.decision is None
    assert package.status == "pending_ceo_exception"


async def test_legacy_task_path_excludes_test_reviewer_from_business_package(session):
    from app.models.task import Task
    from app.services.approvals import submit_package
    from app.services.test_fixtures import E2E_USER_GROUP
    from tests.test_approval_routing import fixture
    from tests.test_approvals import _seed_user

    owner, deal, _, _, _ = await fixture(session)
    bot = await _seed_user(session, email="qa-legacy@isolation.test", groups=["Delivery", E2E_USER_GROUP])
    await submit_package(session, actor_id=owner.id, opportunity_id=deal.id)
    assert not list((await session.scalars(select(Task).where(Task.owner_id == bot.id))).all())


@pytest.mark.parametrize("boundary", ["queue", "dispatch"])
async def test_task_linked_approval_reminder_blocks_test_identity(session, boundary):
    from app.integrations.ses import StubSES
    from app.models.notification import Notification
    from app.models.task import Task
    from app.services.notifications import queue_notification
    from app.services.test_fixtures import E2E_USER_GROUP
    from tests.test_approvals import _seed_user
    from worker.notification_sender import _handle_row

    _, _, people = await business_package(session)
    bot = await _seed_user(session, email="qa-reminder@isolation.test", groups=["Delivery", E2E_USER_GROUP])
    task = await session.scalar(select(Task).where(Task.owner_id == people["delivery"].id))
    task.owner_id = bot.id  # Historic contamination; task.created audit links its business package.
    await session.commit()
    payload = dict(user_id=bot.id, category="approval_pending", subject="Review overdue",
                   body_md="Business approval reminder", related_entity="task", related_entity_id=str(task.id))
    if boundary == "queue":
        with pytest.raises(HTTPException) as denied:
            await queue_notification(session, **payload, channels=("email",))
        assert denied.value.status_code == 403
    else:
        row = Notification(id=uuid.uuid4(), **payload, channel="email", status="pending", attempts=0)
        session.add(row)
        await session.commit()
        sink = StubSES()
        await _handle_row(session, sink, row)
        assert sink.sent == []
        assert row.status == "suppressed"
