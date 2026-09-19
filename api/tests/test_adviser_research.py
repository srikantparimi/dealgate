"""S7 wave 2 — Adviser real web research (Tavily) + public/confidential split.

These tests exercise the new public-research pass in
:mod:`app.services.adviser` and the guardrail helper
:func:`app.services.adviser.public_search_terms`. The confidentiality
assertion (secret text never reaches Tavily) is the load-bearing one — it
enforces Blueprint §5's public/confidential split at the service boundary.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.integrations.tavily import Source, StubTavily
from app.models.adviser_estimate import AdviserEstimate
from app.services.adviser import (
    Estimate,
    Questions,
    estimate as run_estimate,
    public_search_terms,
)


# --- helpers ---------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
def _no_tavily_env(monkeypatch):
    """Ensure the real Tavily key is never read during tests."""

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("DEALGATE_ENV", "local")


def _rich_intake() -> dict:
    return {
        "client_name": "Acme Widgets",
        "website": "https://acme.com/about",
        "industry": "Manufacturing",
        "problem": (
            "Replace a bespoke internal quoting tool with a modern app "
            "used by sales and delivery teams across three regions."
        ),
        "functions": ["quoting", "approvals", "reporting"],
        "users_count": 250,
        "systems": ["Salesforce", "NetSuite"],
        "geography": "Global",
        "timeline": "9 months",
    }


def _canned_sources() -> list[Source]:
    return [
        {
            "url": f"https://example.com/story-{i}",
            "title": f"Acme story {i}",
            "snippet": f"Public snippet number {i} about Acme.",
        }
        for i in range(1, 6)
    ]


# --- public_search_terms ---------------------------------------------------


def test_public_search_terms_never_includes_confidential_text():
    """The guardrail: confidential intake fields NEVER reach the query."""

    inputs = {
        "client_name": "Acme",
        "website": "acme.com",
        "problem": "secret confidential info about acquisition targets",
        "notes": "internal cost breakdown, do not share",
        "budget": "500000 USD internal",
    }
    terms = public_search_terms(inputs)

    assert terms, "must return at least the client name term"
    joined = " ".join(terms).lower()
    for banned in ("secret", "confidential", "acquisition", "internal", "500000"):
        assert banned not in joined, f"leaked {banned!r} into public search terms"
    # And the client name / website do come through.
    assert any("Acme" in t for t in terms)
    assert any("acme.com" in t for t in terms)


def test_public_search_terms_includes_industry_and_geography_when_public():
    terms = public_search_terms(
        {
            "client_name": "Globex",
            "industry": "Insurance",
            "geography": "UK",
        }
    )
    assert terms
    assert "Globex" in terms[0]
    # Industry + geography are public and safe to include.
    assert "Insurance" in terms[0]
    assert "UK" in terms[0]


def test_public_search_terms_empty_when_no_client_name():
    assert public_search_terms({"problem": "anything"}) == []


def test_public_search_terms_normalises_website_to_bare_domain():
    terms = public_search_terms(
        {"client_name": "Acme", "website": "https://acme.com/company"}
    )
    assert "acme.com" in terms
    # No scheme, no path.
    assert "https://acme.com/company" not in terms


# --- happy path -----------------------------------------------------------


async def test_estimate_populates_sources_from_tavily(session):
    """Tavily returns 5 canned results → estimate has 5 sources + ok status."""

    stub = StubTavily(results=_canned_sources())
    result = await run_estimate(
        session,
        actor_id=uuid.uuid4(),
        inputs=_rich_intake(),
        tavily=stub,
    )
    assert isinstance(result, Estimate), "rich intake should produce a team"
    body = result.serialize()
    assert body["research_status"] == "ok"
    assert len(body["sources"]) == 5
    for src in body["sources"]:
        assert set(src.keys()) >= {"url", "title", "snippet"}

    # And Tavily was called with the *public* query, not any confidential text.
    assert stub.calls, "estimate() must call Tavily"
    query = stub.calls[0]["query"]
    assert "Acme Widgets" in query
    assert "quoting tool" not in query  # from confidential problem statement
    assert "bespoke" not in query


async def test_estimate_persists_research_status_and_sources(session):
    stub = StubTavily(results=_canned_sources())
    result = await run_estimate(
        session,
        actor_id=uuid.uuid4(),
        inputs=_rich_intake(),
        tavily=stub,
    )
    assert isinstance(result, Estimate)
    row = (
        await session.execute(
            select(AdviserEstimate).where(AdviserEstimate.id == result.id)
        )
    ).scalar_one()
    assert row.research_status == "ok"
    assert row.sources is not None
    assert len(row.sources) == 5


# --- unavailable branches -------------------------------------------------


async def test_estimate_marks_status_unavailable_when_tavily_empty(session):
    """StubTavily returns [] → estimate proceeds; sources=[], status=unavailable."""

    stub = StubTavily(results=[])  # simulate no results / missing key
    result = await run_estimate(
        session,
        actor_id=uuid.uuid4(),
        inputs=_rich_intake(),
        tavily=stub,
    )
    assert isinstance(result, Estimate)
    body = result.serialize()
    assert body["research_status"] == "unavailable"
    assert body["sources"] == []


async def test_estimate_marks_status_unavailable_when_tavily_raises(session):
    """Upstream failure must NOT crash the estimate; status = unavailable."""

    stub = StubTavily(fail_with="tavily 500")
    result = await run_estimate(
        session,
        actor_id=uuid.uuid4(),
        inputs=_rich_intake(),
        tavily=stub,
    )
    assert isinstance(result, Estimate)
    body = result.serialize()
    assert body["research_status"] == "unavailable"
    # Critical: no invented sources when upstream fails.
    assert body["sources"] == []


# --- thin intake still calls Tavily ---------------------------------------


async def test_thin_intake_still_queries_tavily_then_returns_questions(session):
    """A thin intake (only client_name) still triggers the public search — the
    query is safe (client name only) — and the LLM still returns clarifying
    questions because the confidential problem statement is missing detail.
    """

    stub = StubTavily(results=_canned_sources())
    result = await run_estimate(
        session,
        actor_id=uuid.uuid4(),
        inputs={"client_name": "Mystery Co", "problem": "Help us."},
        tavily=stub,
    )
    assert isinstance(result, Questions), "thin intake should ask questions"
    assert stub.calls, "Tavily should still be called on thin intake"
    query = stub.calls[0]["query"]
    assert "Mystery Co" in query
    # Only the client name — no confidential problem text.
    assert "Help us" not in query
