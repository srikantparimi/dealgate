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
    # S13a follow-up: archived clients never resurrect from a fresh
    # upload (fresh-start rule), but if the incoming name would match
    # an archived record we surface it as a non-blocking informational
    # note so the audit trail stays connected. Same pattern as the
    # archived-SOW duplicate note in ``sow_upload_job_service``.
    archived_matches: list[Candidate] = field(default_factory=list)
    info: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution": self.resolution,
            "client_id": str(self.client_id) if self.client_id else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "create_new": self.create_new,
            "reason": self.reason,
            "archived_matches": [c.to_dict() for c in self.archived_matches],
            "info": self.info,
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


_POSSESSIVE = re.compile(r"[’']s\b", re.IGNORECASE)
# Punctuation includes the em-dash and en-dash — names copied from PDFs
# often use the typographic forms rather than a plain hyphen.
_PUNCT = re.compile(r"[.,;:!?\"()/\-_–—]+")

# Entity-form suffixes stripped from the tail of a legal name for matching
# only (never for display). Punctuation is already collapsed by `_PUNCT`
# above, so the suffixes are listed in their space-separated form (e.g.
# "l l c" rather than "l.l.c.") — the tail-strip below runs on tokens.
# Ordered so multi-word forms are attempted before single-word ones they
# contain.
_ENTITY_SUFFIXES: tuple[str, ...] = (
    "limited liability company",
    "public limited company",
    "sociedad anonima",
    "societe anonyme",
    "societa a responsabilita limitata",
    "aktiengesellschaft",
    "gesellschaft mit beschrankter haftung",
    "corporation",
    "incorporated",
    "company",
    "limited",
    "gmbh",
    "pty ltd",
    "co ltd",
    "l l c",
    "l l p",
    "p l c",
    "s a",
    "s r l",
    "s r o",
    "llc",
    "inc",
    "corp",
    "ltd",
    "llp",
    "plc",
    "co",
    "sa",
    "ag",
    "srl",
    "pty",
)


def _strip_entity_suffix(tokens: list[str]) -> list[str]:
    """Peel off any trailing entity-form suffix ("llc", "corp", ...).

    Runs iteratively so a name like "Peppermill Casino's, LLC, Inc" (rare
    but real) sheds both suffixes. The stripped list never falls below one
    token — a bare "LLC" wouldn't match anything anyway, and losing it
    entirely would score every one-word name as identical.
    """

    joined = " ".join(tokens)
    changed = True
    while changed and len(tokens) > 1:
        changed = False
        for suffix in _ENTITY_SUFFIXES:
            if joined.endswith(" " + suffix) or joined == suffix:
                joined = joined[: len(joined) - len(suffix)].strip()
                tokens = joined.split()
                changed = True
                break
    return tokens


def _norm(text: str) -> str:
    """Canonicalise a legal name for scoring: lowercase, strip possessives,
    strip punctuation, drop entity-form suffixes, collapse whitespace.

    ``Peppermill Casino's, LLC`` and ``Peppermill Casino`` both canonicalise
    to ``peppermill casino``, so the exact-match and fuzzy branches score
    them as one entity (S13a directive §2.1).
    """

    lowered = text.lower()
    # Possessive first so "casino's" becomes "casino" before the punctuation
    # pass eats the apostrophe entirely.
    lowered = _POSSESSIVE.sub("", lowered)
    lowered = _PUNCT.sub(" ", lowered)
    tokens = lowered.split()
    tokens = _strip_entity_suffix(tokens)
    return " ".join(tokens)


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

    # S13a: two parallel scoring buckets. `scored` holds LIVE clients
    # (the only ones eligible to auto-match); `archived` holds clients
    # whose `archived_at IS NOT NULL` so we can attach an informational
    # note without resurrecting the record (fresh-start rule).
    scored: dict[uuid.UUID, Candidate] = {}
    archived: dict[uuid.UUID, Candidate] = {}
    normalised_name = _norm(signals.legal_name)

    def _score_row(
        row: Client, score: float, reason: str
    ) -> None:
        if row.archived_at is None:
            _bump(scored, row.id, row.name, score, reason)
        else:
            _bump(archived, row.id, row.name, score, reason)

    # 1. Exact legal-name match.
    exact_stmt = select(Client).where(Client.name.ilike(signals.legal_name))
    exact_rows = (await session.execute(exact_stmt)).scalars().all()
    for row in exact_rows:
        if _norm(row.name) == normalised_name:
            _score_row(row, 1.0, "exact_name")

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
                _score_row(client, 0.95, "domain")
        # Also try hubspot_company_id equal to the domain — some tenants
        # use the domain as the natural key.
        hs_stmt = select(Client).where(
            Client.hubspot_company_id.in_(list(domain_variants))
        )
        for row in (await session.execute(hs_stmt)).scalars().all():
            _score_row(row, 0.95, "domain")

    # 3. Alias match on the extracted legal name.
    alias_name_stmt = select(ClientAlias, Client).join(
        Client, Client.id == ClientAlias.client_id
    )
    for alias, client in (await session.execute(alias_name_stmt)).all():
        if _norm(alias.alias) == normalised_name:
            _score_row(client, 0.9, "alias")

    # 4. Fuzzy sweep across the freshest N clients (live + archived,
    #    then split by archived_at when scoring).
    fuzzy_stmt = (
        select(Client)
        .order_by(Client.created_at.desc(), Client.id.desc())
        .limit(scan_limit)
    )
    for row in (await session.execute(fuzzy_stmt)).scalars().all():
        ratio = fuzz.token_sort_ratio(normalised_name, _norm(row.name)) / 100.0
        if ratio >= MATCH_SCORE_MIN:
            _score_row(row, ratio, "fuzzy_name")

    ordered = sorted(scored.values(), key=lambda c: c.score, reverse=True)
    ordered_archived = sorted(
        archived.values(), key=lambda c: c.score, reverse=True
    )

    # Informational note when the best archived match is a strong candidate
    # — non-blocking, does not resurrect the record.
    info_note: str | None = None
    top_archived_matches: list[Candidate] = []
    if ordered_archived and ordered_archived[0].score >= MATCH_SCORE_MIN:
        top_archived_matches = ordered_archived[:3]
        info_note = (
            f"matches archived client {ordered_archived[0].name!r} "
            f"(score {ordered_archived[0].score:.2f}) — not resurrected"
        )

    if not ordered:
        return ResolutionResult(
            resolution="needs_pick",
            candidates=[],
            create_new=create_new,
            reason="no candidates above 0.85",
            archived_matches=top_archived_matches,
            info=info_note,
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
            archived_matches=top_archived_matches,
            info=info_note,
        )

    return ResolutionResult(
        resolution="needs_pick",
        candidates=ordered[:3],
        create_new=create_new,
        reason=(
            f"top={top.score:.2f} gap={top.score - second:.2f} — below match"
            f" threshold ({MATCH_SCORE_MIN} with gap {MATCH_SCORE_GAP})"
        ),
        archived_matches=top_archived_matches,
        info=info_note,
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
