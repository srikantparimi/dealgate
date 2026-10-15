"""S23-PL2 B10 — CSV formula neutralisation for every CSV the product writes.

Spreadsheet programs evaluate a cell that starts with ``=``, ``+``, ``-`` or
``@`` (and some also after a leading tab or carriage return) as a formula, so a
HubSpot deal named ``=HYPERLINK(...)`` would run when someone opens the
export. Such a cell gets a leading apostrophe, which spreadsheets show as
text. A plain number (``-123.45``) can never be a formula and stays as it is,
so amounts keep summing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_PLAIN_NUMBER = re.compile(r"-?\d+(\.\d+)?")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def neutralise(value: Any) -> str:
    """The cell as text, prefixed with ``'`` when it could run as a formula."""
    text = "" if value is None else str(value)
    if not text or _PLAIN_NUMBER.fullmatch(text):
        return text
    return "'" + text if text.startswith(_FORMULA_START) else text


def safe_row(cells: Iterable[Any]) -> list[str]:
    return [neutralise(cell) for cell in cells]
