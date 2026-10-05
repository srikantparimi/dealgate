"""Staffing advice for the commercial editor (S22).

Composes three rule-separated parts:
- the Bedrock scope→team DRAFT (rule 6: quotes as evidence, human
  confirms; rule 2: it never prices anything);
- cost rates looked up from the active rate card (median cost_base per
  location; explicit defaults with a warning when no card exists);
- the pure-Decimal ``gm.staffing_mix`` solver, which alone does the
  math and raises the delivery caution when scope needs more people
  than the fee supports at the target GM.

Nothing here writes: the editor applies the suggestion into the normal
versioned save path.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gm.staffing_mix import solve_staffing_mix
from app.integrations.bedrock_team_estimate import EstimateUnavailable, TeamEstimate
from app.models.sow import Sow, SowVersion
from app.services.policy import active_policy
from app.services.provenance import value_of
from app.services.rate_cards import active_rate_card

_DEFAULT_ONSHORE = Decimal("95")
_DEFAULT_OFFSHORE = Decimal("30")


class AdviceError(HTTPException):
    pass


async def _current_version(session: AsyncSession, opportunity_id: uuid.UUID) -> SowVersion:
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
        raise AdviceError(404, "No SOW version to advise from")
    return version


async def _location_rates(session: AsyncSession) -> tuple[Decimal, Decimal, str, list[str]]:
    card = await active_rate_card(session)
    warnings: list[str] = []
    if card is None or not card.rows:
        warnings.append(
            "No active rate card — onshore/offshore cost defaults used; "
            "publish a rate card for real numbers"
        )
        return _DEFAULT_ONSHORE, _DEFAULT_OFFSHORE, "defaulted", warnings
    by_location: dict[str, list[Decimal]] = {}
    for row in card.rows:
        by_location.setdefault(row.location, []).append(Decimal(row.cost_base))
    onshore = median(by_location["US"]) if by_location.get("US") else _DEFAULT_ONSHORE
    offshore = (
        median(by_location["India"]) if by_location.get("India") else _DEFAULT_OFFSHORE
    )
    if "US" not in by_location or "India" not in by_location:
        warnings.append("Rate card misses a location — its default was used")
    return Decimal(onshore), Decimal(offshore), "looked_up", warnings


def _fields_text(version: SowVersion) -> str:
    parts: list[str] = []
    for name, cell in (version.extracted_fields or {}).items():
        value = value_of(cell)
        if value:
            parts.append(f"{name}: {value}")
    return "\n".join(parts)


async def advise(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    estimator: Any,
    document_text: str | None = None,
    revenue: Decimal | None = None,
    weeks: Decimal | None = None,
    service_start: date | None = None,
    service_end: date | None = None,
    target_gm: Decimal | None = None,
    required_fte: Decimal | None = None,
    min_onshore_fte: Decimal = Decimal("0"),
) -> dict[str, Any]:
    version = await _current_version(session, opportunity_id)
    warnings: list[str] = []

    estimate_payload: dict[str, Any] | None = None
    if required_fte is None:
        text = document_text or _fields_text(version)
        if not text.strip():
            warnings.append("No SOW text available for a scope estimate")
            raw: TeamEstimate | EstimateUnavailable = EstimateUnavailable(
                reason="no text"
            )
        else:
            raw = estimator.estimate(text)
        if isinstance(raw, TeamEstimate):
            try:
                required_fte = Decimal(raw.required_fte)
            except InvalidOperation:
                required_fte = None
            if required_fte is not None and required_fte <= 0:
                required_fte = None
            if weeks is None and raw.duration_weeks:
                try:
                    weeks = Decimal(raw.duration_weeks)
                except InvalidOperation:
                    weeks = None
            estimate_payload = {
                "required_fte": raw.required_fte,
                "duration_weeks": raw.duration_weeks,
                "roles": [
                    {"role": r.role, "fte": r.fte,
                     "location_hint": r.location_hint, "evidence": r.evidence}
                    for r in raw.roles
                ],
                "rationale": raw.rationale,
                "evidence": list(raw.evidence),
                "provenance": "extracted",
            }
        else:
            warnings.append(f"Scope estimate unavailable: {raw.reason} — enter the FTE by hand")

    if revenue is None:
        raw_price = value_of((version.extracted_fields or {}).get("price"))
        if raw_price:
            cleaned = (
                str(raw_price).replace(",", "").replace("$", "").replace("USD", "").strip()
            )
            try:
                revenue = Decimal(cleaned)
            except ArithmeticError:
                revenue = None
    if revenue is None or revenue <= 0:
        raise AdviceError(422, "A positive fee is required to advise — enter the fee")

    if weeks is None and service_start and service_end and service_end > service_start:
        weeks = (Decimal((service_end - service_start).days) / Decimal(7)).quantize(
            Decimal("0.1")
        )
    if weeks is None or weeks <= 0:
        raise AdviceError(
            422, "A duration is required — set the term dates or weeks"
        )

    if target_gm is None:
        policy = await active_policy(session)
        target_gm = Decimal(policy.us_floor)
        target_provenance = "defaulted"
        warnings.append(
            f"Target GM defaulted to the US policy floor ({target_gm}); "
            "set the deal's contractual target if it differs"
        )
    else:
        target_provenance = "manual"

    onshore_rate, offshore_rate, rate_provenance, rate_warnings = await _location_rates(
        session
    )
    warnings.extend(rate_warnings)

    result = solve_staffing_mix(
        revenue=revenue,
        weeks=weeks,
        target_gm=target_gm,
        onshore_cost_per_hour=onshore_rate,
        offshore_cost_per_hour=offshore_rate,
        required_fte=required_fte,
        min_onshore_fte=min_onshore_fte,
    )

    def _mix(c):
        return None if c is None else {
            "onshore_fte": str(c.onshore), "offshore_fte": str(c.offshore),
            "cost": str(c.cost), "gm": str(c.gm),
        }

    return {
        "inputs": {
            "revenue": str(revenue), "weeks": str(weeks),
            "target_gm": str(target_gm), "target_gm_provenance": target_provenance,
            "required_fte": str(required_fte) if required_fte is not None else None,
            "min_onshore_fte": str(min_onshore_fte),
            "onshore_cost_per_hour": str(onshore_rate),
            "offshore_cost_per_hour": str(offshore_rate),
            "rates_provenance": rate_provenance,
        },
        "estimate": estimate_payload,
        "suggested": _mix(result.suggested),
        "feasible": result.feasible,
        "max_fte_at_target": str(result.max_fte_at_target),
        "caution": result.caution,
        "warnings": warnings,
        "sow_version_id": str(version.id),
    }
