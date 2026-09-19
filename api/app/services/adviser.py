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
from app.integrations.bedrock_embeddings import Embedder, default_embedder
from app.integrations.tavily import Source, TavilyClient, get_tavily_client
from app.models.adviser_estimate import DEFAULT_LABEL, AdviserEstimate
from app.services.embeddings import search_capabilities, search_sow
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
    # Public web-research outcome for this estimate. "ok" when Tavily
    # returned at least one citation; "unavailable" when the key is missing
    # or the upstream call failed. Never invented (Blueprint rule 6).
    research_status: str = "unavailable"
    # S7 wave 2: snapshot of the past-SOW + capability catalog matches
    # the LLM saw for this estimate. ``{"past_sows": [...],
    # "capabilities": [...]}`` (both lists may be empty). Persisted on
    # ``adviser_estimate.retrieved`` for audit / debug.
    retrieved: dict[str, Any] = field(default_factory=dict)

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
            "research_status": self.research_status,
            "retrieved": dict(self.retrieved or {}),
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
    research_status: str = "unavailable"

    def serialize(self) -> dict[str, Any]:
        return {
            "kind": "questions",
            "questions": list(self.questions),
            "note": self.note,
            "label": self.label,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "sources": list(self.sources),
            "research_status": self.research_status,
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


# --- public research -------------------------------------------------------

# Confidential fields — MUST NEVER end up in a Tavily query. The intake
# schema (routers/adviser.py::AdviserIntake) may add more free-text fields
# over time; keeping this list explicit makes the guardrail auditable.
_CONFIDENTIAL_INTAKE_KEYS: frozenset[str] = frozenset(
    {"problem", "notes", "budget", "attachments"}
)


def public_search_terms(inputs: dict[str, Any]) -> list[str]:
    """Return the *public* search terms for an intake, in query order.

    Blueprint §5 guardrail: public research and confidential uploads run in
    separate steps. Client-confidential text (``problem``, ``notes``,
    ``budget``, uploads) is never put into a search query. This helper is
    the single choke-point — the adviser service calls it and passes the
    result verbatim to Tavily.

    The first term is always ``"{client_name} company overview"`` (with an
    optional ``{industry}``/``{geography}`` suffix); a second term is the
    bare website domain when supplied. Absent client_name → ``[]`` (Tavily
    then returns [] and the caller flags ``research_status=unavailable``).
    """

    client_name = str(inputs.get("client_name") or "").strip()
    if not client_name:
        return []

    # Public suffix: prefer industry over geography (industry is a stronger
    # search signal). Both are optional; both are public.
    suffix_parts: list[str] = []
    for key in ("industry", "geography"):
        val = inputs.get(key)
        if isinstance(val, str) and val.strip():
            suffix_parts.append(val.strip())
    primary = f"{client_name} company overview"
    if suffix_parts:
        primary = f"{primary} {' '.join(suffix_parts)}"

    terms: list[str] = [primary]

    website = inputs.get("website")
    if isinstance(website, str) and website.strip():
        # Bare domain only — no path, no query string. Tavily indexes the
        # domain itself well.
        domain = website.strip()
        for prefix in ("https://", "http://"):
            if domain.lower().startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.split("/", 1)[0].strip()
        if domain:
            terms.append(domain)

    # Belt: assert we didn't accidentally pick up a confidential value.
    lowered_terms = " ".join(terms).lower()
    for key in _CONFIDENTIAL_INTAKE_KEYS:
        val = inputs.get(key)
        if isinstance(val, str) and val.strip():
            for word in val.split():
                if len(word) < 4:
                    continue
                assert word.lower() not in lowered_terms, (
                    f"public_search_terms leaked confidential value from {key!r}"
                )
    return terms


async def _run_retrieval(
    session: AsyncSession,
    inputs: dict[str, Any],
    embedder: Embedder | None,
) -> dict[str, Any]:
    """Run past-SOW + capability retrieval on the intake ``problem``.

    Returns ``{"past_sows": [...], "capabilities": [...]}`` (both lists
    may be empty). Never raises: a search failure logs and falls back to
    empty lists so the estimate is not blocked on the retrieval layer —
    matching Blueprint rule 6.
    """

    problem = str(inputs.get("problem") or "").strip()
    if not problem:
        return {"past_sows": [], "capabilities": []}
    emb = embedder or default_embedder()
    try:
        past_sows = await search_sow(
            session, embedder=emb, query_text=problem, top_k=5
        )
    except Exception:
        past_sows = []
    try:
        capabilities = await search_capabilities(
            session, embedder=emb, query_text=problem, top_k=5
        )
    except Exception:
        capabilities = []
    return {"past_sows": past_sows, "capabilities": capabilities}


async def _run_public_research(
    inputs: dict[str, Any], tavily: TavilyClient | None
) -> tuple[list[Source], str]:
    """Call Tavily with the public search terms and return (sources, status).

    Never raises: any exception is swallowed and reported as
    ``research_status = "unavailable"``. The service continues without
    public sources rather than blocking the estimate — Blueprint rule 6.
    """

    terms = public_search_terms(inputs)
    if not terms:
        return [], "unavailable"
    client = tavily or get_tavily_client()
    query = terms[0]
    try:
        results = await client.search(query, max_results=5)
    except Exception:
        return [], "unavailable"
    if not results:
        return [], "unavailable"
    return list(results), "ok"


# --- public entry ----------------------------------------------------------


async def estimate(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    inputs: dict[str, Any],
    adapter: Adviser | None = None,
    tavily: TavilyClient | None = None,
    embedder: Embedder | None = None,
) -> Estimate | Questions:
    """Draft, price and persist one opportunity estimate.

    Returns an :class:`Estimate` (persisted) or a :class:`Questions` payload
    (nothing persisted — the LLM asked for more information).

    The flow is: (1) call Tavily with the *public* search terms to gather
    background on the client, (2) query pgvector for the top past-SOW
    chunks + capability-catalog matches on the confidential ``problem``
    string, (3) hand *all three* (public research, retrieved refs,
    confidential intake) to Bedrock, (4) price the resulting team
    deterministically. When any upstream is unavailable the estimate
    still runs — Blueprint rule 6: never block on external context,
    never invent sources.
    """

    public_sources, research_status = await _run_public_research(inputs, tavily)

    # S7 wave 2: embed the confidential ``problem`` string and pull the
    # top-5 past-SOW chunks + capability matches. Failures degrade
    # silently to an empty retrieval so the estimate still runs.
    retrieved = await _run_retrieval(session, inputs, embedder)

    draft: ProposeResult = propose_team(
        inputs,
        adapter=adapter,
        public_research=list(public_sources),
        retrieved=retrieved,
    )

    if isinstance(draft, ClarifyingQuestions):
        return Questions(
            questions=draft.questions,
            note=draft.note,
            model=draft.model,
            prompt_version=draft.prompt_version,
            sources=tuple(public_sources) or draft.sources,
            research_status=research_status,
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
        "research_status": research_status,
    }

    # Prefer public research citations (from Tavily) over anything the
    # adapter might have echoed back. The stub adapter never invents
    # sources; the real one is instructed not to. Belt + braces.
    sources_out: tuple[dict[str, Any], ...] = (
        tuple(public_sources) if public_sources else tuple(draft.sources)
    )

    row = AdviserEstimate(
        id=uuid.uuid4(),
        submitted_by=actor_id,
        inputs=inputs,
        structured_output=structured,
        sources=list(sources_out),
        model=draft.model,
        prompt_version=draft.prompt_version,
        label=DEFAULT_LABEL,
        research_status=research_status,
        retrieved=retrieved,
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
            "research_status": research_status,
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
        sources=sources_out,
        model=row.model,
        prompt_version=row.prompt_version,
        inputs=inputs,
        rate_card_version_id=(rate_card.id if rate_card is not None else None),
        has_sentinel_costs=structured["has_sentinel_costs"],
        reviewer_id=row.reviewer_id,
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
        research_status=research_status,
        retrieved=dict(retrieved),
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
        # Prefer the dedicated column but fall back to the structured_output
        # blob for rows written by intermediate builds during the sprint.
        "research_status": (
            row.research_status
            or structured.get("research_status")
        ),
        "retrieved": dict(row.retrieved or {}),
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
    "public_search_terms",
    "serialize_row",
]
