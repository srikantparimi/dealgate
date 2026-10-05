"""Proposed commercial component from the SOW + auto-staffing grid (S22).

The owner's directive (2026-10-05): the Staffing & GM editor opens
pre-filled from what the system already derived — human intervention
only where needed, every value correctable. Sources, in provenance
terms:

- ``extracted``  — term dates, currency, total price, engagement type:
  the SOW extraction the human confirms field by field.
- ``looked_up``  — staffing lines the deterministic auto-staffing
  service persisted at upload (roles, locations, allocation fractions,
  bill/cost rates from rate cards and past-SOW retrieval).
- ``calculated`` — the even fee spread across service months.
- ``defaulted``  — anything the sources could not supply, each with an
  explicit warning.

Rule 2 holds: no LLM writes a number here. The proposal is a draft with
``costs_confirmed=False`` — the gm engine reports it honestly
incomplete until a human confirms, and saving still goes through the
versioned, audited ``save_commercial_model`` path. A signed financial
basis refuses a proposal outright.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gm.calendar import StaffingAssignment
from app.gm.commercial import CalendarPricing, FeeAllocation, FixedFee, PricingComponent, StaffingRate
from app.models.approval import ApprovalPackage
from app.models.gm_model import GmModel, ResourceLine
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.services.commercial_models import COMPONENT
from app.services.policy import active_policy
from app.services.provenance import value_of


class ProposalError(HTTPException):
    pass


_PROFILE_BY_ENGAGEMENT: dict[str, str] = {
    "staff_aug": "calendar_staff_aug",
    "tm": "calendar_staff_aug",
    "time_and_materials": "calendar_staff_aug",
    "managed_service": "fixed_assignment",
    "fixed_price": "fixed_assignment",
    "assessment": "fixed_assignment",
}

_DEFAULT_TIMEZONE = "America/Los_Angeles"


def _months(start: date, end: date) -> list[date]:
    months: list[date] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        months.append(cursor)
        cursor = (
            date(cursor.year + 1, 1, 1)
            if cursor.month == 12
            else date(cursor.year, cursor.month + 1, 1)
        )
    return months


def _even_fractions(count: int) -> list[Decimal]:
    """Exact even split summing to exactly 1 (remainder on the last month)."""
    base = (Decimal(1) / Decimal(count)).quantize(Decimal("0.0001"))
    fractions = [base] * (count - 1)
    fractions.append(Decimal(1) - base * (count - 1))
    return fractions


def _to_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


async def propose_component(
    session: AsyncSession, *, opportunity_id: uuid.UUID
) -> dict[str, Any]:
    version = await session.scalar(
        select(SowVersion)
        .join(Sow, Sow.id == SowVersion.sow_id)
        .where(
            Sow.opportunity_id == opportunity_id,
            SowVersion.discarded_at.is_(None),
            SowVersion.superseded_by.is_(None),
        )
        .order_by(SowVersion.version_no.desc(), SowVersion.uploaded_at.desc())
        .limit(1)
    )
    if version is None:
        raise ProposalError(404, "No SOW version to propose from")
    signed = await session.scalar(
        select(ApprovalPackage.id)
        .where(
            ApprovalPackage.sow_version_id == version.id,
            or_(
                ApprovalPackage.status == "released",
                ApprovalPackage.id.in_(
                    select(SignedSowUpload.package_id).where(
                        SignedSowUpload.verify_status == "verified"
                    )
                ),
            ),
        )
        .limit(1)
    )
    if signed is not None:
        raise ProposalError(
            409,
            "Signed financial basis is immutable; a proposal would be "
            "misleading — create a separate amendment SOW version",
        )

    fields = version.extracted_fields or {}
    provenance: dict[str, str] = {}
    warnings: list[str] = []

    term_start = _to_date(value_of(fields.get("term_start")))
    term_end = _to_date(value_of(fields.get("term_end")))
    if term_start and term_end and term_start <= term_end:
        provenance["service_start"] = provenance["service_end"] = "extracted"
    else:
        today = date.today()
        term_start = date(today.year, today.month, 1)
        term_end = _months(term_start, term_start)[0]
        term_end = (
            date(term_start.year + (term_start.month + 2 > 12), ((term_start.month + 2 - 1) % 12) + 1, 1)
        )
        provenance["service_start"] = provenance["service_end"] = "defaulted"
        warnings.append(
            "SOW term dates missing or invalid — a three-month window was "
            "defaulted; confirm the real term"
        )

    currency = value_of(fields.get("currency"))
    if currency:
        provenance["currency"] = "extracted"
    else:
        currency, provenance["currency"] = "USD", "defaulted"
        warnings.append("Currency missing from the SOW — defaulted to USD")

    raw_price = value_of(fields.get("price"))
    price: Decimal | None = None
    if raw_price not in (None, ""):
        try:
            price = Decimal(str(raw_price))
            provenance["pricing.amount"] = "extracted"
        except ArithmeticError:
            price = None
    if price is None:
        warnings.append("Contract price missing — enter the fee")
        provenance["pricing.amount"] = "defaulted"

    engagement = (
        version.engagement_type_confirmed
        or value_of(fields.get("engagement_type_suggested"))
        or "fixed_price"
    )
    suggested_profile = _PROFILE_BY_ENGAGEMENT.get(str(engagement), "fixed_assignment")

    lines = (
        await session.scalars(
            select(ResourceLine)
            .join(GmModel, GmModel.id == ResourceLine.gm_model_id)
            .where(GmModel.sow_version_id == version.id)
            .order_by(ResourceLine.created_at.asc(), ResourceLine.id.asc())
        )
    ).all()
    if lines:
        provenance["staffing"] = "looked_up"
    else:
        warnings.append(
            "No auto-staffing lines were available for this SOW — add "
            "Calendar staffing assignments by hand"
        )

    policy = await active_policy(session)
    policy_version = str(policy.id) if policy.id else "blueprint-defaults-v1"
    source_id = str(version.sow_id)
    source_version = str(version.id)
    binding = dict(
        source_id=source_id,
        source_version=source_version,
        component_id="proposed",
        profile_version="1",
        policy_version=policy_version,
    )

    dominant_location = "US"
    if lines:
        by_loc: dict[str, int] = {}
        for line in lines:
            by_loc[line.location] = by_loc.get(line.location, 0) + 1
        dominant_location = max(by_loc, key=lambda k: by_loc[k])

    staffing = tuple(
        StaffingAssignment(
            assignment_id=f"proposed-{index + 1}",
            role=f"{line.seniority} {line.role}".strip(),
            location=line.location if line.location in ("US", "India") else None,
            timezone=_DEFAULT_TIMEZONE,
            currency=currency,
            quantity=1,
            allocation=Decimal(line.allocation_pct),
            calendar=None,
            bill_rate=Decimal(line.hourly_bill_rate),
            cost_rate=Decimal(line.hourly_loaded_cost),
            rate_version="auto-staff",
            cost_version="auto-staff",
            start=max(line.start_date, term_start),
            end=min(line.end_date, term_end),
            cost_rate_basis="hourly",
            **binding,
        )
        for index, line in enumerate(lines)
    )

    if suggested_profile == "calendar_staff_aug" and staffing:
        pricing: Any = CalendarPricing(
            rates=tuple(
                StaffingRate(
                    assignment_id=a.assignment_id,
                    basis="hourly",
                    rate=a.bill_rate,
                    version="auto-staff",
                )
                for a in staffing
            )
        )
        profile = "calendar_staff_aug"
        provenance["pricing.rates"] = "looked_up"
    else:
        months = _months(term_start, term_end)
        fractions = _even_fractions(len(months))
        pricing = FixedFee(
            price if price is not None else Decimal("0"),
            tuple(
                FeeAllocation(month, dominant_location, fraction)
                for month, fraction in zip(months, fractions)
            ),
            "even service months (proposed)",
            Decimal("0.01"),
        )
        profile = "fixed_assignment"
        provenance["pricing.allocations"] = "calculated"

    component = PricingComponent(
        version="1",
        workstream_id="delivery",
        profile=profile,
        source_evidence=(f"sow-version:{source_version}",),
        service_start=term_start,
        service_end=term_end,
        timezone=_DEFAULT_TIMEZONE,
        currency=currency,
        billing_cadence=None,
        cost_basis=None,
        costs_confirmed=False,  # the machine never confirms costs
        costs=(),
        pricing=pricing,
        staffing=staffing,
        **binding,
    )

    # JsonB round-trips Python None as JSON null on some engines, so test
    # the snapshot's truthiness rather than SQL NULL-ness.
    snapshots = (
        await session.scalars(
            select(GmModel.commercial_snapshot).where(
                GmModel.opportunity_id == opportunity_id
            )
        )
    ).all()
    saved_version_exists = any(bool(snapshot) for snapshot in snapshots)

    return {
        "component": COMPONENT.dump_python(component, mode="json"),
        "provenance": provenance,
        "warnings": warnings,
        "suggested_profile": suggested_profile,
        "engagement_type": str(engagement),
        "saved_version_exists": saved_version_exists,
        "sow_version_id": source_version,
    }
