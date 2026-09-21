"""S13a §2.1 — client-matcher normalisation.

The Pipeline clients screenshot shipped with the S13a directive shows
two rows for the same company:

- "Peppermill Casino (S12 1789936428334)"  (created by S12's Playwright)
- "Peppermill Casino's, LLC"                (a real upload)

The second should have matched the first (or its `Peppermill Casino`
core) with score ≥ 0.85 and never opened a second client. The failure
was the possessive apostrophe and the trailing `LLC` bypassing the
normaliser, so `token_sort_ratio` scored the pair below the threshold.

`_norm` now strips possessives, punctuation and standard entity-form
suffixes before scoring. These tests pin the canonicalisation so a
future edit doesn't reintroduce the split.
"""

from __future__ import annotations

import uuid

import pytest
from rapidfuzz import fuzz
from sqlalchemy import select

from app.models.client import Client
from app.services.client_resolver import (
    ClientSignals,
    _norm,
    resolve_client,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Peppermill Casino", "peppermill casino"),
        ("Peppermill Casino's, LLC", "peppermill casino"),
        ("Peppermill Casino’s, LLC", "peppermill casino"),  # curly apostrophe
        ("PEPPERMILL CASINO, INC.", "peppermill casino"),
        ("Peppermill Casino Corporation", "peppermill casino"),
        ("Acme Widgets Co., Ltd.", "acme widgets"),
        ("Foo Bar GmbH", "foo bar"),
        ("Baz S.A.", "baz"),
        # A one-token name that IS the suffix keeps at least one token — a
        # bare "LLC" wouldn't match anything and losing it entirely would
        # score every one-word name as identical.
        ("LLC", "llc"),
        # Multi-suffix (rare) sheds both.
        ("Foo LLC, Inc", "foo"),
        # Punctuation collapses to space; whitespace collapses.
        ("Foo   —  Bar", "foo bar"),
    ],
)
def test_norm_canonicalises_common_shapes(raw: str, expected: str):
    assert _norm(raw) == expected


def test_possessive_llc_pair_scores_1_0():
    """The exact case the directive named. Both forms canonicalise to
    the same three tokens, so token_sort_ratio is 100."""

    ratio = fuzz.token_sort_ratio(
        _norm("Peppermill Casino"),
        _norm("Peppermill Casino's, LLC"),
    )
    assert ratio == 100


@pytest.mark.asyncio
async def test_resolve_client_matches_across_possessive_and_llc(session):
    """End-to-end via the resolver: a client seeded as `Peppermill Casino`
    matches a signal that says `Peppermill Casino's, LLC` at score ≥ 0.85
    with resolution `matched` (not `needs_pick`).
    """

    existing = Client(
        id=uuid.uuid4(),
        name="Peppermill Casino",
        hubspot_company_id=None,
    )
    session.add(existing)
    await session.commit()

    result = await resolve_client(
        session,
        ClientSignals.from_dict(
            {
                "legal_name": "Peppermill Casino's, LLC",
                "domain": None,
                "aliases": [],
                "address_lines": [],
            }
        ),
    )

    assert result.resolution == "matched", (
        f"expected matched; got {result.resolution!r} with candidates "
        f"{[(c.name, c.score) for c in result.candidates]}"
    )
    assert result.candidates
    top = result.candidates[0]
    assert top.client_id == existing.id
    assert top.score >= 0.85, top.score


@pytest.mark.asyncio
async def test_resolve_client_ignores_archived_and_notes_the_match(session):
    """S13a fresh-start rule + informational note.

    Archive a client, then re-upload a SOW that would otherwise match by
    name. The resolver must NOT auto-match (fresh client is created via
    ``needs_pick``) but must attach an ``info`` string + ``archived_matches``
    entry so the audit trail stays connected.
    """

    from datetime import UTC, datetime

    archived = Client(
        id=uuid.uuid4(),
        name="Peppermill Casino",
        hubspot_company_id=None,
        archived_at=datetime.now(UTC),
        archived_by=None,
        archived_reason="e2e archive",
    )
    session.add(archived)
    await session.commit()

    result = await resolve_client(
        session,
        ClientSignals.from_dict(
            {
                "legal_name": "Peppermill Casino's, LLC",
                "domain": None,
                "aliases": [],
                "address_lines": [],
            }
        ),
    )

    # Live scoring bucket empty → needs_pick, so a new client is created.
    assert result.resolution == "needs_pick", (
        f"expected needs_pick (archived should not resurrect); got "
        f"{result.resolution!r} with candidates "
        f"{[(c.name, c.score) for c in result.candidates]}"
    )
    assert result.candidates == [], result.candidates
    # Non-blocking informational note surfaces the archived match.
    assert result.archived_matches, result.archived_matches
    top_archived = result.archived_matches[0]
    assert top_archived.client_id == archived.id
    assert top_archived.score >= 0.85, top_archived.score
    assert result.info and "archived" in result.info.lower(), result.info
