"""S23-PL2 B8 / T7 — dates are calendar dates in America/Los_Angeles.

Frozen clocks at a month end, a quarter end and both DST changes. Each instant
is chosen so the UTC calendar date and the Los Angeles one differ (or sit
either side of a DST jump), so any drift to UTC changes the answer.

Unit half: ``business_today`` / ``la_date`` / ``preset_range`` for every
preset. API half: ``GET /pipeline/workspace`` returns exactly the deals each
preset names, for close, created and activity dates.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.services.business_time import (
    BUSINESS_TZ,
    DATE_PRESETS,
    business_now,
    business_today,
    la_date,
    preset_range,
)
from app.services.hubspot_pipeline import resolve_date_preset

LA = ZoneInfo("America/Los_Angeles")

# instant (UTC) → (LA today, current LA month, current LA quarter)
INSTANTS: dict[str, tuple[datetime, date, tuple[date, date], tuple[date, date]]] = {
    # Oct 31 23:30 PDT; UTC is already Nov 1.
    "month_end": (datetime(2026, 11, 1, 6, 30, tzinfo=UTC), date(2026, 10, 31),
                  (date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 10, 1), date(2026, 12, 31))),
    # Sep 30 23:30 PDT: LA is still in Q3, UTC is in Q4.
    "quarter_end": (datetime(2026, 10, 1, 6, 30, tzinfo=UTC), date(2026, 9, 30),
                    (date(2026, 9, 1), date(2026, 9, 30)), (date(2026, 7, 1), date(2026, 9, 30))),
    # DST ends Sun Nov 1 2026 at 02:00 PDT: 00:30 PDT, and 23:30 PST the same day.
    "dst_end_early": (datetime(2026, 11, 1, 7, 30, tzinfo=UTC), date(2026, 11, 1),
                      (date(2026, 11, 1), date(2026, 11, 30)), (date(2026, 10, 1), date(2026, 12, 31))),
    "dst_end_late": (datetime(2026, 11, 2, 7, 30, tzinfo=UTC), date(2026, 11, 1),
                     (date(2026, 11, 1), date(2026, 11, 30)), (date(2026, 10, 1), date(2026, 12, 31))),
    # DST starts Sun Mar 8 2026 at 02:00 PST: Mar 7 23:30 PST, and Mar 9 00:30 PDT.
    "dst_start_early": (datetime(2026, 3, 8, 7, 30, tzinfo=UTC), date(2026, 3, 7),
                        (date(2026, 3, 1), date(2026, 3, 31)), (date(2026, 1, 1), date(2026, 3, 31))),
    "dst_start_late": (datetime(2026, 3, 9, 7, 30, tzinfo=UTC), date(2026, 3, 9),
                       (date(2026, 3, 1), date(2026, 3, 31)), (date(2026, 1, 1), date(2026, 3, 31))),
}


def expected_range(preset: str, today: date, month: tuple[date, date], quarter: tuple[date, date],
                   date_from: date | None = None, date_to: date | None = None) -> tuple[date | None, date | None]:
    """The contract's preset text, written out independently of the service."""
    days = timedelta(days=1)
    return {
        "any": (None, None),
        "passed": (None, today - days),
        "next7": (today, today + 7 * days),
        "next30": (today, today + 30 * days),
        "next90": (today, today + 90 * days),
        "last7": (today - 6 * days, today),
        "last30": (today - 29 * days, today),
        "last90": (today - 89 * days, today),
        "month": month,
        "quarter": quarter,
        "custom": (date_from, date_to),
    }[preset]


def test_the_business_zone_resolves():
    # zoneinfo needs the system tz database; the API image must carry it.
    assert BUSINESS_TZ == "America/Los_Angeles"
    assert datetime(2026, 7, 1, 12, tzinfo=UTC).astimezone(ZoneInfo(BUSINESS_TZ)).utcoffset() == timedelta(hours=-7)


@pytest.mark.parametrize("name", list(INSTANTS))
def test_business_today_is_the_los_angeles_calendar_date(name):
    now, today, _, _ = INSTANTS[name]
    assert business_today(now) == today
    assert now.astimezone(LA).date() == today  # the table itself is right


@pytest.mark.parametrize("name", list(INSTANTS))
@pytest.mark.parametrize("preset", DATE_PRESETS)
def test_every_preset_at_every_frozen_instant(name, preset):
    now, today, month, quarter = INSTANTS[name]
    bounds = (today - timedelta(days=3), today + timedelta(days=3)) if preset == "custom" else (None, None)
    assert preset_range(preset, business_today(now), *bounds) == expected_range(
        preset, today, month, quarter, *bounds)


def test_custom_bounds_are_each_optional():
    today = date(2026, 10, 14)
    assert preset_range("custom", today, date(2026, 10, 1), None) == (date(2026, 10, 1), None)
    assert preset_range("custom", today, None, date(2026, 10, 9)) == (None, date(2026, 10, 9))
    assert preset_range("custom", today, None, None) == (None, None)
    # Bounds are ignored by every other preset.
    assert preset_range("next7", today, date(2020, 1, 1), date(2020, 1, 2)) == (today, date(2026, 10, 21))


def test_unknown_preset_is_rejected():
    with pytest.raises(ValueError):
        preset_range("this_month", date(2026, 10, 14))


def test_timestamps_become_los_angeles_dates():
    # 23:30 PDT on Oct 31 is Nov 1 in UTC.
    assert la_date(datetime(2026, 11, 1, 6, 30, tzinfo=UTC)) == date(2026, 10, 31)
    # SQLite hands timestamps back naive; they are UTC.
    assert la_date(datetime(2026, 11, 1, 6, 30)) == date(2026, 10, 31)
    # Either side of the spring-forward gap (02:00 PST → 03:00 PDT).
    assert la_date(datetime(2026, 3, 8, 7, 59, tzinfo=UTC)) == date(2026, 3, 7)
    assert la_date(datetime(2026, 3, 8, 8, 0, tzinfo=UTC)) == date(2026, 3, 8)
    # Either side of fall-back: 01:30 happens twice on Nov 1; both are Nov 1.
    assert la_date(datetime(2026, 11, 1, 8, 30, tzinfo=UTC)) == date(2026, 11, 1)
    assert la_date(datetime(2026, 11, 1, 9, 30, tzinfo=UTC)) == date(2026, 11, 1)
    assert la_date(datetime(2026, 11, 2, 7, 59, tzinfo=UTC)) == date(2026, 11, 1)
    assert la_date(datetime(2026, 11, 2, 8, 0, tzinfo=UTC)) == date(2026, 11, 2)
    assert la_date(None) is None


def test_the_clock_honours_dealgate_now(monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", "2026-11-01T06:30:00Z")
    assert business_now() == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert business_today() == date(2026, 10, 31)
    # An explicit instant always wins over the override.
    assert business_today(datetime(2026, 11, 2, 7, 30, tzinfo=UTC)) == date(2026, 11, 1)
    monkeypatch.delenv("DEALGATE_NOW")
    assert abs(business_now() - datetime.now(UTC)) < timedelta(minutes=1)


def test_the_old_presets_are_unchanged():
    # The old endpoints keep resolve_date_preset (pinned by test_s20_filter_dates).
    today = date(2026, 10, 14)
    assert resolve_date_preset("last7", today=today) == (date(2026, 10, 7), today)
    assert resolve_date_preset("this_month", today=today) == (date(2026, 10, 1), date(2026, 10, 31))


# --- API half: the workspace applies every preset in Los Angeles dates -------------------

import uuid  # noqa: E402

from app.auth import AuthUser  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402
from tests.test_s23_pl2_workspace import client_for  # noqa: E402

READER = AuthUser(uuid.uuid4(), "dates@example.test", "Dates Reader", ("SalesLeader",))


def _boundary_dates(today: date, month: tuple[date, date], quarter: tuple[date, date]) -> list[date]:
    offsets = (-91, -90, -89, -30, -29, -8, -7, -6, -1, 0, 1, 7, 8, 30, 31, 90, 91)
    days = {today + timedelta(days=n) for n in offsets}
    for start, end in (month, quarter):
        days |= {start - timedelta(days=1), start, end, end + timedelta(days=1)}
    return sorted(days)


@pytest.mark.parametrize("name", list(INSTANTS))
async def test_workspace_presets_use_los_angeles_dates(session, monkeypatch, name):
    now, today, month, quarter = INSTANTS[name]
    monkeypatch.setenv("DEALGATE_NOW", now.isoformat())
    dates = _boundary_dates(today, month, quarter)
    by_title: dict[str, dict[str, date | None]] = {}
    for index, day in enumerate(dates):
        # Created just after LA midnight, last activity just before the next LA midnight:
        # both are that LA day, but the UTC dates differ.
        # Stored as UTC instants, as intake writes them (SQLite keeps no offset).
        created = (datetime.combine(day, datetime.min.time(), LA) + timedelta(minutes=5)).astimezone(UTC)
        activity = (datetime.combine(day + timedelta(days=1), datetime.min.time(), LA)
                    - timedelta(minutes=5)).astimezone(UTC)
        title = f"Deal {index:02}"
        session.add(Opportunity(source="hubspot", hubspot_deal_id=f"t7-{index}", name=title, close_date=day,
                                hubspot_created_at=created, created_at=created, hubspot_last_activity_at=activity,
                                amount=Decimal("1.00"), currency="USD", governance_status="Intake"))
        by_title[title] = {"close": day, "created": day, "activity": day}
    undated_created = datetime(2000, 1, 1, 20, tzinfo=UTC)
    session.add(Opportunity(source="hubspot", hubspot_deal_id="t7-none", name="Deal undated", close_date=None,
                            hubspot_created_at=None, created_at=undated_created, hubspot_last_activity_at=None,
                            governance_status="Intake"))
    by_title["Deal undated"] = {"close": None, "created": date(2000, 1, 1), "activity": None}
    await session.commit()

    custom_bounds = [(today - timedelta(days=7), today + timedelta(days=7)), (today, None), (None, today)]
    async with client_for(session, READER) as api:
        for field in DATE_FIELDS_UNDER_TEST:
            for preset in DATE_PRESETS:
                for bounds in custom_bounds if preset == "custom" else [(None, None)]:
                    params = {"date_field": field, "date_preset": preset, "page_size": 100, "sort": "name"}
                    if bounds[0]:
                        params["date_from"] = bounds[0].isoformat()
                    if bounds[1]:
                        params["date_to"] = bounds[1].isoformat()
                    response = await api.get("/pipeline/workspace", params=params)
                    assert response.status_code == 200, response.text
                    body = response.json()
                    assert body["today"] == today.isoformat()
                    low, high = expected_range(preset, today, month, quarter, *bounds)
                    expected = sorted(
                        title for title, values in by_title.items()
                        if preset == "any" or (values[field] is not None
                                               and (low is None or values[field] >= low)
                                               and (high is None or values[field] <= high)))
                    assert sorted(row["title"] for row in body["rows"]) == expected, (name, field, preset, bounds)
    # The created / activity dates on the rows are the Los Angeles calendar dates.
    async with client_for(session, READER) as api:
        rows = (await api.get("/pipeline/workspace", params={"page_size": 100})).json()["rows"]
    for row in rows:
        values = by_title[row["title"]]
        assert row["created_date"] == values["created"].isoformat()
        assert row["last_activity_date"] == (values["activity"].isoformat() if values["activity"] else None)


DATE_FIELDS_UNDER_TEST = ("close", "created", "activity")
