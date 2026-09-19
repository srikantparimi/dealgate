"""Embedding pipeline — chunker, SOW embed idempotency, ranked search.

Uses the deterministic :class:`StubEmbeddings` adapter so tests never
touch the real Bedrock model. The SQLite fallback path is exercised
end-to-end (Postgres+pgvector is covered in the CI matrix; the story
requires SQLite to keep the app tests portable).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.integrations.bedrock_embeddings import StubEmbeddings
from app.models.capability import CapabilityCatalog
from app.models.embedding import SowEmbedding
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.embeddings import (
    chunk_text,
    embed_capability,
    embed_sow_version,
    search_capabilities,
    search_sow,
)


# --- chunker -------------------------------------------------------------


def test_chunk_text_empty_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   \n\t  ") == []


def test_chunk_text_preserves_word_boundaries():
    text = "one two three four five six seven eight nine ten"
    chunks = chunk_text(text, size=15, overlap=0)
    # Every chunk should be non-empty and contain whole words only.
    for c in chunks:
        assert c.strip() == c
        for word in c.split():
            assert word in text.split()
    assert " ".join(chunks).count("one") == 1  # zero overlap -> no dupes


def test_chunk_text_overlap_repeats_boundary():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    chunks = chunk_text(text, size=20, overlap=8)
    assert len(chunks) >= 2
    # With overlap > 0 some words appear in more than one chunk.
    combined_words = []
    for c in chunks:
        combined_words.extend(c.split())
    assert len(combined_words) > len(text.split())


def test_chunk_text_bounds_check():
    with pytest.raises(ValueError):
        chunk_text("hello", size=0)
    with pytest.raises(ValueError):
        chunk_text("hello", size=10, overlap=10)


# --- fixtures -------------------------------------------------------------


@pytest_asyncio.fixture
async def opp_with_sow_version(session):
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="123",
        governance_status="Intake.new",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        file_s3_key="s3://k",
        file_hash="h",
        extract_status="complete",
        extracted_fields={
            "scope_summary": {
                "value": (
                    "Replace bespoke quoting tool with a modern web app used by "
                    "sales and delivery teams across three regions."
                ),
                "page_ref": 1,
                "status": "confirmed",
            },
            "deliverables": {
                "value": [
                    "Discovery + backlog for quoting workflow",
                    "Modern React frontend replacing legacy quoting UI",
                    "Integration with NetSuite for pricing lookups",
                ],
                "page_ref": 2,
                "status": "confirmed",
            },
        },
    )
    session.add(version)
    await session.flush()
    return version


# --- embed_sow_version idempotency ---------------------------------------


@pytest.mark.asyncio
async def test_embed_sow_version_is_idempotent(session, opp_with_sow_version):
    embedder = StubEmbeddings()
    version = opp_with_sow_version

    rows_first = await embed_sow_version(
        session, sow_version_id=version.id, embedder=embedder
    )
    assert rows_first, "expected at least one chunk row"
    first_ids = {r.id for r in rows_first}

    # Second run should be a no-op — no extra rows.
    rows_second = await embed_sow_version(
        session, sow_version_id=version.id, embedder=embedder
    )
    assert {r.id for r in rows_second} == first_ids

    total = (
        await session.execute(
            select(SowEmbedding).where(SowEmbedding.sow_version_id == version.id)
        )
    ).scalars().all()
    assert len(total) == len(rows_first)


@pytest.mark.asyncio
async def test_embed_sow_version_no_extract_returns_empty(session):
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="999",
        governance_status="Intake.new",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        file_s3_key="s3://k",
        file_hash="h",
        extract_status="pending",
        extracted_fields=None,
    )
    session.add(version)
    await session.flush()
    rows = await embed_sow_version(
        session, sow_version_id=version.id, embedder=StubEmbeddings()
    )
    assert rows == []


# --- search ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_sow_returns_ranked_results(session):
    embedder = StubEmbeddings()

    # Seed two very different SOWs so the ranking is unambiguous.
    async def seed(text_scope: str, text_deliv: str) -> uuid.UUID:
        opp = Opportunity(
            id=uuid.uuid4(),
            hubspot_deal_id=str(uuid.uuid4()),
            governance_status="Intake.new",
        )
        session.add(opp)
        await session.flush()
        sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
        session.add(sow)
        await session.flush()
        version = SowVersion(
            id=uuid.uuid4(),
            sow_id=sow.id,
            file_s3_key="s3://k",
            file_hash="h",
            extract_status="complete",
            extracted_fields={
                "scope_summary": {
                    "value": text_scope,
                    "page_ref": 1,
                    "status": "confirmed",
                },
                "deliverables": {
                    "value": [text_deliv],
                    "page_ref": 1,
                    "status": "confirmed",
                },
            },
        )
        session.add(version)
        await session.flush()
        await embed_sow_version(
            session, sow_version_id=version.id, embedder=embedder
        )
        return version.id

    quoting_id = await seed(
        "Bespoke quoting tool replacement for sales and delivery teams",
        "Discovery quoting backlog integration NetSuite",
    )
    hr_id = await seed(
        "HR onboarding platform for global talent acquisition and payroll",
        "Employee onboarding workflow, payroll integration, benefits portal",
    )

    # Query heavily overlapping the quoting SOW.
    hits = await search_sow(
        session,
        embedder=embedder,
        query_text="quoting tool sales delivery integration NetSuite",
        top_k=5,
    )
    assert hits, "expected at least one match"
    # The quoting SOW must rank strictly ahead of the HR SOW.
    top = hits[0]
    assert top["sow_version_id"] == str(quoting_id)
    other_scores = [
        h["score"]
        for h in hits
        if h["sow_version_id"] == str(hr_id)
    ]
    assert not other_scores or top["score"] > max(other_scores)


@pytest.mark.asyncio
async def test_search_capabilities_ranks_by_similarity(session):
    embedder = StubEmbeddings()
    rows = [
        CapabilityCatalog(
            id=uuid.uuid4(),
            name="Salesforce implementation",
            description="Build custom Salesforce CRM flows for sales teams",
            tags=["salesforce", "crm"],
        ),
        CapabilityCatalog(
            id=uuid.uuid4(),
            name="Data migration",
            description="Legacy mainframe data migration to cloud warehouses",
            tags=["data"],
        ),
    ]
    for r in rows:
        session.add(r)
    await session.flush()
    for r in rows:
        await embed_capability(
            session, capability_id=r.id, embedder=embedder
        )

    hits = await search_capabilities(
        session,
        embedder=embedder,
        query_text="Salesforce CRM sales team implementation",
        top_k=5,
    )
    assert hits
    assert hits[0]["name"] == "Salesforce implementation"


@pytest.mark.asyncio
async def test_search_returns_empty_when_query_empty(session):
    hits = await search_sow(
        session, embedder=StubEmbeddings(), query_text="", top_k=5
    )
    assert hits == []


# --- capability re-embed --------------------------------------------------


@pytest.mark.asyncio
async def test_embed_capability_skips_existing_unless_forced(session):
    row = CapabilityCatalog(
        id=uuid.uuid4(),
        name="Bedrock RAG",
        description="Retrieval augmented generation on AWS Bedrock",
        tags=["ai"],
    )
    session.add(row)
    await session.flush()

    result = await embed_capability(
        session, capability_id=row.id, embedder=StubEmbeddings()
    )
    assert result is not None
    original_vec = list(result.embedding or [])
    assert original_vec

    # Change the description on the model but call without ``force`` —
    # the embedding should stay unchanged.
    row.description = "different text"
    await session.flush()
    unchanged = await embed_capability(
        session, capability_id=row.id, embedder=StubEmbeddings()
    )
    assert unchanged is not None
    assert list(unchanged.embedding or []) == original_vec

    # With ``force=True`` the vector must actually re-compute.
    reembedded = await embed_capability(
        session,
        capability_id=row.id,
        embedder=StubEmbeddings(),
        force=True,
    )
    assert reembedded is not None
    assert list(reembedded.embedding or []) != original_vec
