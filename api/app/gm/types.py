"""Shared GM types. Pure library, no I/O.

Money is Python ``Decimal``. Never ``float``. Rounding is only applied for
display via :func:`quantize_money` — computations use unrounded values so
totals match to the cent regardless of intermediate precision.

See ``docs/build-guide.md`` §7 for the six engagement templates that consume
these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Literal, Optional

# --- Aliases ---------------------------------------------------------------

Location = Literal["US", "India"]
Geography = Literal["US", "India", "Mixed"]
Money = Decimal

_MONEY_QUANTUM = Decimal("0.01")


def quantize_money(value: Money) -> Money:
    """Round-half-even to two decimal places for **display only**.

    Never call this in the middle of a computation; §2 hard rule: compare
    unrounded, round only for display.
    """
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


# --- Enums -----------------------------------------------------------------


class EngagementType(str, Enum):
    """The six templates in build-guide §7, plus permanent placement."""

    STAFF_AUG = "staff_aug"
    SINGLE_RESOURCE = "single_resource"
    FIXED_PRICE = "fixed_price"
    ASSESSMENT = "assessment"
    TM = "tm"  # time and materials
    MANAGED_SERVICE = "managed_service"
    PERMANENT_PLACEMENT = "permanent_placement"


# --- Line items ------------------------------------------------------------


@dataclass(frozen=True)
class ResourceLine:
    """One person on the engagement.

    ``hourly_bill_rate`` and ``hourly_cost`` are per billable hour. A missing
    ``hourly_cost`` (``None``) marks the sheet incomplete — never treat it as
    zero (see CLAUDE.md rule 2, blueprint §2).
    """

    role: str
    seniority: str
    location: Location
    allocation_pct: Decimal  # 0..1
    start: date
    end: date
    hours_billable: Decimal
    hourly_bill_rate: Money
    hourly_cost: Optional[Money] = None
    validated_by: Optional[str] = None

    def revenue(self) -> Money:
        return self.hours_billable * self.hourly_bill_rate * self.allocation_pct

    def cost(self) -> Optional[Money]:
        if self.hourly_cost is None:
            return None
        return self.hours_billable * self.hourly_cost * self.allocation_pct


@dataclass(frozen=True)
class CostLine:
    """A non-labor cost. ``amount=None`` means "still pending" — flag it,
    do not silently treat as zero."""

    category: Literal["tools", "travel", "subcontractor", "other"]
    amount: Optional[Money]
    note: str = ""
    location: Location = "US"  # which component the cost lands in


# --- Result ----------------------------------------------------------------


@dataclass
class TemplateResult:
    """Result of a template computation.

    Component values (``*_us``/``*_india``) are ``Decimal("0")`` when the
    template has no revenue on that side. ``gm_us`` / ``gm_india`` are
    ``None`` when the corresponding revenue is zero (undefined GM), so that
    the caller can distinguish "no work here" from "0% margin".
    """

    revenue_us: Money = Decimal("0")
    cost_us: Money = Decimal("0")
    revenue_india: Money = Decimal("0")
    cost_india: Money = Decimal("0")
    gm_us: Optional[Decimal] = None
    gm_india: Optional[Decimal] = None
    gm_blended: Optional[Decimal] = None
    complete: bool = True
    missing: list[str] = field(default_factory=list)
    finance_summary: dict | None = None

    @property
    def revenue_total(self) -> Money:
        return self.revenue_us + self.revenue_india

    @property
    def cost_total(self) -> Money:
        return self.cost_us + self.cost_india

    @property
    def geography(self) -> Geography:
        has_us = self.revenue_us > 0
        has_in = self.revenue_india > 0
        if has_us and has_in:
            return "Mixed"
        if has_in:
            return "India"
        return "US"
