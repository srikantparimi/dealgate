"""Cost-free, dated recruiting proposals. A match never reserves or hires anyone."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Context, Decimal, Inexact, localcontext

from app.gm.calendar import _decimal, _period, _timezone
from app.gm.engine import GM_PRECISION

ZERO = Decimal("0")
ONE = Decimal("1")
DAY = timedelta(days=1)
VERSION = "people-interval-allocation-v2"


def _identity(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _capability(row):
    for key in ("role", "level", "location", "timezone"):
        if not isinstance(getattr(row, key), str):
            raise ValueError(f"{key} must be text or explicitly empty")
    if row.timezone:
        _timezone(row.timezone)
    if not isinstance(row.skills, tuple) or any(not isinstance(skill, str) or not skill.strip() for skill in row.skills):
        raise ValueError("Skills require explicit nonempty keys")
    _period(row.start, row.end)
    if row.end == date.max:
        raise ValueError("End date must allow an exclusive boundary")
    _decimal(row.allocation, "allocation", ONE)
    if row.allocation == ZERO:
        raise ValueError("Allocation must be positive")


@dataclass(frozen=True)
class Demand:
    id: str
    account_id: str
    role: str
    skills: tuple[str, ...]
    level: str
    location: str
    timezone: str
    quantity: int
    allocation: Decimal
    start: date
    end: date
    probability: Decimal | None
    lifecycle: str
    selected: bool = True
    retained_person_ids: tuple[str, ...] = ()

    def __post_init__(self):
        _capability(self)
        if not _identity(self.id) or not _identity(self.account_id) or type(self.quantity) is not int or not 1 <= self.quantity <= 10000:
            raise ValueError("Demand requires identity and positive integer quantity")
        if type(self.selected) is not bool:
            raise ValueError("Scenario selection must be an explicit boolean")
        if self.probability is not None:
            _decimal(self.probability, "probability", ONE)
        if self.lifecycle not in {"needs_review", "tentative", "won_unsigned", "committed", "closed_lost", "dismissed", "expired"}:
            raise ValueError("Invalid demand lifecycle")
        if (not isinstance(self.retained_person_ids, tuple) or
            len(set(self.retained_person_ids)) != len(self.retained_person_ids) or
            len(self.retained_person_ids) > self.quantity or any(not _identity(key) for key in self.retained_person_ids)):
            raise ValueError("Continuity requires distinct explicit person identities")


@dataclass(frozen=True)
class Capacity:
    person_id: str
    role: str
    skills: tuple[str, ...]
    level: str
    location: str
    timezone: str
    allocation: Decimal
    start: date
    end: date

    def __post_init__(self):
        _capability(self)
        if not _identity(self.person_id):
            raise ValueError("Stable person identity is required")


@dataclass(frozen=True)
class Commitment:
    person_id: str
    source_id: str
    allocation: Decimal
    start: date
    end: date
    status: str

    def __post_init__(self):
        _period(self.start, self.end)
        _decimal(self.allocation, "commitment allocation", ONE)
        if (not _identity(self.person_id) or not _identity(self.source_id) or self.allocation == ZERO
            or self.status not in {"committed", "reserved", "hired"} or self.end == date.max):
            raise ValueError("Invalid authoritative commitment")


def _missing(row):
    return [key for key in ("role", "skills", "level", "location", "timezone")
        if not (getattr(row, key).strip() if isinstance(getattr(row, key), str) else getattr(row, key))]


def _matches(need, capacity):
    return (not _missing(need) and not _missing(capacity)
        and all(getattr(need, key) == getattr(capacity, key) for key in ("role", "level", "location", "timezone"))
        and set(need.skills) <= set(capacity.skills))


def _month_after(day):
    if day.year == 9999 and day.month == 12:
        return date.max
    return date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)


def allocate_demand(demands: tuple[Demand, ...], capacities: tuple[Capacity, ...],
    commitments: tuple[Commitment, ...], *, policy_version: str, coverages=()) -> dict:
    """Allocate globally before any caller applies account/owner display filters."""
    if not _identity(policy_version):
        raise ValueError("A versioned proposal ordering is required")
    if len({row.id for row in demands}) != len(demands):
        raise ValueError("duplicate demand identity")
    from app.gm.demand_coverage import apply_coverage, validate_coverage
    validate_coverage(demands, coverages)
    capacity_by_person = {}
    for row in capacities:
        others = capacity_by_person.setdefault(row.person_id, [])
        if any(row.start <= other.end and other.start <= row.end for other in others):
            raise ValueError("overlapping gross capacity for one person")
        others.append(row)
    seen_commitments = {}
    for row in commitments:
        key = (row.person_id, row.source_id)
        others = seen_commitments.setdefault(key, [])
        if any(row.start <= other.end and other.start <= row.end for other in others):
            raise ValueError("duplicate commitment identity or overlapping segments")
        others.append(row)
    included = [row for row in demands if row.selected and row.lifecycle not in {"closed_lost", "dismissed", "expired"}]
    excluded = [{"id": row.id, "reason": "not_selected" if not row.selected else row.lifecycle}
        for row in demands if row not in included]
    result = {"calculation_version": VERSION, "policy_version": policy_version,
        "policy_status": "proposal", "is_reservation": False, "intervals": [], "months": [], "excluded": excluded}
    if not included:
        return result
    start, end = min(row.start for row in included), max(row.end for row in included) + DAY
    boundaries = {start, end}
    for row in (*included, *capacities, *commitments, *coverages):
        boundaries.update(day for day in (row.start, row.end + DAY) if start <= day <= end)
    month = _month_after(start)
    while month < end:
        boundaries.add(month)
        month = _month_after(month)
    ordered = sorted(boundaries)
    monthly = {}
    with localcontext(Context(prec=GM_PRECISION)) as context:
        context.traps[Inexact] = True
        for left, right in zip(ordered, ordered[1:]):
            residual = apply_coverage(demands, coverages, left, right - DAY) if coverages else included
            active = sorted((row for row in residual if row.selected and row.lifecycle not in {
                "closed_lost", "dismissed", "expired"} and row.start <= left <= row.end),
                key=lambda row: (row.lifecycle != "committed", row.start, row.id))
            supply = {row.person_id: row for row in capacities if row.start <= left <= row.end}
            available = {key: row.allocation for key, row in supply.items()}
            committed = {}
            overcommitted = set()
            for item in commitments:
                if item.start <= left <= item.end and item.person_id in available:
                    committed[(item.person_id, item.source_id)] = item.allocation
                    available[item.person_id] -= item.allocation
                    if available[item.person_id] < ZERO:
                        overcommitted.add(item.person_id)
            available = {key: max(ZERO, value) for key, value in available.items()}
            rows = []
            for need in active:
                matches = []
                missing = _missing(need)
                retained = set(need.retained_person_ids)
                chosen = set()
                for index in range(need.quantity):
                    required_person = need.retained_person_ids[index] if index < len(need.retained_person_ids) else None
                    # Same-source continuity consumes its existing commitment, not
                    # the free pool a second time. Other sources never receive it.
                    credit = committed.get((required_person, need.id), ZERO) if required_person not in overcommitted else ZERO
                    eligible = [key for key in sorted(supply) if key not in chosen
                        and (key == required_person if required_person else key not in retained)
                        and available[key] + credit >= need.allocation and _matches(need, supply[key])]
                    if eligible:
                        key = eligible[0]
                        chosen.add(key)
                        available[key] -= max(ZERO, need.allocation - credit)
                        matches.append({"person_id": key, "allocation": need.allocation,
                            "continuity": required_person is not None})
                    elif required_person:
                        missing.append(f"continuity:{required_person}")
                required = need.allocation * need.quantity
                matched = sum((row["allocation"] for row in matches), ZERO)
                rows.append({"id": need.id, "account_id": need.account_id, "quantity": need.quantity,
                    "retained_quantity": len(retained), "incremental_quantity": need.quantity - len(retained),
                    "required_fte": required, "matched_fte": matched, "gap_fte": required - matched,
                    "lifecycle": need.lifecycle, "probability": need.probability, "matches": matches, "missing": missing})
            result["intervals"].append({"start": left, "end_exclusive": right, "demands": rows,
                "overcommitted_person_ids": sorted(overcommitted)})
            key = left.replace(day=1)
            totals = {"peak_headcount": sum(row["quantity"] for row in rows),
                "peak_fte": sum((row["required_fte"] for row in rows), ZERO),
                "gap_fte": sum((row["gap_fte"] for row in rows), ZERO)}
            summary = monthly.setdefault(key, {"month": key, **totals})
            for field, value in totals.items():
                summary[field] = max(summary[field], value)
    result["months"] = list(monthly.values())
    return result
