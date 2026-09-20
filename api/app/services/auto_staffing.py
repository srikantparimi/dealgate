"""Auto-staffing service (Sprint 9 wave 1, story C).

Given an engagement type + extracted SOW fields, produce a proposed
staffing grid the Delivery Model Builder opens with pre-filled. Every
proposed line carries a ``provenance`` (extracted / calculated /
looked_up / defaulted) so the confirmation screen can render its
badges.

The staff builder is deliberately deterministic — LLMs never write a
row (rule 6). Fixed-price and assessment types lean on the past-SOW +
capability catalog retrieval services; the pgvector search is injected
so tests can pass a stub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Iterable

from app.services.provenance import value_of


# 40h/week/FTE is the manifesto §4 default; SOWs stating otherwise
# override via ``extracted["fte_hours_per_week"]``.
DEFAULT_FTE_HOURS_PER_WEEK: Decimal = Decimal("40")
DEFAULT_FORECAST_UTILIZATION: Decimal = Decimal("0.75")


PastSowSearch = Callable[[str], Awaitable[list[dict[str, Any]]]]
CapabilitySearch = Callable[[str], Awaitable[list[dict[str, Any]]]]


@dataclass
class StaffingLine:
    """One proposed resource_line for the Builder to consume."""

    role: str
    seniority: str
    location: str
    allocation_pct: Decimal
    hours_billable: Decimal
    hourly_bill_rate: Decimal
    provenance: str
    start_date: date | None = None
    end_date: date | None = None
    source_id: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "seniority": self.seniority,
            "location": self.location,
            "allocation_pct": format(self.allocation_pct, "f"),
            "hours_billable": format(self.hours_billable, "f"),
            "hourly_bill_rate": format(self.hourly_bill_rate, "f"),
            "provenance": self.provenance,
            "source_id": self.source_id,
            "warning": self.warning,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }


@dataclass
class AutoStaffingResult:
    lines: list[StaffingLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


# --- helpers ---------------------------------------------------------------


def _dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _term_dates(extracted: dict[str, Any]) -> tuple[date | None, date | None]:
    start = _date(value_of(extracted.get("term_start")))
    end = _date(value_of(extracted.get("term_end")))
    return start, end


def _term_weeks(start: date | None, end: date | None) -> Decimal:
    if start is None or end is None:
        return Decimal("4")  # sensible default for un-dated SOWs
    days = (end - start).days
    if days <= 0:
        return Decimal("1")
    return Decimal(days) / Decimal("7")


def _fte_hours_per_week(extracted: dict[str, Any]) -> Decimal:
    override = _dec(value_of(extracted.get("fte_hours_per_week")), Decimal("0"))
    if override > 0:
        return override
    return DEFAULT_FTE_HOURS_PER_WEEK


def _default_location(extracted: dict[str, Any]) -> str:
    loc = value_of(extracted.get("primary_location"))
    if isinstance(loc, str) and loc in {"US", "India"}:
        return loc
    return "US"


def _scope_query(extracted: dict[str, Any]) -> str:
    parts: list[str] = []
    for name in ("scope_summary", "deliverables"):
        v = value_of(extracted.get(name))
        if isinstance(v, list):
            parts.extend(str(x) for x in v if x)
        elif v:
            parts.append(str(v))
    return "\n".join(parts)


# --- per-type builders -----------------------------------------------------


def _build_from_resource_table(
    extracted: dict[str, Any],
    *,
    start: date | None,
    end: date | None,
) -> list[StaffingLine]:
    """Straight readout of the SOW's resource table (staff_aug / single_resource)."""

    rows = value_of(extracted.get("resource_table")) or value_of(
        extracted.get("resources")
    )
    if not isinstance(rows, list):
        return []
    default_loc = _default_location(extracted)
    lines: list[StaffingLine] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            StaffingLine(
                role=str(row.get("role") or "TBD"),
                seniority=str(row.get("seniority") or "TBD"),
                location=str(row.get("location") or default_loc),
                allocation_pct=_dec(row.get("allocation_pct"), Decimal("1")),
                hours_billable=_dec(row.get("hours"), Decimal("0")),
                hourly_bill_rate=_dec(row.get("hourly_rate"), Decimal("0")),
                provenance="extracted",
                start_date=_date(row.get("start_date")) or start,
                end_date=_date(row.get("end_date")) or end,
            )
        )
    return lines


def _managed_service_lines(
    extracted: dict[str, Any],
    *,
    start: date | None,
    end: date | None,
) -> tuple[list[StaffingLine], list[str]]:
    """coverage_hours ÷ FTE capacity per shift → headcount by role."""

    coverage = _dec(value_of(extracted.get("coverage_hours")), Decimal("0"))
    if coverage <= 0:
        return [], ["managed_service: coverage_hours missing; no lines proposed"]

    fte_hours = _fte_hours_per_week(extracted)
    headcount_decimal = coverage / fte_hours if fte_hours > 0 else Decimal("0")
    # Round up — you cannot staff a fractional FTE for coverage.
    from decimal import ROUND_UP

    headcount = int(headcount_decimal.to_integral_value(rounding=ROUND_UP))
    headcount = max(headcount, 1)

    role = str(value_of(extracted.get("primary_role")) or "Support Engineer")
    seniority = str(value_of(extracted.get("primary_seniority")) or "Mid")
    location = _default_location(extracted)
    weeks = _term_weeks(start, end)
    hours_per_line = fte_hours * weeks

    lines = [
        StaffingLine(
            role=role,
            seniority=seniority,
            location=location,
            allocation_pct=Decimal("1"),
            hours_billable=hours_per_line,
            hourly_bill_rate=Decimal("0"),  # bill_rate resolved downstream
            provenance="calculated",
            start_date=start,
            end_date=end,
            warning=f"headcount from coverage_hours / {fte_hours} hpw",
        )
        for _ in range(headcount)
    ]
    return lines, [
        f"coverage={coverage} h/week ÷ {fte_hours} h/FTE/week → {headcount} FTE"
    ]


def _tm_lines(
    extracted: dict[str, Any],
    *,
    start: date | None,
    end: date | None,
) -> tuple[list[StaffingLine], list[str]]:
    """rate card × forecast utilization — one line per named role, defaulted."""

    resource_lines = _build_from_resource_table(
        extracted, start=start, end=end
    )
    if resource_lines:
        # Even though the resource table is present, T&M lines are
        # "defaulted" — the cap on hours implies a forecast, not a fixed
        # commitment. Downgrade the provenance.
        for line in resource_lines:
            line.provenance = "defaulted"
            line.warning = "T&M forecast — cap enforced by not-to-exceed"
        return resource_lines, ["T&M: forecast from stated resource table"]

    # Fall back to a single "Consultant" line sized to the term × utilization.
    fte_hours = _fte_hours_per_week(extracted)
    weeks = _term_weeks(start, end)
    hours = fte_hours * weeks * DEFAULT_FORECAST_UTILIZATION
    return (
        [
            StaffingLine(
                role="Consultant",
                seniority="Senior",
                location=_default_location(extracted),
                allocation_pct=Decimal("1"),
                hours_billable=hours,
                hourly_bill_rate=Decimal("0"),
                provenance="defaulted",
                start_date=start,
                end_date=end,
                warning="T&M forecast at 75% utilization",
            )
        ],
        ["T&M: no resource table; defaulted to 1 Consultant × 75% utilization"],
    )


async def _looked_up_lines(
    extracted: dict[str, Any],
    *,
    past_sow_search: PastSowSearch | None,
    capability_search: CapabilitySearch | None,
    start: date | None,
    end: date | None,
    engagement_type: str,
) -> tuple[list[StaffingLine], list[str], list[str]]:
    """Fixed-price + assessment: propose lines from past SOWs + capabilities."""

    query = _scope_query(extracted)
    sources: list[str] = []
    notes: list[str] = []
    lines: list[StaffingLine] = []

    past_hits: list[dict[str, Any]] = []
    if past_sow_search is not None and query:
        try:
            past_hits = await past_sow_search(query)
        except Exception:  # noqa: BLE001 — never block on retrieval outage
            past_hits = []

    for hit in past_hits[:3]:
        sid = str(hit.get("sow_version_id") or hit.get("id") or "")
        if sid:
            sources.append(sid)

    location = _default_location(extracted)
    weeks = _term_weeks(start, end)
    # Assessment default: 2-3 people × 4 weeks. Fixed-price: 3 people
    # sized to the term. Bill rate stays at 0 — resolver fills at save.
    # No evidence → propose nothing, and say why.
    #
    # This used to emit a hardcoded roster (Architect/Engineer/Engineer, or
    # Consultant/Analyst/Architect for an assessment) at a default hours
    # figure, a ZERO bill rate and today+90d dates, with an empty `warnings`
    # list. For a SOW with no resource table that produced a complete-looking
    # staffing plan in which every number was invented — and a gross margin
    # computed from it, with nothing to tell Finance the inputs were made up.
    #
    # CLAUDE.md rule 6: AI output is a draft *with sources*. A guess with no
    # source is not a draft, it is a fabrication. sow-first-principles §7:
    # "fallbacks are loud". An empty grid the human fills in is honest; an
    # invented one is not.
    if not past_hits:
        notes.append(
            f"{engagement_type}: the SOW lists no resources and no approved "
            "past SOW matched this scope — staffing must be entered or "
            "uploaded before a gross margin can be calculated"
        )
        if capability_search is not None and query:
            try:
                cap_hits = await capability_search(query)
                if cap_hits:
                    notes.append(
                        f"{engagement_type}: {len(cap_hits)} capability catalog "
                        "match(es) available as a starting point"
                    )
            except Exception:  # noqa: BLE001 — never block on retrieval outage
                pass
        return [], notes, sources

    if engagement_type == "assessment":
        roster = [("Consultant", "Senior"), ("Analyst", "Mid"), ("Architect", "Principal")]
        hours_per_person = _fte_hours_per_week(extracted) * min(weeks, Decimal("4"))
    else:
        roster = [
            ("Architect", "Principal"),
            ("Engineer", "Senior"),
            ("Engineer", "Mid"),
        ]
        hours_per_person = _fte_hours_per_week(extracted) * weeks

    for role, seniority in roster:
        lines.append(
            StaffingLine(
                role=role,
                seniority=seniority,
                location=location,
                allocation_pct=Decimal("1"),
                hours_billable=hours_per_person,
                hourly_bill_rate=Decimal("0"),
                provenance="looked_up",
                start_date=start,
                end_date=end,
                source_id=sources[0] if sources else None,
                warning="estimated from past SOW — confirm hours and rates",
            )
        )

    notes.append(f"{engagement_type}: {len(past_hits)} past SOW(s) matched scope")
    return lines, notes, sources


# --- public API ------------------------------------------------------------


async def staff(
    engagement_type: str,
    extracted: dict[str, Any] | None,
    *,
    past_sow_search: PastSowSearch | None = None,
    capability_search: CapabilitySearch | None = None,
) -> AutoStaffingResult:
    """Return the proposed staffing grid for one engagement type.

    ``past_sow_search`` / ``capability_search`` are async callables; the
    caller wires them from :mod:`app.services.embeddings`. Tests pass
    stubs that return canned hits.
    """

    extracted = extracted or {}
    start, end = _term_dates(extracted)
    warnings: list[str] = []

    if engagement_type in ("staff_aug", "single_resource"):
        lines = _build_from_resource_table(extracted, start=start, end=end)
        notes: list[str] = []
        sources: list[str] = []
        if not lines:
            warnings.append(
                f"{engagement_type}: SOW resource table missing — cannot auto-staff"
            )
    elif engagement_type == "managed_service":
        lines, notes = _managed_service_lines(extracted, start=start, end=end)
        sources = []
    elif engagement_type == "tm":
        lines, notes = _tm_lines(extracted, start=start, end=end)
        sources = []
    elif engagement_type in ("fixed_price", "assessment"):
        lines, notes, sources = await _looked_up_lines(
            extracted,
            past_sow_search=past_sow_search,
            capability_search=capability_search,
            start=start,
            end=end,
            engagement_type=engagement_type,
        )
    elif engagement_type == "permanent_placement":
        # Not a staffed engagement — the placement fee is invoiced once.
        lines = []
        notes = ["permanent_placement: no staffing required (single placement fee)"]
        sources = []
    else:
        raise ValueError(f"unknown engagement_type {engagement_type!r}")

    return AutoStaffingResult(
        lines=lines, notes=notes, warnings=warnings, sources=sources
    )


def lines_to_payload_dicts(lines: Iterable[StaffingLine]) -> list[dict[str, Any]]:
    """Translate proposed lines into ``ResourceLinePayload`` dict shape.

    The delivery-model parser wants ISO date strings + Decimal strings —
    matching :func:`app.services.delivery_model.parse_resource_line`.
    """

    today = date.today()
    default_end = today + timedelta(days=90)
    out: list[dict[str, Any]] = []
    for line in lines:
        out.append(
            {
                "role": line.role,
                "seniority": line.seniority,
                "location": line.location,
                "allocation_pct": format(line.allocation_pct, "f"),
                "start_date": (line.start_date or today).isoformat(),
                "end_date": (line.end_date or default_end).isoformat(),
                "hours_billable": format(line.hours_billable, "f"),
                "hourly_bill_rate": format(line.hourly_bill_rate, "f"),
                # bill_rate_source + cost_band_source live in the metadata
                # audit — the parser dataclass doesn't carry them yet.
            }
        )
    return out


__all__ = [
    "AutoStaffingResult",
    "DEFAULT_FTE_HOURS_PER_WEEK",
    "DEFAULT_FORECAST_UTILIZATION",
    "StaffingLine",
    "lines_to_payload_dicts",
    "staff",
]
