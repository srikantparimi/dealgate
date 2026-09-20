"""Delivery Model Builder service (S3 E6).

The router stays thin: parse, dispatch, respond. Every state change lands
here so:

  * ``create_gm_model_version`` is the single write path — one immutable
    :class:`~app.models.gm_model.GmModel` version + N ``resource_line`` +
    M ``cost_line`` rows in one transaction, with a ``gm_model.created``
    audit row appended (CLAUDE.md rule 5).
  * ``compute_live`` translates the Builder's payload into the ratified
    :func:`app.gm.compute` inputs and returns the resulting numbers. It
    never touches the DB — the Builder calls it on every keystroke.
  * ``capacity_conflicts`` and ``hr_lead_time_warnings`` are pure warnings
    the panel renders inline; they never block a save (Delivery may
    acknowledge and proceed per the story).

Every money field is Decimal (CLAUDE.md rule 2). Missing ``hourly_cost``
propagates as "unvalidated" — blueprint §2 forbids treating a gap as zero.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.gm import compute as gm_compute
from app.gm.core import min_price as gm_min_price
from app.gm.policy import INDIA_FLOOR, US_FLOOR, check_floors
from app.gm.types import (
    CostLine as GmCostLine,
    ResourceLine as GmResourceLine,
    TemplateResult,
)
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.models.gm_model_phase import GmModelPhase
from app.models.gm_model_template import GmModelTemplate
from app.services.gm_sandbox import (
    SandboxInputError,
    parse_engagement_type,
    parse_inputs,
)
from app.services.client_rate_cards import ResolvedBillRate, resolve_bill_rate
from app.services.rate_cards import CostBand, active_rate_card, lookup_cost

# --- exceptions ------------------------------------------------------------


class DeliveryModelInputError(ValueError):
    """422-worthy payload problem. The router turns this into HTTPException."""


# --- HR config -------------------------------------------------------------


@dataclass(frozen=True)
class HrConfig:
    """Minimal HR knobs the story needs.

    ``lead_time_days`` is the number of working days HR needs between the
    "to hire" flag going up and a body actually starting billable work.
    Sprint 3 keeps this as a static blueprint constant; the S4 admin UI
    will publish per-role overrides.
    """

    lead_time_days: int = 45


DEFAULT_HR_CONFIG = HrConfig()


# --- payload dataclasses ---------------------------------------------------


@dataclass(frozen=True)
class ResourceLinePayload:
    role: str
    seniority: str
    location: str
    person_name: Optional[str]
    allocation_pct: Decimal
    start_date: date
    end_date: date
    hours_billable: Decimal
    hourly_bill_rate: Decimal
    hourly_cost: Optional[Decimal]
    validated_by: Optional[uuid.UUID]
    # S7 wave 2: soft-link to a WBS phase by name during save. The service
    # resolves ``phase_name`` -> the freshly-created gm_model_phase.id.
    # NULL keeps the row in the Builder's "Ungrouped" bucket (legacy-safe).
    phase_name: Optional[str] = None


@dataclass(frozen=True)
class CostLinePayload:
    category: str
    amount: Decimal
    note: Optional[str]
    location: str = "US"
    phase_name: Optional[str] = None


@dataclass(frozen=True)
class PhaseInput:
    """One WBS phase for the save-time payload (S7 wave 2).

    ``order`` is the display position — the service normalises it to a
    dense 0..N sequence before persist so the UNIQUE(gm_model_id, order)
    constraint holds even when the client sends sparse values.
    """

    name: str
    order: int
    sow_deliverable_ref: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class GmModelPayload:
    engagement_type: str
    sow_version_id: Optional[uuid.UUID]
    delivery_pattern: Optional[str]
    contingency_pct: Optional[Decimal]
    warranty_days: Optional[int]
    resource_lines: list[ResourceLinePayload]
    cost_lines: list[CostLinePayload]
    phases: list[PhaseInput] = None  # type: ignore[assignment]
    # The agreed fee, for engagements where revenue is settled rather than
    # billed by the hour. Optional: T&M and staff aug derive revenue from
    # bill rate x hours and leave this None.
    total_price: Optional[Decimal] = None

    def __post_init__(self):  # dataclass frozen shim
        if self.phases is None:
            object.__setattr__(self, "phases", [])


# --- parsing helpers -------------------------------------------------------

_ALLOWED_LOCATIONS = frozenset({"US", "India"})
_ALLOWED_COST_CATEGORIES = frozenset({"tools", "travel", "subcontractor", "other"})


def _to_decimal(value: Any, *, field: str) -> Decimal:
    if value is None:
        raise DeliveryModelInputError(f"{field} is required")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DeliveryModelInputError(f"{field} is not a valid number: {value!r}") from exc


def _to_optional_decimal(value: Any, *, field: str) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return _to_decimal(value, field=field)


def _to_date(value: Any, *, field: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise DeliveryModelInputError(f"{field} must be an ISO date string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DeliveryModelInputError(f"{field} is not an ISO date: {value!r}") from exc


def _to_optional_uuid(value: Any, *, field: str) -> Optional[uuid.UUID]:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise DeliveryModelInputError(f"{field} is not a UUID: {value!r}") from exc


def parse_resource_line(raw: Any, *, field: str) -> ResourceLinePayload:
    if not isinstance(raw, dict):
        raise DeliveryModelInputError(f"{field} must be an object")
    location = raw.get("location")
    if location not in _ALLOWED_LOCATIONS:
        raise DeliveryModelInputError(f"{field}.location must be 'US' or 'India'")
    person_name = raw.get("person_name")
    if person_name is not None:
        person_name = str(person_name).strip() or None
    phase_name = raw.get("phase_name")
    if phase_name is not None:
        phase_name = str(phase_name).strip() or None
    return ResourceLinePayload(
        role=str(raw.get("role", "")).strip(),
        seniority=str(raw.get("seniority", "")).strip(),
        location=location,
        person_name=person_name,
        allocation_pct=_to_decimal(raw.get("allocation_pct", "1"), field=f"{field}.allocation_pct"),
        start_date=_to_date(raw.get("start_date"), field=f"{field}.start_date"),
        end_date=_to_date(raw.get("end_date"), field=f"{field}.end_date"),
        hours_billable=_to_decimal(
            raw.get("hours_billable", 0), field=f"{field}.hours_billable"
        ),
        hourly_bill_rate=_to_decimal(
            raw.get("hourly_bill_rate", 0), field=f"{field}.hourly_bill_rate"
        ),
        hourly_cost=_to_optional_decimal(
            raw.get("hourly_cost"), field=f"{field}.hourly_cost"
        ),
        validated_by=_to_optional_uuid(raw.get("validated_by"), field=f"{field}.validated_by"),
        phase_name=phase_name,
    )


def parse_cost_line(raw: Any, *, field: str) -> CostLinePayload:
    if not isinstance(raw, dict):
        raise DeliveryModelInputError(f"{field} must be an object")
    category = raw.get("category")
    if category not in _ALLOWED_COST_CATEGORIES:
        raise DeliveryModelInputError(
            f"{field}.category must be one of tools/travel/subcontractor/other"
        )
    location = raw.get("location", "US")
    if location not in _ALLOWED_LOCATIONS:
        raise DeliveryModelInputError(f"{field}.location must be 'US' or 'India'")
    phase_name = raw.get("phase_name")
    if phase_name is not None:
        phase_name = str(phase_name).strip() or None
    return CostLinePayload(
        category=category,
        amount=_to_decimal(raw.get("amount", 0), field=f"{field}.amount"),
        note=(str(raw["note"]) if raw.get("note") else None),
        location=location,
        phase_name=phase_name,
    )


def parse_phase(raw: Any, *, field: str) -> PhaseInput:
    if not isinstance(raw, dict):
        raise DeliveryModelInputError(f"{field} must be an object")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise DeliveryModelInputError(f"{field}.name is required")
    try:
        order = int(raw.get("order", 0))
    except (TypeError, ValueError) as exc:
        raise DeliveryModelInputError(f"{field}.order must be an integer") from exc
    ref = raw.get("sow_deliverable_ref")
    if ref is not None:
        ref = str(ref).strip() or None
    desc = raw.get("description")
    if desc is not None:
        desc = str(desc).strip() or None
    return PhaseInput(
        name=name, order=order, sow_deliverable_ref=ref, description=desc
    )


def parse_gm_model_payload(raw: Any) -> GmModelPayload:
    if not isinstance(raw, dict):
        raise DeliveryModelInputError("payload must be an object")
    engagement_type = raw.get("engagement_type")
    if not isinstance(engagement_type, str) or not engagement_type:
        raise DeliveryModelInputError("engagement_type is required")
    # Validate against the ratified enum without importing the enum here —
    # parse_engagement_type raises SandboxInputError we translate.
    try:
        parse_engagement_type(engagement_type)
    except SandboxInputError as exc:
        raise DeliveryModelInputError(str(exc)) from exc

    resources_raw = raw.get("resource_lines") or []
    if not isinstance(resources_raw, list):
        raise DeliveryModelInputError("resource_lines must be a list")
    resources = [
        parse_resource_line(r, field=f"resource_lines[{i}]")
        for i, r in enumerate(resources_raw)
    ]

    costs_raw = raw.get("cost_lines") or []
    if not isinstance(costs_raw, list):
        raise DeliveryModelInputError("cost_lines must be a list")
    costs = [parse_cost_line(c, field=f"cost_lines[{i}]") for i, c in enumerate(costs_raw)]

    phases_raw = raw.get("phases") or []
    if not isinstance(phases_raw, list):
        raise DeliveryModelInputError("phases must be a list")
    phases = [parse_phase(p, field=f"phases[{i}]") for i, p in enumerate(phases_raw)]

    return GmModelPayload(
        engagement_type=engagement_type,
        sow_version_id=_to_optional_uuid(raw.get("sow_version_id"), field="sow_version_id"),
        delivery_pattern=(
            str(raw["delivery_pattern"]) if raw.get("delivery_pattern") else None
        ),
        contingency_pct=_to_optional_decimal(
            raw.get("contingency_pct"), field="contingency_pct"
        ),
        warranty_days=(int(raw["warranty_days"]) if raw.get("warranty_days") is not None else None),
        resource_lines=resources,
        cost_lines=costs,
        phases=phases,
        total_price=_to_optional_decimal(raw.get('total_price'), field='total_price'),
    )


# --- rate-card lookup ------------------------------------------------------


async def _cost_band_for(
    session: AsyncSession, line: ResourceLinePayload
) -> Optional[CostBand]:
    """Return the cost band for a resource, or ``None`` when unpriced.

    Uses whichever rate card is active as of ``today``. Missing rate card
    (no version at all) collapses to ``None`` — the caller decides whether
    to error or mark the sheet incomplete. See ``services/rate_cards.py``.
    """

    card = await active_rate_card(session)
    if card is None:
        return None
    return lookup_cost(line.role, line.seniority, line.location, card)


async def _client_id_for(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Optional[uuid.UUID]:
    """Return the ``client_id`` on the opportunity, or ``None``."""

    from app.models.opportunity import Opportunity

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        return None
    return opp.client_id


async def _resolve_bill_rate_for(
    session: AsyncSession,
    *,
    client_id: Optional[uuid.UUID],
    line: ResourceLinePayload,
) -> ResolvedBillRate:
    """Resolve a bill rate for a resource line via the client card ladder.

    Wraps :func:`app.services.client_rate_cards.resolve_bill_rate` so the
    Builder gets a single "one call, one answer" surface.
    """

    return await resolve_bill_rate(
        session,
        client_id=client_id,
        role=line.role,
        seniority=line.seniority,
        location=line.location,
        sow_stated=(
            line.hourly_bill_rate if line.hourly_bill_rate and line.hourly_bill_rate > 0 else None
        ),
    )


# --- pure computation ------------------------------------------------------


def _payload_to_compute_inputs(payload: GmModelPayload) -> dict:
    """Translate the Builder payload into the sandbox inputs dict.

    The sandbox parsers already know how to speak GM library dataclasses;
    reusing them keeps the two math paths in lock-step (blueprint §2 —
    all math flows through app.gm).
    """
    resources = [
        {
            "role": r.role,
            "seniority": r.seniority,
            "location": r.location,
            "allocation_pct": format(r.allocation_pct, "f"),
            "start": r.start_date.isoformat(),
            "end": r.end_date.isoformat(),
            "hours_billable": format(r.hours_billable, "f"),
            "hourly_bill_rate": format(r.hourly_bill_rate, "f"),
            **(
                {"hourly_cost": format(r.hourly_cost, "f")}
                if r.hourly_cost is not None
                else {}
            ),
        }
        for r in payload.resource_lines
    ]
    costs = [
        {
            "category": c.category,
            "amount": format(c.amount, "f"),
            "location": c.location,
            "note": c.note or "",
        }
        for c in payload.cost_lines
    ]
    # Fixed-price / assessment / managed_service require explicit revenue
    # allocation and cannot use the resource lines for revenue. For those
    # types the Builder's `total_price` / `revenue_us` / `revenue_india`
    # come in as top-level fields (not resource_lines) — we forward them
    # via a raw dict passthrough.
    return {"resources": resources, "costs": costs}


def compute_live(payload: GmModelPayload, *, extra_inputs: Optional[dict] = None) -> TemplateResult:
    """Pure preview. No I/O. Delegates to :func:`app.gm.compute`."""

    engagement = parse_engagement_type(payload.engagement_type)
    inputs = _payload_to_compute_inputs(payload)
    if extra_inputs:
        inputs.update(extra_inputs)
    try:
        parsed = parse_inputs(engagement, inputs)
    except SandboxInputError as exc:
        raise DeliveryModelInputError(str(exc)) from exc
    return gm_compute(engagement, parsed)


# --- capacity + HR warnings -----------------------------------------------


@dataclass(frozen=True)
class ResourceWarning:
    index: int
    severity: str  # "amber" | "red"
    code: str
    message: str


async def capacity_conflicts(
    session: AsyncSession,
    resource_lines: Iterable[ResourceLinePayload],
    *,
    exclude_gm_model_id: Optional[uuid.UUID] = None,
) -> list[ResourceWarning]:
    """Amber warning per line where the named person overlaps another gm_model.

    Overlap is date-range intersection on ``[start_date, end_date]``. Rows
    with ``person_name is None`` ("to hire") are skipped — those are covered
    by :func:`hr_lead_time_warnings`.
    """

    warnings: list[ResourceWarning] = []
    for idx, line in enumerate(resource_lines):
        if not line.person_name:
            continue
        stmt = select(ResourceLine).where(
            ResourceLine.person_name == line.person_name,
            ResourceLine.start_date <= line.end_date,
            ResourceLine.end_date >= line.start_date,
        )
        if exclude_gm_model_id is not None:
            stmt = stmt.where(ResourceLine.gm_model_id != exclude_gm_model_id)
        others = (await session.execute(stmt)).scalars().all()
        if not others:
            continue
        # Only warn when combined allocation would exceed 100%.
        overlap_pct = sum(
            (o.allocation_pct or Decimal("0")) for o in others
        ) + line.allocation_pct
        if overlap_pct > Decimal("1"):
            warnings.append(
                ResourceWarning(
                    index=idx,
                    severity="amber",
                    code="capacity_conflict",
                    message=(
                        f"{line.person_name} would be allocated "
                        f"{overlap_pct * 100:.0f}% across overlapping engagements "
                        f"(this row + {len(others)} other)."
                    ),
                )
            )
    return warnings


def hr_lead_time_warnings(
    resource_lines: Iterable[ResourceLinePayload],
    hr_config: HrConfig = DEFAULT_HR_CONFIG,
    *,
    today: Optional[date] = None,
) -> list[ResourceWarning]:
    """Red warning per "to hire" line starting before ``today + lead_time_days``."""

    reference = today or date.today()
    warnings: list[ResourceWarning] = []
    for idx, line in enumerate(resource_lines):
        if line.person_name:
            continue
        days_out = (line.start_date - reference).days
        if days_out < hr_config.lead_time_days:
            warnings.append(
                ResourceWarning(
                    index=idx,
                    severity="red",
                    code="hr_lead_time",
                    message=(
                        f"To-hire {line.role} / {line.seniority} starts in "
                        f"{days_out} day(s); HR needs {hr_config.lead_time_days}."
                    ),
                )
            )
    return warnings


# --- completeness check ----------------------------------------------------


def resource_completeness_issues(
    resource_lines: Iterable[ResourceLinePayload],
) -> list[str]:
    """Return a list of missing-piece descriptions per resource line.

    Governance advances from Intake → GMBuild.complete only when every line
    has location, effort, bill_rate and a validated cost. Workflow module
    (Sprint 4) owns the actual transition; this helper is the criterion.
    """

    issues: list[str] = []
    for idx, r in enumerate(resource_lines):
        if r.location not in _ALLOWED_LOCATIONS:
            issues.append(f"resource_lines[{idx}].location")
        if r.hours_billable is None or r.hours_billable <= 0:
            issues.append(f"resource_lines[{idx}].hours_billable")
        if r.hourly_bill_rate is None or r.hourly_bill_rate <= 0:
            issues.append(f"resource_lines[{idx}].hourly_bill_rate")
        if r.hourly_cost is None:
            issues.append(f"resource_lines[{idx}].hourly_cost")
        if r.validated_by is None:
            issues.append(f"resource_lines[{idx}].validated_by")
    return issues


# --- persist ---------------------------------------------------------------


async def create_gm_model_version(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    actor_id: Optional[uuid.UUID],
    payload: GmModelPayload,
) -> GmModel:
    """Create one immutable GM model version + its child rows + audit row.

    Missing costs are filled from the active rate card's base band when the
    payload does not supply a value — the caller's explicit ``hourly_cost``
    always wins. If neither is available the line lands with ``hourly_cost``
    NULL and the sheet is flagged incomplete on read (see
    :func:`resource_completeness_issues`).
    """

    if not payload.resource_lines:
        raise DeliveryModelInputError("resource_lines must not be empty")

    # Look up the deal's client so ``resolve_bill_rate`` can pull the
    # client rate card. ``None`` collapses the resolver to the loud
    # "company default" fallback path (S9 wave 1).
    client_id = await _client_id_for(session, opportunity_id)

    # Pre-fill missing costs from the rate card, and missing bill rates
    # via the client rate card (S9 wave 1). Explicit caller values always
    # win — this only fills gaps.
    filled_lines: list[ResourceLinePayload] = []
    for line in payload.resource_lines:
        # Resolve bill rate when the caller sent zero/None.
        resolved_bill = line.hourly_bill_rate
        if not resolved_bill or resolved_bill <= 0:
            r = await _resolve_bill_rate_for(
                session, client_id=client_id, line=line
            )
            if r.rate is not None:
                resolved_bill = r.rate

        # Resolve cost band when the caller sent no cost.
        cost = line.hourly_cost
        if cost is None:
            band = await _cost_band_for(session, line)
            if band is not None:
                cost = band.base

        if resolved_bill == line.hourly_bill_rate and cost == line.hourly_cost:
            filled_lines.append(line)
            continue
        filled_lines.append(
            ResourceLinePayload(
                role=line.role,
                seniority=line.seniority,
                location=line.location,
                person_name=line.person_name,
                allocation_pct=line.allocation_pct,
                start_date=line.start_date,
                end_date=line.end_date,
                hours_billable=line.hours_billable,
                hourly_bill_rate=resolved_bill,
                hourly_cost=cost,
                validated_by=line.validated_by,
                phase_name=line.phase_name,
            )
        )

    filled_payload = GmModelPayload(
        engagement_type=payload.engagement_type,
        sow_version_id=payload.sow_version_id,
        delivery_pattern=payload.delivery_pattern,
        contingency_pct=payload.contingency_pct,
        warranty_days=payload.warranty_days,
        resource_lines=filled_lines,
        cost_lines=payload.cost_lines,
        phases=payload.phases,
    )

    # Snapshot revenue components at save-time so the list view does not
    # have to re-run the GM engine on read.
    #
    # How revenue is earned depends on the engagement, and this used to
    # assume one shape for all of them: bill rate x hours x allocation, which
    # is right for T&M and staff aug and wrong for a fixed fee. On a
    # fixed-price SOW the revenue is the agreed fee whatever the hours turn
    # out to be — that is what "fixed" means — so computing it from bill
    # rates produced a number unrelated to the contract, and zero whenever
    # the bill rates were left blank (which is reasonable to do on a fixed
    # fee, since nobody is billing by the hour).
    if payload.engagement_type in ("fixed_price", "assessment") and (
        payload.total_price is not None and payload.total_price > 0
    ):
        revenue_us, revenue_india, _alloc_notes = allocate_fixed_fee_revenue(
            filled_lines, payload.total_price
        )
    else:
        revenue_us = Decimal("0")
        revenue_india = Decimal("0")
        for r in filled_lines:
            rev = r.hours_billable * r.hourly_bill_rate * r.allocation_pct
            if r.location == "US":
                revenue_us += rev
            else:
                revenue_india += rev

    model = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opportunity_id,
        sow_version_id=filled_payload.sow_version_id,
        engagement_type=filled_payload.engagement_type,
        delivery_pattern=filled_payload.delivery_pattern,
        contingency_pct=filled_payload.contingency_pct,
        warranty_days=filled_payload.warranty_days,
        revenue_us=revenue_us,
        revenue_india=revenue_india,
        created_by=actor_id,
    )
    session.add(model)
    await session.flush()

    # ---- WBS phases (S7 wave 2) ------------------------------------------
    # Persist phases first so we can resolve resource/cost ``phase_name``
    # -> the freshly-created gm_model_phase.id. Order is normalised to a
    # dense 0..N sequence so the UNIQUE constraint holds even when the
    # client sent sparse or duplicate order values.
    phases_sorted = sorted(
        filled_payload.phases, key=lambda p: (p.order, p.name)
    )
    phase_ids_by_name: dict[str, uuid.UUID] = {}
    for pos, ph in enumerate(phases_sorted):
        row = GmModelPhase(
            id=uuid.uuid4(),
            gm_model_id=model.id,
            name=ph.name,
            order=pos,
            sow_deliverable_ref=ph.sow_deliverable_ref,
            description=ph.description,
        )
        session.add(row)
        # First occurrence wins if two phases share a name (unlikely, but
        # keeps the lookup deterministic).
        phase_ids_by_name.setdefault(ph.name, row.id)
    if phases_sorted:
        await session.flush()

    # Stamp created_at with a monotonic sub-millisecond offset per line so
    # ``resource_lines`` come back in insertion order regardless of clock
    # granularity (the ORM sorts by created_at + id in the relationship).
    from datetime import timedelta

    base_ts = datetime.now(timezone.utc)
    for offset, r in enumerate(filled_lines):
        session.add(
            ResourceLine(
                id=uuid.uuid4(),
                gm_model_id=model.id,
                role=r.role,
                seniority=r.seniority,
                location=r.location,
                person_name=r.person_name,
                allocation_pct=r.allocation_pct,
                start_date=r.start_date,
                end_date=r.end_date,
                billable_hours=r.hours_billable,
                hourly_bill_rate=r.hourly_bill_rate,
                # Legacy NOT NULL column: mirror hourly_cost, or 0 as a
                # placeholder when unvalidated. The real "did we know?"
                # signal is the nullable ``hourly_cost`` field.
                hourly_loaded_cost=(r.hourly_cost or Decimal("0")),
                hourly_cost=r.hourly_cost,
                validated_by=r.validated_by,
                created_at=base_ts + timedelta(microseconds=offset),
                phase_id=phase_ids_by_name.get(r.phase_name) if r.phase_name else None,
            )
        )
    for c in filled_payload.cost_lines:
        session.add(
            CostLine(
                id=uuid.uuid4(),
                gm_model_id=model.id,
                category=c.category,
                amount=c.amount,
                note=c.note,
                location=c.location,
                phase_id=phase_ids_by_name.get(c.phase_name) if c.phase_name else None,
            )
        )

    await append_audit(
        session,
        actor_id=actor_id,
        action="gm_model.created",
        entity="gm_model",
        entity_id=str(model.id),
        before=None,
        after={
            "opportunity_id": str(opportunity_id),
            "sow_version_id": (
                str(filled_payload.sow_version_id) if filled_payload.sow_version_id else None
            ),
            "engagement_type": filled_payload.engagement_type,
            "resource_line_count": len(filled_lines),
            "cost_line_count": len(filled_payload.cost_lines),
            "phase_count": len(phases_sorted),
            "revenue_us": format(revenue_us, "f"),
            "revenue_india": format(revenue_india, "f"),
        },
    )

    # S4 E7 hook: a new gm_model version voids the active approval package
    # (change-voids-approval). Behind a single hook module so this service
    # has no direct dependency on the approvals package.
    from app.services.approvals_hooks import on_gm_model_created

    await on_gm_model_created(
        session,
        opportunity_id=opportunity_id,
        new_gm_model_id=model.id,
        actor_id=actor_id,
    )

    await session.commit()

    return await load_gm_model(session, model.id)


async def load_gm_model(session: AsyncSession, gm_model_id: uuid.UUID) -> GmModel:
    stmt = (
        select(GmModel)
        .options(
            selectinload(GmModel.resource_lines),
            selectinload(GmModel.cost_lines),
            selectinload(GmModel.phases),
        )
        .where(GmModel.id == gm_model_id)
    )
    return (await session.execute(stmt)).scalar_one()


async def latest_gm_model_for(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Optional[GmModel]:
    stmt = (
        select(GmModel)
        .options(
            selectinload(GmModel.resource_lines),
            selectinload(GmModel.cost_lines),
            selectinload(GmModel.phases),
        )
        .where(GmModel.opportunity_id == opportunity_id)
        .order_by(GmModel.created_at.desc(), GmModel.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_gm_models_for(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> list[GmModel]:
    stmt = (
        select(GmModel)
        .options(
            selectinload(GmModel.resource_lines),
            selectinload(GmModel.cost_lines),
            selectinload(GmModel.phases),
        )
        .where(GmModel.opportunity_id == opportunity_id)
        .order_by(GmModel.created_at.desc(), GmModel.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


# --- serialisation ---------------------------------------------------------


def _fmt(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value, "f")


def _resource_line_to_gm_type(r: ResourceLine) -> GmResourceLine:
    return GmResourceLine(
        role=r.role,
        seniority=r.seniority,
        location=r.location,  # type: ignore[arg-type]
        allocation_pct=r.allocation_pct,
        start=r.start_date,
        end=r.end_date,
        hours_billable=r.billable_hours,
        hourly_bill_rate=r.hourly_bill_rate,
        hourly_cost=r.hourly_cost,
    )


def _cost_line_to_gm_type(c: CostLine) -> GmCostLine:
    return GmCostLine(
        category=c.category,  # type: ignore[arg-type]
        amount=c.amount,
        note=c.note or "",
        location=c.location,  # type: ignore[arg-type]
    )


def _model_to_payload(model: GmModel) -> GmModelPayload:
    """Round-trip a persisted model back into a payload the compute path
    consumes. Used by the read endpoint's ``computed`` field and by xlsx
    export so the download always reflects the stored numbers, never
    a re-derivation from a different code path."""

    resources = [
        ResourceLinePayload(
            role=r.role,
            seniority=r.seniority,
            location=r.location,
            person_name=r.person_name,
            allocation_pct=r.allocation_pct,
            start_date=r.start_date,
            end_date=r.end_date,
            hours_billable=r.billable_hours,
            hourly_bill_rate=r.hourly_bill_rate,
            hourly_cost=r.hourly_cost,
            validated_by=r.validated_by,
        )
        for r in model.resource_lines
    ]
    costs = [
        CostLinePayload(
            category=c.category,
            amount=c.amount,
            note=c.note,
            location=c.location,
        )
        for c in model.cost_lines
    ]
    return GmModelPayload(
        engagement_type=model.engagement_type,
        sow_version_id=model.sow_version_id,
        delivery_pattern=model.delivery_pattern,
        contingency_pct=model.contingency_pct,
        warranty_days=model.warranty_days,
        resource_lines=resources,
        cost_lines=costs,
    )


def _extra_inputs_for_model(model: GmModel) -> dict:
    """Rebuild the top-level template inputs (total_price, revenue split,
    term_months, ...) that :func:`compute_live` needs but that don't live
    on the ORM. For fixed_price / assessment we use the stored snapshot
    ``revenue_us`` / ``revenue_india`` (writing the same numbers back
    keeps ``compute`` in agreement with the save-time snapshot)."""

    et = model.engagement_type
    if et in ("fixed_price", "assessment"):
        return {
            "total_price": format(
                (model.revenue_us or Decimal("0")) + (model.revenue_india or Decimal("0")),
                "f",
            ),
            "revenue_us": format(model.revenue_us or Decimal("0"), "f"),
            "revenue_india": format(model.revenue_india or Decimal("0"), "f"),
            # Assessment requires a deliverable string; empty string keeps
            # the parser happy without inventing content.
            **({"deliverable": "(persisted)"} if et == "assessment" else {}),
        }
    if et == "managed_service":
        return {
            "monthly_fee_us": format(model.revenue_us or Decimal("0"), "f"),
            "monthly_fee_india": format(model.revenue_india or Decimal("0"), "f"),
            "term_months": "1",
        }
    return {}


def serialize_resource_line(r: ResourceLine) -> dict:
    return {
        "id": str(r.id),
        "role": r.role,
        "seniority": r.seniority,
        "location": r.location,
        "person_name": r.person_name,
        "allocation_pct": _fmt(r.allocation_pct),
        "start_date": r.start_date.isoformat(),
        "end_date": r.end_date.isoformat(),
        "hours_billable": _fmt(r.billable_hours),
        "hourly_bill_rate": _fmt(r.hourly_bill_rate),
        "hourly_cost": _fmt(r.hourly_cost),
        "validated_by": str(r.validated_by) if r.validated_by else None,
        "phase_id": str(r.phase_id) if getattr(r, "phase_id", None) else None,
    }


def serialize_cost_line(c: CostLine) -> dict:
    return {
        "id": str(c.id),
        "category": c.category,
        "amount": _fmt(c.amount),
        "note": c.note,
        "location": c.location,
        "phase_id": str(c.phase_id) if getattr(c, "phase_id", None) else None,
    }


def serialize_phase(p: GmModelPhase) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "order": p.order,
        "sow_deliverable_ref": p.sow_deliverable_ref,
        "description": p.description,
    }


def build_compute_response(result: TemplateResult) -> dict:
    """Format a ``TemplateResult`` for the JSON API. Mirrors the sandbox
    shape (minus the policy-lookup fields) so the Builder can reuse the
    same rendering code path."""

    us_present = result.revenue_us > 0
    india_present = result.revenue_india > 0
    us_pass = True
    india_pass = True
    failing: list[str] = []
    if us_present:
        us_pass = result.gm_us is not None and result.gm_us >= US_FLOOR
        if not us_pass:
            failing.append("US")
    if india_present:
        india_pass = result.gm_india is not None and result.gm_india >= INDIA_FLOOR
        if not india_pass:
            failing.append("India")
    requires_ceo = bool(failing) or not result.complete
    floors = check_floors(result)  # sanity — same shape.
    _ = floors  # kept for future policy-version pass-through.

    min_price_us = gm_min_price(result.cost_us, US_FLOOR) if result.cost_us > 0 else None
    min_price_india = (
        gm_min_price(result.cost_india, INDIA_FLOOR) if result.cost_india > 0 else None
    )

    return {
        "revenue_us": _fmt(result.revenue_us),
        "cost_us": _fmt(result.cost_us),
        "gm_us": _fmt(result.gm_us),
        "revenue_india": _fmt(result.revenue_india),
        "cost_india": _fmt(result.cost_india),
        "gm_india": _fmt(result.gm_india),
        "gm_blended": _fmt(result.gm_blended),
        "geography": result.geography,
        "complete": result.complete,
        "missing": list(result.missing),
        "min_price_us": _fmt(min_price_us),
        "min_price_india": _fmt(min_price_india),
        "policy": {
            "us_floor": _fmt(US_FLOOR),
            "india_floor": _fmt(INDIA_FLOOR),
            "us_pass": us_pass,
            "india_pass": india_pass,
            "requires_ceo": requires_ceo,
            "failing": failing,
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def serialize_warnings(warnings: Iterable[ResourceWarning]) -> list[dict]:
    return [
        {
            "index": w.index,
            "severity": w.severity,
            "code": w.code,
            "message": w.message,
        }
        for w in warnings
    ]


def _phase_summary(model: GmModel) -> list[dict]:
    """Per-phase revenue + cost totals for the right-panel widget.

    Sum revenue as ``bill_rate * hours * allocation`` (same shape as the
    top-level snapshot); sum cost as ``hourly_cost * hours * allocation``
    when a validated cost exists, otherwise ``0`` — the completeness
    banner already flags missing costs so we don't double-warn here.
    Non-labor cost_lines add to the same phase bucket.
    Rows with ``phase_id == None`` roll up under "Ungrouped".
    """

    phases = getattr(model, "phases", []) or []
    buckets: dict[str | None, dict[str, Any]] = {}
    for p in phases:
        buckets[str(p.id)] = {
            "phase_id": str(p.id),
            "name": p.name,
            "order": p.order,
            "revenue": Decimal("0"),
            "cost": Decimal("0"),
        }
    # "Ungrouped" bucket for legacy rows / phase-less models.
    UNGROUPED = "__ungrouped__"
    buckets[UNGROUPED] = {
        "phase_id": None,
        "name": "Ungrouped",
        "order": 10_000,
        "revenue": Decimal("0"),
        "cost": Decimal("0"),
    }

    for r in model.resource_lines:
        key = str(r.phase_id) if getattr(r, "phase_id", None) else UNGROUPED
        b = buckets.get(key)
        if b is None:
            continue
        alloc = r.allocation_pct or Decimal("0")
        hours = r.billable_hours or Decimal("0")
        bill = r.hourly_bill_rate or Decimal("0")
        b["revenue"] += bill * hours * alloc
        if r.hourly_cost is not None:
            b["cost"] += r.hourly_cost * hours * alloc

    for c in model.cost_lines:
        key = str(c.phase_id) if getattr(c, "phase_id", None) else UNGROUPED
        b = buckets.get(key)
        if b is None:
            continue
        b["cost"] += c.amount or Decimal("0")

    # Drop the Ungrouped bucket when it has no rows and no phaseless costs.
    if (
        buckets[UNGROUPED]["revenue"] == 0
        and buckets[UNGROUPED]["cost"] == 0
        and any(getattr(r, "phase_id", None) for r in model.resource_lines)
    ):
        buckets.pop(UNGROUPED, None)

    out = sorted(buckets.values(), key=lambda b: b["order"])
    return [
        {
            "phase_id": b["phase_id"],
            "name": b["name"],
            "revenue": format(b["revenue"], "f"),
            "cost": format(b["cost"], "f"),
        }
        for b in out
    ]


def serialize_gm_model(
    model: GmModel,
    *,
    result: Optional[TemplateResult] = None,
) -> dict:
    payload: dict = {
        "id": str(model.id),
        "opportunity_id": (
            str(model.opportunity_id) if model.opportunity_id else None
        ),
        "sow_version_id": (
            str(model.sow_version_id) if model.sow_version_id else None
        ),
        "engagement_type": model.engagement_type,
        "delivery_pattern": model.delivery_pattern,
        "contingency_pct": _fmt(model.contingency_pct),
        "warranty_days": model.warranty_days,
        "revenue_us": _fmt(model.revenue_us),
        "revenue_india": _fmt(model.revenue_india),
        "created_by": str(model.created_by) if model.created_by else None,
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "phases": [serialize_phase(p) for p in (getattr(model, "phases", []) or [])],
        "phase_summary": _phase_summary(model),
        "resource_lines": [serialize_resource_line(r) for r in model.resource_lines],
        "cost_lines": [serialize_cost_line(c) for c in model.cost_lines],
        "completeness_issues": resource_completeness_issues(
            [
                ResourceLinePayload(
                    role=r.role,
                    seniority=r.seniority,
                    location=r.location,
                    person_name=r.person_name,
                    allocation_pct=r.allocation_pct,
                    start_date=r.start_date,
                    end_date=r.end_date,
                    hours_billable=r.billable_hours,
                    hourly_bill_rate=r.hourly_bill_rate,
                    hourly_cost=r.hourly_cost,
                    validated_by=r.validated_by,
                )
                for r in model.resource_lines
            ]
        ),
    }
    if result is not None:
        payload["computed"] = build_compute_response(result)
    return payload


def summarize_gm_model(model: GmModel) -> dict:
    """Compact summary used by the deal detail card + version list."""

    return {
        "id": str(model.id),
        "engagement_type": model.engagement_type,
        "delivery_pattern": model.delivery_pattern,
        "revenue_us": _fmt(model.revenue_us),
        "revenue_india": _fmt(model.revenue_india),
        "resource_line_count": len(model.resource_lines),
        "cost_line_count": len(model.cost_lines),
        "created_by": str(model.created_by) if model.created_by else None,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


# --- xlsx export -----------------------------------------------------------


def build_xlsx(model: GmModel, result: TemplateResult, response: dict) -> bytes:
    """Two-sheet workbook: Resources + Result. Numbers echo the API payload
    verbatim (same Decimal strings) so downstream tools reconcile exactly."""

    from openpyxl import Workbook

    wb = Workbook()
    resources_sheet = wb.active
    resources_sheet.title = "Resources"
    resources_sheet.append(
        [
            "role",
            "seniority",
            "location",
            "person_name",
            "allocation_pct",
            "start_date",
            "end_date",
            "hours_billable",
            "hourly_bill_rate",
            "hourly_cost",
        ]
    )
    for r in model.resource_lines:
        resources_sheet.append(
            [
                r.role,
                r.seniority,
                r.location,
                r.person_name or "TO HIRE",
                _fmt(r.allocation_pct),
                r.start_date.isoformat(),
                r.end_date.isoformat(),
                _fmt(r.billable_hours),
                _fmt(r.hourly_bill_rate),
                _fmt(r.hourly_cost) or "",
            ]
        )
    resources_sheet.append([])
    resources_sheet.append(["engagement_type", model.engagement_type])
    resources_sheet.append(["delivery_pattern", model.delivery_pattern or ""])
    resources_sheet.append(["contingency_pct", _fmt(model.contingency_pct) or ""])
    resources_sheet.append(["warranty_days", model.warranty_days or ""])

    if model.cost_lines:
        costs_sheet = wb.create_sheet("Costs")
        costs_sheet.append(["category", "amount", "location", "note"])
        for c in model.cost_lines:
            costs_sheet.append(
                [c.category, _fmt(c.amount), c.location, c.note or ""]
            )

    result_sheet = wb.create_sheet("Result")
    for k in (
        "revenue_us",
        "cost_us",
        "gm_us",
        "revenue_india",
        "cost_india",
        "gm_india",
        "gm_blended",
        "min_price_us",
        "min_price_india",
        "geography",
        "complete",
    ):
        result_sheet.append([k, response.get(k)])
    result_sheet.append(["us_floor", response["policy"]["us_floor"]])
    result_sheet.append(["india_floor", response["policy"]["india_floor"]])
    result_sheet.append(["us_pass", response["policy"]["us_pass"]])
    result_sheet.append(["india_pass", response["policy"]["india_pass"]])
    result_sheet.append(["requires_ceo", response["policy"]["requires_ceo"]])
    result_sheet.append(["missing", ", ".join(response.get("missing") or [])])
    result_sheet.append(["computed_at", response.get("computed_at")])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- S7 wave 2: reorder + templates ---------------------------------------


async def reorder_phases(
    session: AsyncSession,
    *,
    gm_model_id: uuid.UUID,
    ordered_phase_ids: list[uuid.UUID],
    actor_id: Optional[uuid.UUID],
) -> list[GmModelPhase]:
    """Rewrite the ``order`` column across an entire model's phase set.

    Pass ``ordered_phase_ids`` in the desired display order — position 0
    first. The service refuses to run if the list is not exactly the
    same set as the model's current phases (protects against partial
    reorders that would leave a phase orphaned at an old order).

    Emits one ``gm_model.phases_reordered`` audit row in the same
    transaction as the writes (CLAUDE.md rule 5).
    """

    existing = (
        (
            await session.execute(
                select(GmModelPhase).where(GmModelPhase.gm_model_id == gm_model_id)
            )
        )
        .scalars()
        .all()
    )
    existing_ids = {p.id for p in existing}
    incoming = list(ordered_phase_ids)
    if set(incoming) != existing_ids:
        raise DeliveryModelInputError(
            "ordered_phase_ids must be exactly the current phase set"
        )
    if len(set(incoming)) != len(incoming):
        raise DeliveryModelInputError("ordered_phase_ids must not contain duplicates")

    by_id = {p.id: p for p in existing}
    before = [
        {"id": str(p.id), "order": p.order}
        for p in sorted(existing, key=lambda p: p.order)
    ]

    # Two-step swap: bump every row to (10_000 + new_position) first so
    # we never collide with the UNIQUE(gm_model_id, order) constraint
    # mid-way, then rewrite to the final dense 0..N sequence.
    for new_pos, phase_id in enumerate(incoming):
        by_id[phase_id].order = 10_000 + new_pos
    await session.flush()
    for new_pos, phase_id in enumerate(incoming):
        by_id[phase_id].order = new_pos
    await session.flush()

    after = [
        {"id": str(p_id), "order": pos}
        for pos, p_id in enumerate(incoming)
    ]
    await append_audit(
        session,
        actor_id=actor_id,
        action="gm_model.phases_reordered",
        entity="gm_model",
        entity_id=str(gm_model_id),
        before={"phases": before},
        after={"phases": after},
    )
    await session.commit()
    return sorted(existing, key=lambda p: p.order)


def _build_template_json(model: GmModel) -> dict[str, Any]:
    """Capture a persisted model as a reusable template shape.

    Blueprint §7 rule: NO cost values. Resource lines carry
    role/seniority/location/allocation + relative ``hours_billable``;
    ``hourly_cost`` is intentionally omitted. Bill rate is preserved
    so the Builder has a starting price on load — but Delivery is
    expected to revise it against the current rate card.
    """

    phases_by_id = {p.id: p for p in (getattr(model, "phases", []) or [])}

    return {
        "engagement_type": model.engagement_type,
        "delivery_pattern": model.delivery_pattern,
        "contingency_pct": _fmt(model.contingency_pct),
        "warranty_days": model.warranty_days,
        "phases": [
            {
                "name": p.name,
                "order": p.order,
                "sow_deliverable_ref": p.sow_deliverable_ref,
                "description": p.description,
            }
            for p in sorted(phases_by_id.values(), key=lambda p: p.order)
        ],
        "resource_lines": [
            {
                "phase_name": (
                    phases_by_id[r.phase_id].name
                    if getattr(r, "phase_id", None) and r.phase_id in phases_by_id
                    else None
                ),
                "role": r.role,
                "seniority": r.seniority,
                "location": r.location,
                "allocation_pct": _fmt(r.allocation_pct),
                "hours_billable": _fmt(r.billable_hours),
                "hourly_bill_rate": _fmt(r.hourly_bill_rate),
                # NOTE: hourly_cost intentionally omitted (blueprint §7).
            }
            for r in model.resource_lines
        ],
        "cost_lines": [
            {
                "phase_name": (
                    phases_by_id[c.phase_id].name
                    if getattr(c, "phase_id", None) and c.phase_id in phases_by_id
                    else None
                ),
                "category": c.category,
                "amount": _fmt(c.amount),
                "location": c.location,
                "note": c.note,
            }
            for c in model.cost_lines
        ],
    }


async def save_as_template(
    session: AsyncSession,
    *,
    actor_id: Optional[uuid.UUID],
    gm_model_id: uuid.UUID,
    name: str,
) -> GmModelTemplate:
    """Persist ``gm_model_id``'s current shape as a reusable template.

    Fails 422 when ``name`` is blank or already used (UNIQUE at the DB
    level; we surface the friendlier error before the flush). Fails 404
    when the source model does not exist.
    """

    name = (name or "").strip()
    if not name:
        raise DeliveryModelInputError("template name is required")

    # Uniqueness pre-check — the DB UNIQUE index is the source of truth.
    dupe = (
        await session.execute(
            select(GmModelTemplate).where(GmModelTemplate.name == name)
        )
    ).scalar_one_or_none()
    if dupe is not None:
        raise DeliveryModelInputError(f"template name {name!r} is already in use")

    model = await load_gm_model(session, gm_model_id)
    template_json = _build_template_json(model)

    tpl = GmModelTemplate(
        id=uuid.uuid4(),
        name=name,
        engagement_type=model.engagement_type,
        created_by=actor_id,
        template_json=template_json,
        active=True,
    )
    session.add(tpl)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="gm_model_template.created",
        entity="gm_model_template",
        entity_id=str(tpl.id),
        before=None,
        after={
            "name": name,
            "engagement_type": model.engagement_type,
            "source_gm_model_id": str(model.id),
            "phase_count": len(template_json["phases"]),
            "resource_line_count": len(template_json["resource_lines"]),
            "cost_line_count": len(template_json["cost_lines"]),
        },
    )
    await session.commit()
    return tpl


async def list_templates(
    session: AsyncSession, *, engagement_type: Optional[str] = None
) -> list[GmModelTemplate]:
    """List active templates, optionally narrowed to one engagement type."""

    stmt = select(GmModelTemplate).where(GmModelTemplate.active.is_(True))
    if engagement_type:
        stmt = stmt.where(GmModelTemplate.engagement_type == engagement_type)
    stmt = stmt.order_by(GmModelTemplate.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def delete_template(
    session: AsyncSession, *, template_id: uuid.UUID, actor_id: Optional[uuid.UUID]
) -> None:
    """Soft-delete: flip ``active=false`` and audit. Templates are never
    hard-deleted so past ``seed_from_template`` audit rows remain
    resolvable to a name."""

    tpl = (
        await session.execute(
            select(GmModelTemplate).where(GmModelTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tpl is None:
        raise DeliveryModelInputError("template not found")
    if not tpl.active:
        return

    tpl.active = False
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="gm_model_template.deleted",
        entity="gm_model_template",
        entity_id=str(tpl.id),
        before={"active": True},
        after={"active": False, "name": tpl.name},
    )
    await session.commit()


async def seed_from_template(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    template_id: uuid.UUID,
    actor_id: Optional[uuid.UUID],
) -> GmModel:
    """Create a fresh draft ``gm_model`` from a template.

    The seeded model:
      * copies the template's phases + resource_lines + cost_lines
      * sets every resource_line.hourly_cost to NULL — the Builder will
        pull the active rate card's base band when Delivery opens the
        Builder (see :func:`create_gm_model_version` fallback)
      * uses today's date for start/end (Delivery revises per SOW)

    Emits one ``gm_model.seeded_from_template`` audit row.
    """

    tpl = (
        await session.execute(
            select(GmModelTemplate).where(GmModelTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tpl is None or not tpl.active:
        raise DeliveryModelInputError("template not found")

    tj = tpl.template_json or {}
    # Default dates: today .. today+90d. Delivery will overwrite per line.
    today = date.today()
    from datetime import timedelta as _td

    default_start = today
    default_end = today + _td(days=90)

    phase_inputs = [
        PhaseInput(
            name=str(p.get("name") or "Phase").strip() or "Phase",
            order=int(p.get("order") or i),
            sow_deliverable_ref=(p.get("sow_deliverable_ref") or None),
            description=(p.get("description") or None),
        )
        for i, p in enumerate(tj.get("phases") or [])
    ]

    resource_inputs: list[ResourceLinePayload] = []
    for r in tj.get("resource_lines") or []:
        loc = r.get("location") if r.get("location") in _ALLOWED_LOCATIONS else "US"
        resource_inputs.append(
            ResourceLinePayload(
                role=str(r.get("role") or ""),
                seniority=str(r.get("seniority") or ""),
                location=loc,
                person_name=None,  # always "to hire" on seed
                allocation_pct=Decimal(str(r.get("allocation_pct") or "1")),
                start_date=default_start,
                end_date=default_end,
                hours_billable=Decimal(str(r.get("hours_billable") or "0")),
                hourly_bill_rate=Decimal(str(r.get("hourly_bill_rate") or "0")),
                # Template rule: cost is NEVER carried on a template. Leave
                # NULL and let the rate-card fallback in
                # ``create_gm_model_version`` populate on save.
                hourly_cost=None,
                validated_by=None,
                phase_name=(r.get("phase_name") or None),
            )
        )

    cost_inputs: list[CostLinePayload] = []
    for c in tj.get("cost_lines") or []:
        cat = c.get("category")
        if cat not in _ALLOWED_COST_CATEGORIES:
            continue
        loc = c.get("location") if c.get("location") in _ALLOWED_LOCATIONS else "US"
        cost_inputs.append(
            CostLinePayload(
                category=cat,
                amount=Decimal(str(c.get("amount") or "0")),
                note=(c.get("note") or None),
                location=loc,
                phase_name=(c.get("phase_name") or None),
            )
        )

    engagement_type = tj.get("engagement_type") or tpl.engagement_type
    payload = GmModelPayload(
        engagement_type=engagement_type,
        sow_version_id=None,
        delivery_pattern=tj.get("delivery_pattern"),
        contingency_pct=(
            Decimal(str(tj["contingency_pct"]))
            if tj.get("contingency_pct")
            else None
        ),
        warranty_days=tj.get("warranty_days"),
        resource_lines=resource_inputs,
        cost_lines=cost_inputs,
        phases=phase_inputs,
    )

    # Delegate to the immutable-version write path so the seeded model
    # audits + hooks (change-voids-approval) fire identically to a save.
    if not resource_inputs:
        # ``create_gm_model_version`` requires at least one line; when a
        # template has none we insert a phaseless placeholder row that
        # Delivery will overwrite. Keeps the seed idempotent.
        resource_inputs.append(
            ResourceLinePayload(
                role="TBD",
                seniority="TBD",
                location="US",
                person_name=None,
                allocation_pct=Decimal("1"),
                start_date=default_start,
                end_date=default_end,
                hours_billable=Decimal("0"),
                hourly_bill_rate=Decimal("0"),
                hourly_cost=None,
                validated_by=None,
                phase_name=phase_inputs[0].name if phase_inputs else None,
            )
        )
        payload = GmModelPayload(
            engagement_type=engagement_type,
            sow_version_id=None,
            delivery_pattern=tj.get("delivery_pattern"),
            contingency_pct=payload.contingency_pct,
            warranty_days=payload.warranty_days,
            resource_lines=resource_inputs,
            cost_lines=cost_inputs,
            phases=phase_inputs,
        )

    model = await create_gm_model_version(
        session,
        opportunity_id=opportunity_id,
        actor_id=actor_id,
        payload=payload,
    )

    # Extra audit hop naming the template — the create_gm_model_version
    # call already emitted ``gm_model.created``; this row explains WHY
    # (blueprint §12: audits should carry the reason where cheap).
    await append_audit(
        session,
        actor_id=actor_id,
        action="gm_model.seeded_from_template",
        entity="gm_model",
        entity_id=str(model.id),
        before=None,
        after={
            "opportunity_id": str(opportunity_id),
            "template_id": str(tpl.id),
            "template_name": tpl.name,
        },
    )
    await session.commit()
    return model


def serialize_template(tpl: GmModelTemplate) -> dict:
    return {
        "id": str(tpl.id),
        "name": tpl.name,
        "engagement_type": tpl.engagement_type,
        "created_by": str(tpl.created_by) if tpl.created_by else None,
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
        "active": bool(tpl.active),
        "phase_count": len(tpl.template_json.get("phases") or []),
        "resource_line_count": len(tpl.template_json.get("resource_lines") or []),
        "cost_line_count": len(tpl.template_json.get("cost_lines") or []),
    }


__all__ = [
    "CostLinePayload",
    "DEFAULT_HR_CONFIG",
    "DeliveryModelInputError",
    "GmModelPayload",
    "HrConfig",
    "PhaseInput",
    "ResourceLinePayload",
    "ResourceWarning",
    "build_compute_response",
    "build_xlsx",
    "capacity_conflicts",
    "compute_live",
    "create_gm_model_version",
    "delete_template",
    "hr_lead_time_warnings",
    "latest_gm_model_for",
    "list_gm_models_for",
    "list_templates",
    "load_gm_model",
    "parse_cost_line",
    "parse_gm_model_payload",
    "parse_phase",
    "parse_resource_line",
    "reorder_phases",
    "resource_completeness_issues",
    "save_as_template",
    "seed_from_template",
    "serialize_cost_line",
    "serialize_gm_model",
    "serialize_phase",
    "serialize_resource_line",
    "serialize_template",
    "serialize_warnings",
    "summarize_gm_model",
]


# --- fixed-fee revenue allocation (S10-07) --------------------------------


def allocate_fixed_fee_revenue(
    lines: list[ResourceLinePayload], total_price: Decimal
) -> tuple[Decimal, Decimal, list[str]]:
    """Split one fixed fee across US and India. Returns ``(us, india, notes)``.

    For a fixed-fee engagement the revenue is settled — it is the fee. What
    varies is cost, so the margin is the fee against bottom-up delivery cost,
    and a mixed-geography SOW needs that fee attributed to each side before
    the per-geography floors mean anything.

    ``docs/sow-first-principles.md`` §5: "For a mixed fixed-fee SOW the
    default allocation is cost-weighted effort; Finance can override with a
    recorded basis." So cost-weighted where cost is known.

    When no cost rate has resolved — no published cost band, nothing entered
    on the line — cost-weighting is impossible and the fallback is
    hours-weighted, which is a proxy, not the policy. That is returned as a
    note so it reaches the confirm screen as a visible fallback rather than
    passing for the real thing (sow-first §7, "fallbacks are loud").

    The remainder is placed on the larger side so the two always sum to
    exactly ``total_price``: the fixed-price template rejects an allocation
    that does not, and silently losing a cent of revenue to rounding would be
    a worse answer than putting it somewhere explicit.
    """

    notes: list[str] = []
    if total_price <= 0:
        return Decimal("0"), Decimal("0"), ["total price is zero — nothing to allocate"]
    if not lines:
        return total_price, Decimal("0"), ["no resource lines — all revenue to US"]

    def _weight(line: ResourceLinePayload, *, use_cost: bool) -> Decimal:
        hours = line.hours_billable or Decimal("0")
        if not use_cost:
            return hours
        return hours * (line.hourly_cost or Decimal("0"))

    use_cost = all(
        line.hourly_cost is not None and line.hourly_cost > 0 for line in lines
    )
    if not use_cost:
        notes.append(
            "revenue split by hours, not cost — no cost rate resolved for every "
            "line, so cost-weighted allocation was not possible"
        )

    us = sum(
        (_weight(r, use_cost=use_cost) for r in lines if r.location == "US"),
        Decimal("0"),
    )
    india = sum(
        (_weight(r, use_cost=use_cost) for r in lines if r.location == "India"),
        Decimal("0"),
    )
    total_weight = us + india
    if total_weight <= 0:
        return total_price, Decimal("0"), [
            *notes,
            "no billable hours on any line — all revenue to US",
        ]

    revenue_us = (total_price * us / total_weight).quantize(Decimal("0.01"))
    revenue_india = (total_price - revenue_us).quantize(Decimal("0.01"))

    # Guard the sum explicitly rather than trusting the quantize.
    drift = total_price - (revenue_us + revenue_india)
    if drift != 0:
        if revenue_us >= revenue_india:
            revenue_us += drift
        else:
            revenue_india += drift

    return revenue_us, revenue_india, notes
