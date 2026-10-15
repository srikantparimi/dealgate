"""S23-PL2 B8 — one business clock: calendar dates in America/Los_Angeles.

"Today" is the calendar date in Los Angeles, never the server's (UTC on ECS)
or the database session's. Timestamps (HubSpot created / last activity) are
compared as the Los Angeles calendar date they fall on. Every caller passes
``now`` explicitly; when it does not, ``DEALGATE_NOW`` (an ISO instant, as the
schedulers and ``engagement_forecast.today()`` honour it) freezes the clock
for tests.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

BUSINESS_TZ = "America/Los_Angeles"
_ZONE = ZoneInfo(BUSINESS_TZ)

DATE_PRESETS: tuple[str, ...] = (
    "any", "passed", "next7", "next30", "next90", "last7", "last30", "last90",
    "month", "quarter", "custom",
)
_NEXT = {"next7": 7, "next30": 30, "next90": 90}
_LAST = {"last7": 7, "last30": 30, "last90": 90}


def _aware(value: datetime) -> datetime:
    # SQLite returns timestamptz values naive; they are UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def business_now(now: datetime | None = None) -> datetime:
    """The current instant (UTC-aware), honouring ``DEALGATE_NOW``."""
    if now is not None:
        return _aware(now)
    raw = os.environ.get("DEALGATE_NOW")
    if raw:
        return _aware(datetime.fromisoformat(raw.replace("Z", "+00:00"))).astimezone(UTC)
    return datetime.now(UTC)


def business_today(now: datetime | None = None) -> date:
    """Today's calendar date in America/Los_Angeles."""
    return business_now(now).astimezone(_ZONE).date()


def la_date(value: datetime | None) -> date | None:
    """The Los Angeles calendar date an instant falls on."""
    if value is None:
        return None
    return _aware(value).astimezone(_ZONE).date()


def _month(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, following - timedelta(days=1)


def _quarter(today: date) -> tuple[date, date]:
    first_month = (today.month - 1) // 3 * 3 + 1
    start = date(today.year, first_month, 1)
    _, end = _month(date(today.year, first_month + 2, 1))
    return start, end


def preset_range(preset: str, today: date, date_from: date | None = None,
                 date_to: date | None = None) -> tuple[date | None, date | None]:
    """Inclusive ``(from, to)`` calendar dates for a preset; ``None`` = open.

    ``passed`` is before today; ``nextN`` is today through today+N; ``lastN``
    is today-(N-1) through today; ``month`` / ``quarter`` are the current Los
    Angeles calendar month / quarter; ``custom`` uses the given bounds, each
    optional. ``any`` is no constraint. The caller excludes rows without the
    date for every preset other than ``any``.
    """
    if preset == "any":
        return None, None
    if preset == "passed":
        return None, today - timedelta(days=1)
    if preset in _NEXT:
        return today, today + timedelta(days=_NEXT[preset])
    if preset in _LAST:
        return today - timedelta(days=_LAST[preset] - 1), today
    if preset == "month":
        return _month(today)
    if preset == "quarter":
        return _quarter(today)
    if preset == "custom":
        return date_from, date_to
    raise ValueError(f"unknown date preset: {preset}")
