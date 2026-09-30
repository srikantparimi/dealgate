"""S20 D8/T25: two-calendar-month renewal alert date.

Pure-function tests over :func:`app.services.renewals.compute_alert_date`
and its short-engagement / weekly-repeat companions. No database, no
async — the whole point of factoring the calendar math out of the
scheduler is to make it trivially testable.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.services.renewals import (
    BUSINESS_TIMEZONE,
    SHORT_ENGAGEMENT_MAX_DAYS,
    WEEKLY_REPEAT_UNTIL_DAYS,
    business_today,
    compute_alert_date,
    compute_short_engagement_alerts,
    weekly_repeat_dates,
)


# ---- compute_alert_date ------------------------------------------------


def test_two_calendar_months_before_march_31():
    # T25: month-end. March 31 minus two calendar months = January 31.
    assert compute_alert_date(date(2026, 3, 31)) == date(2026, 1, 31)


def test_month_end_clamps_when_target_month_is_shorter():
    # T25: October 31 minus two months = August 31 (August has 31 — no
    # clamp needed). But March 31 minus one-plus-one = January 31.
    # The critical clamp case is May 31 → March 31 (fine), Aug 31 →
    # June 30 (clamped, June has only 30).
    assert compute_alert_date(date(2026, 8, 31)) == date(2026, 6, 30)


def test_leap_year_boundary_feb_29():
    # T25: leap year — April 29 (leap year) minus two months = Feb 29.
    assert compute_alert_date(date(2028, 4, 29)) == date(2028, 2, 29)


def test_non_leap_year_feb_clamps_to_28():
    # T25: April 30 (non-leap) → Feb 28 (clamped, since Feb has 28 days
    # in 2026 but April 30 target-day is 30 > 28).
    assert compute_alert_date(date(2026, 4, 30)) == date(2026, 2, 28)


def test_january_wraps_to_previous_year():
    # 2026-01-15 minus two months = 2025-11-15. Year decrements twice.
    assert compute_alert_date(date(2026, 1, 15)) == date(2025, 11, 15)


def test_february_wraps_to_december():
    # 2026-02-14 minus two months = 2025-12-14.
    assert compute_alert_date(date(2026, 2, 14)) == date(2025, 12, 14)


def test_mid_month_no_clamp():
    # A boring middle-of-the-month date shifts back cleanly.
    assert compute_alert_date(date(2026, 6, 15)) == date(2026, 4, 15)


# ---- compute_short_engagement_alerts -----------------------------------


def test_short_engagement_returns_both_open_and_close():
    # T25: short assessment — term < 3 months (90d) → renewal review at
    # start and at close.
    start = date(2026, 1, 1)
    end = date(2026, 3, 15)  # 73 days — short
    result = compute_short_engagement_alerts(start=start, term_end=end)
    assert result == (start, end)


def test_engagement_of_exactly_ninety_days_is_not_short():
    # Boundary: SHORT_ENGAGEMENT_MAX_DAYS = 90. Duration of 90d is NOT
    # short (< 90 required).
    start = date(2026, 1, 1)
    end = start.replace(day=1)  # placeholder to type-hint
    end = date(2026, 4, 1)  # 90 days
    assert (end - start).days == 90
    assert compute_short_engagement_alerts(start=start, term_end=end) is None


def test_engagement_of_ninety_one_days_is_not_short():
    start = date(2026, 1, 1)
    end = date(2026, 4, 2)  # 91 days
    assert compute_short_engagement_alerts(start=start, term_end=end) is None


def test_negative_duration_returns_none():
    # Defensive: end before start.
    assert (
        compute_short_engagement_alerts(
            start=date(2026, 4, 1), term_end=date(2026, 3, 1)
        )
        is None
    )


# ---- weekly_repeat_dates -----------------------------------------------


def test_weekly_repeat_stops_two_weeks_before_term_end():
    # Alert 2026-01-31 (compute_alert_date(2026-03-31)); horizon is
    # term_end - 14d = 2026-03-17. Weekly steps: Jan-31, Feb-07, Feb-14,
    # Feb-21, Feb-28, Mar-07, Mar-14. Mar-21 falls outside horizon.
    alert = date(2026, 1, 31)
    end = date(2026, 3, 31)
    dates = weekly_repeat_dates(alert_date=alert, term_end=end)
    assert dates[0] == date(2026, 1, 31)
    assert dates[-1] <= end - _timedelta_days(WEEKLY_REPEAT_UNTIL_DAYS)
    # No date falls inside the last two weeks.
    for d in dates:
        assert (end - d).days >= WEEKLY_REPEAT_UNTIL_DAYS


def test_weekly_repeat_empty_when_alert_after_horizon():
    # Alert falls inside the two-week window — the weekly cadence never
    # emits anything (escalations take over).
    alert = date(2026, 3, 25)
    end = date(2026, 3, 31)
    assert weekly_repeat_dates(alert_date=alert, term_end=end) == ()


# ---- business_today ----------------------------------------------------


def test_business_today_uses_pacific_zone():
    # A datetime at 2026-01-31T20:00Z is 2026-01-31T12:00 PT (or 13:00
    # if PDT). Either way, the local calendar day is 2026-01-31. The
    # UTC day is also 2026-01-31, so this test is trivial — but its
    # sibling below is not.
    now = datetime(2026, 1, 31, 20, 0, tzinfo=UTC)
    assert business_today(now) == date(2026, 1, 31)


def test_business_today_before_utc_midnight_stays_previous_day_local():
    # A datetime at 2026-02-01T02:00Z is 2026-01-31T18:00 PT. The UTC
    # day has already rolled to Feb 1, but the business day is still
    # Jan 31 — and that is the day the two-month alert must fire on.
    now = datetime(2026, 2, 1, 2, 0, tzinfo=UTC)
    assert business_today(now) == date(2026, 1, 31)


def test_business_timezone_constant_is_los_angeles():
    # A drift here would silently shift every alert by whatever the
    # runtime happened to have set. Pin it.
    assert BUSINESS_TIMEZONE == "America/Los_Angeles"


# ---- test helpers ------------------------------------------------------


def _timedelta_days(n: int):
    from datetime import timedelta

    return timedelta(days=n)
