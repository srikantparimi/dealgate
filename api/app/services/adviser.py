"""Opportunity adviser service — deterministic pricing on top of the LLM draft.

The LLM proposes a team (via :mod:`app.integrations.bedrock_adviser`). This
module never lets the LLM produce a number. Instead:

1. Look up the currently-active rate card version (Agent L's tables).
2. For every proposed role/seniority/location, resolve a per-hour cost band.
   A missing band is filled with the ``SENTINEL_COST_BAND`` and flagged in
   the response so Presales sees the gap immediately.
3. Multiply cost * hours * allocation to get a per-member cost band.
4. Roll up per geography (US-only, India-only, Mixed) and apply the policy
   floors (US 35%, India 50% by default; overridden by the active
   ``policy_version`` when Finance has published one).
5. Persist the immutable ``adviser_estimate`` row with the inputs, the
   structured team, the pricing bands, the sources, model + prompt_version.
6. Emit an ``adviser.estimated`` audit row in the same transaction.

Return value is either an :class:`AdviserEstimate` (structured payload)
or a :class:`Questions` payload (thin intake / adapter unavailable).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.gm.core import min_price as gm_min_price
from app.gm.policy import INDIA_FLOOR, US_FLOOR
from app.integrations.bedrock_adviser import (
    Adviser,
    ClarifyingQuestions,
    ProposeResult,
    StructuredTeam,
    TeamMember,
    propose_team,
)
from app.models.adviser_estimate import DEFAULT_LABEL, AdviserEstimate
from app.services.rate_cards import CostBand, active_rate_card, lookup_cost


# --- sentinels --------------------------------------------------------------

# Sentinel cost band used when a rate card is missing entirely, or when a
# role/seniority/location is absent from the active version. Marked with
# ``is_sentinel`` so the UI can show "TBD" instead of pretending the number
# is real. Blueprint §2: never fabricate a number silently.
SENTINEL_COST_BAND = CostBand(
    low=Decimal("100.00"), base=Decimal("125.00"), high=Decimal("150.00")
)


# --- dataclasses ------------------------------------------------------------


@dataclass(frozen=True)
class PricedMember:
    role: str
    seniority: str
    location: str
    hours: Decimal
    allocation_pct: Decimal
    cost_low: Decimal
    cost_base: Decimal
    cost_high: Decimal
    is_sentinel: bool  # True when we fell back to the sentinel band

    def serialize(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "seniority": self.seniority,
            "location": self.location,
            "hours": _fmt(self.hours),
            "allocation_pct": _fmt(self.allocation_pct),
            "cost_low": _fmt(self.cost_low),
            "cost_base": _fmt(self.cost_base),
            "cost_high": _fmt(self.cost_high),
            "is_sentinel": self.is_sentinel,
        }


@dataclass(frozen=True)
class DeliveryOption:
    """A staffing mix + min price for one geography scenario.

    ``eligible`` is False when the LLM's team can't be delivered from that
    geography (e.g. Mixed team ↔ India-only option). UI hides ineligible
    options rather than showing a $0.
    """

    key: str  # "us_only" | "india_only" | "mixed"
    label: str
    cost_low: Decimal
    cost_base: Decimal
    cost_high: Decimal
    min_price: Decimal
    floor_applied: Decimal
    eligible: bool

    def serialize(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "cost_low": _fmt(self.cost_low),
            "cost_base": _fmt(self.cost_base),
            "cost_high": _fmt(self.cost_high),
            "min_price": _fmt(self.min_price),
            "floor_applied": _fmt(self.floor_applied),
            "eligible": self.eligible,
        }


@dataclass(frozen=True)
class Estimate:
    """Return payload for a successful estimate.

    Wraps the persisted ORM row so the router can serialize either directly
    (POST /adviser/estimates response) or via ``load_estimate`` on GET.
    """

    id: uuid.UUID
    submitted_at: str
    submitted_by: uuid.UUID | None
    label: str
    scope: str
    confidence: str
    reasons: tuple[str, ...]
    team: tuple[PricedMember, ...]
    cost_low: Decimal
    cost_base: Decimal
    cost_high: Decimal
    options: tuple[DeliveryOption, ...]
    sources: tuple[dict[str, Any], ...]
    model: str
    prompt_version: str
    inputs: dict[str, Any]
    rate_card_version_id: uuid.UUID | None
    has_sentinel_costs: bool
    reviewer_id: uuid.UUID | None = None
    reviewed_at: str | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "kind": "estimate",
            "id": str(self.id),
            "submitted_at": self.submitted_at,
            "submitted_by": str(self.submitted_by) if self.submitted_by else None,
            "label": self.label,
            "scope": self.scope,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "team": [m.serialize() for m in self.team],
            "cost_low": _fmt(self.cost_low),
            "cost_base": _fmt(self.cost_base),
            "cost_high": _fmt(self.cost_high),
            "options": [o.serialize() for o in self.options],
            "sources": list(self.sources),
            "model": self.model,
            "prompt_version": self.prompt_version,
            "inputs": self.inputs,
            "rate_card_version_id": (
                str(self.rate_card_version_id) if self.rate_card_version_id else None
            ),
            "has_sentinel_costs": self.has_sentinel_costs,
            "reviewer_id": str(self.reviewer_id) if self.reviewer_id else None,
            "reviewed_at": self.reviewed_at,
        }


@dataclass(frozen=True)
class Questions:
    """Return payload when the adviser needs more information."""

    questions: tuple[str, ...]
    note: str
    label: str = DEFAULT_LABEL
    model: str = ""
    prompt_version: str = ""
    sources: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def serialize(self) -> dict[str, Any]:
        return {
            "kind": "questions",
            "questions": list(self.questions),
            "note": self.note,
            "label": self.label,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "sources": list(self.sources),
        }


# --- helpers ---------------------------------------------------------------


def _fmt(value: Decimal) -> str:
    """Serialise a Decimal as a plain string — never a JSON number."""

    return format(value, "f")


def _dec(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _price_member(
    member: TeamMember, rate_card
) -> PricedMember:
    """Look up the cost band for one team member and compute the total cost.

    Falls back to :data:`SENTINEL_COST_BAND` when the rate card is missing or
    doesn't cover the (role, seniority, location) tuple. The caller shows
    Presales the gap via ``is_sentinel``; the number is still deterministic.
    """

    band: CostBand | None = None
    if rate_card is not None:
        band = lookup_cost(member.role, member.seniority, member.location, rate_card)
    is_sentinel = band is None
    if band is None:
        band = SENTINEL_COST_BAND

    hours = _dec(member.hours)
    alloc = _dec(member.allocation_pct)
    factor = hours * alloc
    return PricedMember(
        role=member.role,
        seniority=member.seniority,
        location=member.location,
        hours=hours,
        allocation_pct=alloc,
        cost_low=band.low * factor,
        cost_base=band.base * factor,
        cost_high=band.high * factor,
        is_sentinel=is_sentinel,
    )


def _bucket(
    priced: tuple[PricedMember, ...], location: str
) -> tuple[Decimal, Decimal, Decimal]:
    low = base = high = Decimal("0")
    for m in priced:
        if m.location != location:
            continue
        low += m.cost_low
        base += m.cost_base
        high += m.cost_high
    return low, base, high


def _option(
    key: str,
    label: str,
    priced: tuple[PricedMember, ...],
    *,
    only_location: str | None,
    us_floor: Decimal,
    india_floor: Decimal,
) -> DeliveryOption:
    """Build one delivery option (US-only, India-only, Mixed).

    - us_only / india_only: eligible iff every proposed role is in that
      geography, and we use that side's floor.
    - mixed: eligible iff both sides are non-empty, and we take the *higher*
      floor across the two components so the roll-up never under-prices.
    """

    if only_location is not None:
        eligible = all(m.location == only_location for m in priced)
        low, base, high = _bucket(priced, only_location)
        floor = us_floor if only_location == "US" else india_floor
        cost_low = low
        cost_base = base
        cost_high = high
    else:  # Mixed
        us_low, us_base, us_high = _bucket(priced, "US")
        in_low, in_base, in_high = _bucket(priced, "India")
        cost_low = us_low + in_low
        cost_base = us_base + in_base
        cost_high = us_high + in_high
        eligible = us_base > 0 and in_base > 0
        # Mixed engagements test each component — take the higher floor so
        # the blended min price still clears the tighter constraint.
        floor = max(us_floor, india_floor)

    min_price = (
        gm_min_price(cost_base, floor) if eligible and cost_base > 0 else Decimal("0")
    )
    return DeliveryOption(
        key=key,
        label=label,
        cost_low=cost_low,
        cost_base=cost_base,
        cost_high=cost_high,
        min_price=min_price,
        floor_applied=floor,
        eligible=eligible,
    )


async def _resolve_floors(session: AsyncSession) -> tuple[Decimal, Decimal]:
    """Fetch the active policy version's floors, or the blueprint defaults.

    Kept resilient: the adviser is a math tool, not a policy publisher, so
    any failure resolving the policy collapses to the sentinel defaults.
    """

    try:
        from app.services.policy import active_policy  # type: ignore
    except Exception:
        return US_FLOOR, INDIA_FLOOR
    try:
        policy = await active_policy(session)
    except Exception:
        return US_FLOOR, INDIA_FLOOR
    if policy is None:
        return US_FLOOR, INDIA_FLOOR
    us = getattr(policy, "us_floor", None) or US_FLOOR
    india = getattr(policy, "india_floor", None) or INDIA_FLOOR
    return _dec(us), _dec(india)


# --- public entry ----------------------------------------------------------


async def estimate(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    inputs: dict[str, Any],
    adapter: Adviser | None = None,
) -> Estimate | Questions:
    """Draft, price and persist one opportunity estimate.

    Returns an :class:`Estimate` (persisted) or a :class:`Questions` payload
    (nothing persisted — the LLM asked for more information).
    """

    draft: ProposeResult = propose_team(inputs, adapter=adapter)

    if isinstance(draft, ClarifyingQuestions):
        return Questions(
            questions=draft.questions,
            note=draft.note,
            model=draft.model,
            prompt_version=draft.prompt_version,
            sources=draft.sources,
        )

    assert isinstance(draft, StructuredTeam)

    rate_card = None
    try:
        rate_card = await active_rate_card(session)
    except Exception:
        rate_card = None

    priced: tuple[PricedMember, ...] = tuple(
        _price_member(m, rate_card) for m in draft.team
    )

    us_floor, india_floor = await _resolve_floors(session)

    options = (
        _option(
            "us_only",
            "US-only",
            priced,
            only_location="US",
            us_floor=us_floor,
            india_floor=india_floor,
        ),
        _option(
            "india_only",
            "India-only",
            priced,
            only_location="India",
            us_floor=us_floor,
            india_floor=india_floor,
        ),
        _option(
            "mixed",
            "Mixed",
            priced,
            only_location=None,
            us_floor=us_floor,
            india_floor=india_floor,
        ),
    )

    total_low = sum((m.cost_low for m in priced), Decimal("0"))
    total_base = sum((m.cost_base for m in priced), Decimal("0"))
    total_high = sum((m.cost_high for m in priced), Decimal("0"))

    structured = {
        "scope": draft.scope,
        "team": [m.serialize() for m in priced],
        "confidence": draft.confidence,
        "reasons": list(draft.reasons),
        "options": [o.serialize() for o in options],
        "cost_low": _fmt(total_low),
        "cost_base": _fmt(total_base),
        "cost_high": _fmt(total_high),
        "rate_card_version_id": (
            str(rate_card.id) if rate_card is not None else None
        ),
        "has_sentinel_costs": any(m.is_sentinel for m in priced),
        "us_floor": _fmt(us_floor),
        "india_floor": _fmt(india_floor),
    }

    row = AdviserEstimate(
        id=uuid.uuid4(),
        submitted_by=actor_id,
        inputs=inputs,
        structured_output=structured,
        sources=list(draft.sources),
        model=draft.model,
        prompt_version=draft.prompt_version,
        label=DEFAULT_LABEL,
    )
    session.add(row)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="adviser.estimated",
        entity="adviser_estimate",
        entity_id=str(row.id),
        before=None,
        after={
            "model": row.model,
            "prompt_version": row.prompt_version,
            "team_size": len(priced),
            "rate_card_version_id": structured["rate_card_version_id"],
            "has_sentinel_costs": structured["has_sentinel_costs"],
        },
    )
    await session.commit()
    await session.refresh(row)

    return Estimate(
        id=row.id,
        submitted_at=row.submitted_at.isoformat(),
        submitted_by=row.submitted_by,
        label=row.label,
        scope=draft.scope,
        confidence=draft.confidence,
        reasons=draft.reasons,
        team=priced,
        cost_low=total_low,
        cost_base=total_base,
        cost_high=total_high,
        options=options,
        sources=draft.sources,
        model=row.model,
        prompt_version=row.prompt_version,
        inputs=inputs,
        rate_card_version_id=(rate_card.id if rate_card is not None else None),
        has_sentinel_costs=structured["has_sentinel_costs"],
        reviewer_id=row.reviewer_id,
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


async def load_estimate(
    session: AsyncSession, estimate_id: uuid.UUID
) -> AdviserEstimate | None:
    stmt = select(AdviserEstimate).where(AdviserEstimate.id == estimate_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_estimates(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID | None,
    page: int,
    size: int,
) -> tuple[list[AdviserEstimate], int]:
    stmt = select(AdviserEstimate)
    if owner_id is not None:
        stmt = stmt.where(AdviserEstimate.submitted_by == owner_id)
    stmt = stmt.order_by(AdviserEstimate.submitted_at.desc())
    rows = list((await session.execute(stmt)).scalars().all())
    total = len(rows)
    offset = max(0, (page - 1) * size)
    return rows[offset : offset + size], total


def serialize_row(row: AdviserEstimate) -> dict[str, Any]:
    """Full serialisation of a persisted row for GET /adviser/estimates/{id}."""

    structured = dict(row.structured_output or {})
    return {
        "kind": "estimate",
        "id": str(row.id),
        "submitted_by": str(row.submitted_by) if row.submitted_by else None,
        "submitted_at": row.submitted_at.isoformat(),
        "label": row.label,
        "scope": structured.get("scope", ""),
        "confidence": structured.get("confidence", ""),
        "reasons": structured.get("reasons", []),
        "team": structured.get("team", []),
        "cost_low": structured.get("cost_low"),
        "cost_base": structured.get("cost_base"),
        "cost_high": structured.get("cost_high"),
        "options": structured.get("options", []),
        "sources": row.sources or [],
        "model": row.model,
        "prompt_version": row.prompt_version,
        "inputs": row.inputs,
        "rate_card_version_id": structured.get("rate_card_version_id"),
        "has_sentinel_costs": structured.get("has_sentinel_costs", False),
        "reviewer_id": str(row.reviewer_id) if row.reviewer_id else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


__all__ = [
    "DeliveryOption",
    "Estimate",
    "PricedMember",
    "Questions",
    "SENTINEL_COST_BAND",
    "estimate",
    "list_estimates",
    "load_estimate",
    "serialize_row",
]
