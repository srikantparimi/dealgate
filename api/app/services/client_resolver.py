"""Client resolver (S10-01).

Turns the client signals the SOW extractor lifted (``legal_name``,
``domain``, ``aliases``, ``address_lines``) into either a definitive
``client_id`` (``resolution="matched"``) or a picker payload
(``resolution="needs_pick"``) that the reviewer chooses from.

Matching order (per ``docs/backlog/s10-sow-upload.md``):

1. Exact legal-name match against ``client.name``      → score 1.0.
2. Domain match — a ``client_alias`` row whose alias is either the raw
   domain or the domain with the tld stripped, or a hubspot_company_id
   that includes the domain                            → score 0.95.
3. Alias match (``client_alias.alias`` case-insensitive equal to the
   extracted legal name)                               → score 0.9.
4. Rapidfuzz token_sort_ratio between the extracted legal_name and
   ``client.name`` for the top few hundred rows        → score >= 0.85
   qualifies.

A "matched" resolution requires the top score is at least ``0.85`` AND
at least ``0.15`` above the second score, so a near-tie always drops to
``needs_pick`` and the human chooses.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.client_alias import ClientAlias


# Score thresholds. Kept as constants (not env vars) — this is a
# functional decision, not an operations knob. If we ever need to
# ratchet it we bump the value with a code change + test.
MATCH_SCORE_MIN = 0.85
MATCH_SCORE_GAP = 0.15


@dataclass(frozen=True)
class ClientSignals:
    """The subset of extracted fields the resolver reads."""

    legal_name: str | None = None
    domain: str | None = None
    aliases: tuple[str, ...] = ()
    address_lines: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ClientSignals:
        payload = payload or {}
        aliases_raw = payload.get("aliases") or []
        address_raw = payload.get("address_lines") or []
        return cls(
            legal_name=_to_str(payload.get("legal_name")),
            domain=_to_str(payload.get("domain")),
            aliases=tuple(_to_str(a) or "" for a in aliases_raw if _to_str(a)),
            address_lines=tuple(
                _to_str(a) or "" for a in address_raw if _to_str(a)
            ),
        )

    def to_create_new(self) -> dict[str, Any]:
        """Pre-filled `create_new` block for the picker."""

        return {
            "legal_name": self.legal_name,
            "domain": self.domain,
            "address_lines": list(self.address_lines),
        }


@dataclass
class Candidate:
    client_id: uuid.UUID
    name: str
    score: float
    reason: str  # "exact_name" | "domain" | "alias" | "fuzzy_name"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["client_id"] = str(self.client_id)
        d["score"] = round(self.score, 4)
        return d


@dataclass
class ResolutionResult:
    resolution: str  # "matched" | "needs_pick"
    client_id: uuid.UUID | None = None
    candidates: list[Candidate] = field(default_factory=list)
    create_new: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution": self.resolution,
            "client_id": str(self.client_id) if self.client_id else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "create_new": self.create_new,
            "reason": self.reason,
        }


# --- helpers --------------------------------------------------------------


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_DOMAIN_TAIL = re.compile(r"\.[a-z]{2,}$", re.IGNORECASE)


def _domain_stem(domain: str) -> str:
    """"acme.co.uk" → "acme". Lossy on purpose — good enough to match
    aliases like ``["Acme"]``."""

    stem = domain.lower()
    stem = _DOMAIN_TAIL.sub("", stem)
    # Strip subdomains: keep the last dotted segment.
    if "." in stem:
        stem = stem.split(".")[-1]
    return stem.strip()


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


# --- resolver -------------------------------------------------------------


async def resolve_client(
    session: AsyncSession,
    signals: ClientSignals,
    *,
    scan_limit: int = 500,
) -> ResolutionResult:
    """Score every candidate and pick a winner (or route to the picker).

    ``scan_limit`` caps the fuzzy-match sweep so a five-figure client
    table doesn't turn into a slow scan. The scan is ordered by created_at
    DESC so freshly-added clients rank first — the most likely target for
    a brand-new SOW.
    """

    create_new = signals.to_create_new()

    if signals.legal_name is None:
        return ResolutionResult(
            resolution="needs_pick",
            candidates=[],
            create_new=create_new,
            reason="no legal_name extracted from SOW",
        )

    scored: dict[uuid.UUID, Candidate] = {}
    normalised_name = _norm(signals.legal_name)

    # 1. Exact legal-name match.
    exact_stmt = select(Client).where(Client.name.ilike(signals.legal_name))
    exact_rows = (await session.execute(exact_stmt)).scalars().all()
    for row in exact_rows:
        if _norm(row.name) == normalised_name:
            _bump(scored, row.id, row.name, 1.0, "exact_name")

    # 2. Domain match via client_alias.
    if signals.domain:
        stem = _domain_stem(signals.domain)
        domain_variants = {signals.domain.lower(), stem} - {""}
        alias_stmt = select(ClientAlias, Client).join(
            Client, Client.id == ClientAlias.client_id
        )
        alias_rows = (await session.execute(alias_stmt)).all()
        for alias, client in alias_rows:
            alias_norm = _norm(alias.alias)
            if alias_norm in domain_variants:
                _bump(scored, client.id, client.name, 0.95, "domain")
        # Also try hubspot_company_id equal to the domain — some tenants
        # use the domain as the natural key.
        hs_stmt = select(Client).where(
            Client.hubspot_company_id.in_(list(domain_variants))
        )
        for row in (await session.execute(hs_stmt)).scalars().all():
            _bump(scored, row.id, row.name, 0.95, "domain")

    # 3. Alias match on the extracted legal name.
    alias_name_stmt = select(ClientAlias, Client).join(
        Client, Client.id == ClientAlias.client_id
    )
    for alias, client in (await session.execute(alias_name_stmt)).all():
        if _norm(alias.alias) == normalised_name:
            _bump(scored, client.id, client.name, 0.9, "alias")

    # 4. Fuzzy sweep across the freshest N clients.
    fuzzy_stmt = (
        select(Client)
        .order_by(Client.created_at.desc(), Client.id.desc())
        .limit(scan_limit)
    )
    for row in (await session.execute(fuzzy_stmt)).scalars().all():
        ratio = fuzz.token_sort_ratio(normalised_name, _norm(row.name)) / 100.0
        if ratio >= 0.85:
            _bump(scored, row.id, row.name, ratio, "fuzzy_name")

    ordered = sorted(scored.values(), key=lambda c: c.score, reverse=True)

    if not ordered:
        return ResolutionResult(
            resolution="needs_pick",
            candidates=[],
            create_new=create_new,
            reason="no candidates above 0.85",
        )

    top = ordered[0]
    second = ordered[1].score if len(ordered) > 1 else 0.0

    if top.score >= MATCH_SCORE_MIN and (top.score - second) >= MATCH_SCORE_GAP:
        return ResolutionResult(
            resolution="matched",
            client_id=top.client_id,
            candidates=ordered[:3],
            create_new=create_new,
            reason=top.reason,
        )

    return ResolutionResult(
        resolution="needs_pick",
        candidates=ordered[:3],
        create_new=create_new,
        reason=(
            f"top={top.score:.2f} gap={top.score - second:.2f} — below match"
            f" threshold ({MATCH_SCORE_MIN} with gap {MATCH_SCORE_GAP})"
        ),
    )


def _bump(
    bucket: dict[uuid.UUID, Candidate],
    client_id: uuid.UUID,
    name: str,
    score: float,
    reason: str,
) -> None:
    """Keep the best score per client and remember which rule found it."""

    existing = bucket.get(client_id)
    if existing is None or score > existing.score:
        bucket[client_id] = Candidate(
            client_id=client_id, name=name, score=score, reason=reason
        )


__all__ = [
    "Candidate",
    "ClientSignals",
    "MATCH_SCORE_GAP",
    "MATCH_SCORE_MIN",
    "ResolutionResult",
    "resolve_client",
]
