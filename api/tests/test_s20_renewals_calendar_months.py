"""T25 · renewals two calendar months + edge cases (S20 · W5).

Per D8:
> Renewals: two calendar months before term end; month-end clamped;
> business timezone.

L15 flagged that the current UI says `term_end - 60 days`, which is
wrong for months with 28-31 days. This test asserts the D8 rule.

**Skeleton, xfail until W4 lands D8 semantics (owner: W4).**

Test cases:
  1. term_end = 2027-03-15 → renewal trigger = 2027-01-15.
  2. term_end = 2027-03-01 → renewal trigger = 2027-01-01
     (NOT 2026-12-30 which is term_end - 60 days).
  3. term_end = 2027-04-30 → renewal trigger = 2027-02-28
     (Feb has 28 days; month-end clamped).
  4. term_end = 2028-04-30 → renewal trigger = 2028-02-29
     (2028 is a leap year).
  5. Timezone is America/Los_Angeles; a term_end at 2027-03-01 00:00 UTC
     does NOT shift the trigger date by a day.
  6. Short assessment (< 60 days total) → alert at engagement start;
     rule documented in decisions.md.
  7. Weekly repeat: once triggered, the reminder fires every 7 days
     until acknowledged.
  8. Unverified claimed extension does NOT push the trigger.
"""

from __future__ import annotations

from datetime import date

import pytest


@pytest.mark.xfail(reason="depends on W4 renewals calendar-month engine (D8)", strict=False)
def test_normal_march_15():
    from app.services.renewals import compute_trigger_date  # noqa: WPS433
    assert compute_trigger_date(term_end=date(2027, 3, 15)) == date(2027, 1, 15)


@pytest.mark.xfail(reason="depends on W4 D8 engine")
def test_march_1_uses_january_1_not_60_days_back():
    from app.services.renewals import compute_trigger_date  # noqa: WPS433
    # 60 days before 2027-03-01 is 2026-12-30, which is WRONG under D8.
    # The correct value is 2027-01-01 (two calendar months).
    assert compute_trigger_date(term_end=date(2027, 3, 1)) == date(2027, 1, 1)


@pytest.mark.xfail(reason="depends on W4 D8 engine + month-end clamp")
def test_april_30_clamps_to_feb_28():
    from app.services.renewals import compute_trigger_date  # noqa: WPS433
    assert compute_trigger_date(term_end=date(2027, 4, 30)) == date(2027, 2, 28)


@pytest.mark.xfail(reason="depends on W4 D8 engine + leap year")
def test_april_30_leap_year_gives_feb_29():
    from app.services.renewals import compute_trigger_date  # noqa: WPS433
    assert compute_trigger_date(term_end=date(2028, 4, 30)) == date(2028, 2, 29)


@pytest.mark.xfail(reason="depends on W4 TZ handling")
def test_tz_boundary_no_day_shift():
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 short-assessment rule")
def test_short_assessment_alerts_at_start():
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 weekly-repeat scheduler")
def test_weekly_repeat_until_acknowledged():
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 extension verification")
def test_unverified_extension_does_not_push_trigger():
    raise AssertionError("skeleton")
