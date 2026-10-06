"""Duration-aware term assist (S22 redesign, owner click-through fix).

Many SOWs state a duration ("seven weeks from kickoff", a milestone
table ending at "Week 7") without calendar dates. The extractor is
right to leave term_start/term_end unknown — but once a human supplies
the kickoff date, the end date is pure arithmetic from the SOW's own
stated duration. This module finds that stated duration
DETERMINISTICALLY (regex over the already-extracted field text — no AI,
rule 2/6: nothing here invents a number) and computes the derived end
date server-side (rule 9: no date math in the browser).

The result is a SUGGESTION with its verbatim source snippet. A human
applies it through the normal field-confirm flow; nothing auto-saves.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from app.services.provenance import value_of

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "sixteen": 16, "twenty": 20, "twenty-four": 24,
    "thirty-six": 36, "fifty-two": 52,
}

# "7 weeks", "seven weeks", "7-week", "seven (7) weeks"
_EXPLICIT_WEEKS = re.compile(
    r"\b(\d{1,3}|" + "|".join(_WORD_NUMBERS) + r")[\s-]*(?:\(\s*\d{1,3}\s*\)\s*)?weeks?\b",
    re.IGNORECASE,
)
# "6 months", "six-month", "twelve (12) months"
_EXPLICIT_MONTHS = re.compile(
    r"\b(\d{1,2}|" + "|".join(_WORD_NUMBERS) + r")[\s-]*(?:\(\s*\d{1,2}\s*\)\s*)?months?\b",
    re.IGNORECASE,
)
# Milestone phase labels: "Week 7", "Weeks 2-5" — the largest week
# mentioned is the stated span of the plan.
_WEEK_LABEL = re.compile(r"\bweeks?\s+(\d{1,3})(?:\s*[–—-]\s*(\d{1,3}))?", re.IGNORECASE)

# Fields worth scanning, most authoritative first.
_FIELDS = ("billing_basis", "scope_summary", "milestones", "deliverables", "acceptance")

_SNIPPET = 160


def _to_int(token: str) -> int | None:
    token = token.lower()
    if token.isdigit():
        value = int(token)
        return value if 0 < value <= 160 else None
    return _WORD_NUMBERS.get(token)


def _snippet(text: str, match: re.Match[str]) -> str:
    lo = max(0, match.start() - 60)
    hi = min(len(text), match.end() + 100)
    return text[lo:hi].strip()[:_SNIPPET]


def stated_duration(extracted_fields: dict[str, Any] | None) -> dict[str, Any] | None:
    """Find the SOW's stated duration in the extracted field text.

    Returns ``{"weeks": int, "source_field": str, "quote": str}`` or
    ``None`` when no duration is stated. Explicit "N weeks"/"N months"
    statements win over milestone week labels; earlier fields win over
    later ones.
    """
    fields = extracted_fields or {}
    best_label: dict[str, Any] | None = None
    for name in _FIELDS:
        raw = value_of(fields.get(name))
        if not raw or not isinstance(raw, str):
            continue
        match = _EXPLICIT_WEEKS.search(raw)
        if match:
            weeks = _to_int(match.group(1))
            if weeks:
                return {"weeks": weeks, "source_field": name, "quote": _snippet(raw, match)}
        match = _EXPLICIT_MONTHS.search(raw)
        if match:
            months = _to_int(match.group(1))
            if months and months <= 36:
                # Months stated, no dates: weeks ≈ months — keep months
                # explicit so the caller can say "N months" honestly.
                return {
                    "months": months,
                    "source_field": name,
                    "quote": _snippet(raw, match),
                }
        if best_label is None:
            top = 0
            top_match: re.Match[str] | None = None
            for label in _WEEK_LABEL.finditer(raw):
                weeks = _to_int(label.group(2) or label.group(1)) or 0
                if weeks > top:
                    top, top_match = weeks, label
            if top_match and top > 0:
                best_label = {
                    "weeks": top,
                    "source_field": name,
                    "quote": _snippet(raw, top_match),
                }
    return best_label


def derived_end(start: date, duration: dict[str, Any]) -> date:
    """End date = start + the stated duration (server-side arithmetic).

    A "7 weeks from kickoff" engagement starting 2026-10-01 runs through
    2026-11-18 (inclusive last day of week 7). Months add calendar
    months, landing on the day before the same day-of-month.
    """
    if "weeks" in duration:
        return start + timedelta(weeks=int(duration["weeks"])) - timedelta(days=1)
    months = int(duration["months"])
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    from calendar import monthrange

    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day) - timedelta(days=1)
