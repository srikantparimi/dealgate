"""Business-day arithmetic for approval SLA timers (S7 C).

Blueprint §4: "one business day to accept ownership, two business days per
approval". This module holds the pure helpers so the approvals service +
alert scheduler + tests share the same definition.

No holidays for now (open question tracked in docs/questions.md for the
Legal / HR calendar). Saturday + Sunday are the only non-business days.

Design rules:

- Only ``date`` in / ``date`` out — callers convert timestamps at the edge.
- ``add_business_days(start, 0)`` returns ``start`` verbatim (or the next
  business day if ``start`` itself falls on a weekend, so the SLA clock
  starts on a working day).
- ``business_days_between`` is half-open: ``start`` day excluded,
  ``end`` day included. Reversed range yields 0 (no negative counts).
"""

from __future__ import annotations

from datetime import date, timedelta


_WEEKEND: frozenset[int] = frozenset({5, 6})  # Saturday, Sunday


def is_business_day(day: date) -> bool:
    """True when ``day`` is Mon-Fri."""

    return day.weekday() not in _WEEKEND


def _next_business_day(day: date) -> date:
    """Return ``day`` if it's a business day, else the next Mon-Fri."""

    cursor = day
    while not is_business_day(cursor):
        cursor = cursor + timedelta(days=1)
    return cursor


def add_business_days(start: date, days: int) -> date:
    """Add ``days`` business days to ``start`` and return the resulting date.

    If ``start`` falls on a weekend we first walk forward to the next
    business day, then add ``days`` more. That matches the SLA rule: a
    package submitted on Saturday starts the clock on Monday, and 2
    business days later is Wednesday (not Sunday).
    """

    if days < 0:
        raise ValueError("days must be non-negative")
    cursor = _next_business_day(start)
    remaining = days
    while remaining > 0:
        cursor = cursor + timedelta(days=1)
        if is_business_day(cursor):
            remaining -= 1
    return cursor


def business_days_between(start: date, end: date) -> int:
    """Count business days strictly between ``start`` (exclusive) and ``end`` (inclusive).

    Half-open: the ``start`` day itself is not counted, the ``end`` day is
    (matches the alert scheduler's existing helper). Returns 0 when
    ``end <= start`` so callers do not need to guard.
    """

    if end <= start:
        return 0
    days = 0
    cursor = start
    while cursor < end:
        cursor = cursor + timedelta(days=1)
        if is_business_day(cursor):
            days += 1
    return days


__all__ = [
    "add_business_days",
    "business_days_between",
    "is_business_day",
]
