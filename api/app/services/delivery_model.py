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

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.gm import EngagementType, compute as gm_compute
from app.gm.core import min_price as gm_min_price
from app.gm.policy import INDIA_FLOOR, US_FLOOR, check_floors
from app.gm.types import (
    CostLine as GmCostLine,
    ResourceLine as GmResourceLine,
    TemplateResult,
)
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.services.gm_sandbox import (
    SandboxInputError,
    parse_engagement_type,
    parse_inputs,
)
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


@dataclass(frozen=True)
class CostLinePayload:
    category: str
    amount: Decimal
    note: Optional[str]
    location: str = "US"


@dataclass(frozen=True)
class GmModelPayload:
    engagement_type: str
    sow_version_id: Optional[uuid.UUID]
    delivery_pattern: Optional[str]
    contingency_pct: Optional[Decimal]
    warranty_days: Optional[int]
    resource_lines: list[ResourceLinePayload]
    cost_lines: list[CostLinePayload]


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
    return CostLinePayload(
        category=category,
        amount=_to_decimal(raw.get("amount", 0), field=f"{field}.amount"),
        note=(str(raw["note"]) if raw.get("note") else None),
        location=location,
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

    # Pre-fill missing costs from the rate card, once per role/seniority/loc.
    filled_lines: list[ResourceLinePayload] = []
    for line in payload.resource_lines:
        if line.hourly_cost is not None:
            filled_lines.append(line)
            continue
        band = await _cost_band_for(session, line)
        if band is None:
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
                hourly_bill_rate=line.hourly_bill_rate,
                hourly_cost=band.base,
                validated_by=line.validated_by,
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
    )

    # Snapshot revenue components at save-time so the list view does not
    # have to re-run the GM engine on read. Bill-rate * hours * allocation
    # per line (matches the pure library — see ``ResourceLine.revenue``).
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
    }


def serialize_cost_line(c: CostLine) -> dict:
    return {
        "id": str(c.id),
        "category": c.category,
        "amount": _fmt(c.amount),
        "note": c.note,
        "location": c.location,
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


__all__ = [
    "CostLinePayload",
    "DEFAULT_HR_CONFIG",
    "DeliveryModelInputError",
    "GmModelPayload",
    "HrConfig",
    "ResourceLinePayload",
    "ResourceWarning",
    "build_compute_response",
    "build_xlsx",
    "capacity_conflicts",
    "compute_live",
    "create_gm_model_version",
    "hr_lead_time_warnings",
    "latest_gm_model_for",
    "list_gm_models_for",
    "load_gm_model",
    "parse_cost_line",
    "parse_gm_model_payload",
    "parse_resource_line",
    "resource_completeness_issues",
    "serialize_cost_line",
    "serialize_gm_model",
    "serialize_resource_line",
    "serialize_warnings",
    "summarize_gm_model",
]
