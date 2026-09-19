"""Embedding pipeline: chunk SOWs / capabilities and search them.

Design principles for this module:

- No network calls at import time — the caller passes an
  :class:`~app.integrations.bedrock_embeddings.Embedder` (usually
  :class:`StubEmbeddings` in tests) so the same code path runs against
  Titan in prod.
- Idempotency: :func:`embed_sow_version` and :func:`embed_capability`
  skip work when the chunk already exists (unique on
  ``(sow_version_id, chunk_index)`` / on capability id). Re-running the
  hook after a re-confirm is safe.
- Portable search: Postgres uses the ``<=>`` (cosine distance) operator
  from pgvector; SQLite falls through to a Python cosine helper. Both
  paths return the top-k rows in similarity order.

The adviser service calls :func:`search_sow` and
:func:`search_capabilities` on the intake ``problem`` string and injects
the results into the LLM prompt (see :mod:`app.services.adviser`).
"""

from __future__ import annotations

import math
import re
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.bedrock_embeddings import (
    DEFAULT_MODEL_ID,
    EMBEDDING_DIM,
    Embedder,
)
from app.models.capability import CapabilityCatalog
from app.models.embedding import SowEmbedding
from app.models.sow import SowVersion


# --- chunking -------------------------------------------------------------


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    """Simple word-preserving chunker.

    Splits on whitespace, joins back into groups of roughly ``size``
    characters with ``overlap`` characters of run-on so the chunk
    boundary doesn't drop a sentence.

    Guarantees:

    - Empty input returns ``[]``.
    - Every returned chunk is non-empty and no longer than
      ``size + <last word len>`` characters — we never split mid-word.
    - Overlap can be zero; the loop still terminates.
    """

    if size <= 0:
        raise ValueError("chunk size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be in [0, size)")

    words = re.split(r"\s+", (text or "").strip())
    words = [w for w in words if w]
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        # +1 for the space we'd insert before this word.
        step = len(word) + (1 if current else 0)
        if current and current_len + step > size:
            chunks.append(" ".join(current))
            # Peel the tail of the last chunk back into the next one so
            # the overlap window preserves boundary context.
            if overlap > 0:
                keep: list[str] = []
                keep_len = 0
                for w in reversed(current):
                    w_step = len(w) + (1 if keep else 0)
                    if keep_len + w_step > overlap:
                        break
                    keep.insert(0, w)
                    keep_len += w_step
                current = keep
                current_len = keep_len
            else:
                current = []
                current_len = 0

        if current:
            current_len += 1  # for the space
        current.append(word)
        current_len += len(word)

    if current:
        chunks.append(" ".join(current))
    return chunks


# --- SOW extraction of embed-worthy text ----------------------------------


def _sow_embed_source_text(version: SowVersion) -> str:
    """Extract the text we want to embed from a SOW version.

    Blueprint §5: past-SOW retrieval leans on ``scope`` + ``deliverables``.
    We concatenate those two fields from ``extracted_fields`` (populated
    by the SOW extract pipeline) into a single string suitable for
    :func:`chunk_text`. Falls back gracefully when either field is
    missing so a partial extract doesn't skip embedding entirely.
    """

    fields = version.extracted_fields or {}
    scope = _field_str(fields.get("scope_summary"))
    deliverables = _field_str(fields.get("deliverables"))
    parts = [p for p in (scope, deliverables) if p]
    return "\n\n".join(parts)


def _field_str(entry: Any) -> str:
    if entry is None:
        return ""
    if isinstance(entry, dict):
        value = entry.get("value")
    else:
        value = entry
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v) for v in value if v)
    return str(value)


# --- write path -----------------------------------------------------------


async def embed_sow_version(
    session: AsyncSession,
    *,
    sow_version_id: uuid.UUID,
    embedder: Embedder,
    model_id: str | None = None,
) -> list[SowEmbedding]:
    """Chunk + embed one SOW version's scope + deliverables.

    Idempotent: existing ``(sow_version_id, chunk_index)`` rows are
    skipped, so re-triggering the ``sow.confirmed`` hook is safe. Returns
    every row that ended up in the table (fresh or pre-existing) for the
    caller's audit payload.
    """

    version = (
        await session.execute(
            select(SowVersion).where(SowVersion.id == sow_version_id)
        )
    ).scalar_one_or_none()
    if version is None:
        return []

    source = _sow_embed_source_text(version)
    chunks = chunk_text(source)
    if not chunks:
        return []

    existing = (
        (
            await session.execute(
                select(SowEmbedding.chunk_index).where(
                    SowEmbedding.sow_version_id == sow_version_id
                )
            )
        )
        .scalars()
        .all()
    )
    seen = set(existing)

    created: list[SowEmbedding] = []
    for idx, chunk in enumerate(chunks):
        if idx in seen:
            continue
        vector = embedder.embed(chunk, model_id=model_id or DEFAULT_MODEL_ID)
        row = SowEmbedding(
            id=uuid.uuid4(),
            sow_version_id=sow_version_id,
            chunk_index=idx,
            chunk_text=chunk,
            embedding=vector,
        )
        session.add(row)
        created.append(row)

    if created:
        await session.flush()

    # Return every row that now exists for this version so callers can
    # link ``sow_embedding.id`` back into audit / retrieved payloads.
    rows = (
        (
            await session.execute(
                select(SowEmbedding)
                .where(SowEmbedding.sow_version_id == sow_version_id)
                .order_by(SowEmbedding.chunk_index)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def embed_capability(
    session: AsyncSession,
    *,
    capability_id: uuid.UUID,
    embedder: Embedder,
    model_id: str | None = None,
    force: bool = False,
) -> CapabilityCatalog | None:
    """Embed one capability's ``name + description``.

    Idempotent: skips work when ``embedding`` is already populated,
    unless the caller passes ``force=True`` (used by PATCH when the
    description changes so the vector stays fresh).
    """

    row = (
        await session.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.id == capability_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.embedding and not force:
        return row

    payload = f"{row.name}\n\n{row.description}"
    row.embedding = embedder.embed(
        payload, model_id=model_id or DEFAULT_MODEL_ID
    )
    await session.flush()
    return row


# --- search ---------------------------------------------------------------


def _cosine(a: list[float] | None, b: list[float] | None) -> float:
    """Cosine similarity for the Python fallback (SQLite path).

    Returns 0.0 for any missing / zero-length vector so search never
    raises on a partially embedded row.
    """

    if not a or not b:
        return 0.0
    if len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in vector) + "]"


async def search_sow(
    session: AsyncSession,
    *,
    embedder: Embedder,
    query_text: str,
    top_k: int = 5,
    model_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return the top-``top_k`` past-SOW chunks by cosine similarity.

    Each result carries the source ``sow_version_id``, the ``chunk_index``,
    a short preview of ``chunk_text`` and a ``score`` in ``[-1, 1]`` (higher
    is closer). The adviser passes the resulting shape straight into
    ``adviser_estimate.retrieved`` and the LLM prompt.
    """

    if not query_text or top_k <= 0:
        return []

    query_vec = embedder.embed(
        query_text, model_id=model_id or DEFAULT_MODEL_ID
    )
    dialect = session.bind.dialect.name if session.bind is not None else ""

    if dialect == "postgresql":
        # pgvector's ``<=>`` returns cosine *distance* — closer to 0 is
        # better. Convert to a similarity in [-1, 1] for the caller.
        stmt = text(
            "SELECT id, sow_version_id, chunk_index, chunk_text, "
            "1 - (embedding <=> CAST(:qv AS vector)) AS score "
            "FROM sow_embedding "
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:qv AS vector) "
            "LIMIT :limit"
        )
        rows = (
            await session.execute(
                stmt, {"qv": _pgvector_literal(query_vec), "limit": top_k}
            )
        ).all()
        return [
            {
                "id": str(r.id),
                "sow_version_id": str(r.sow_version_id),
                "chunk_index": int(r.chunk_index),
                "chunk_text": _preview(r.chunk_text),
                "score": float(r.score),
            }
            for r in rows
        ]

    # SQLite fallback — pull every row, score in Python, return the top-k.
    stmt2 = select(SowEmbedding).where(SowEmbedding.embedding.isnot(None))
    rows2 = (await session.execute(stmt2)).scalars().all()
    scored = [
        {
            "id": str(r.id),
            "sow_version_id": str(r.sow_version_id),
            "chunk_index": int(r.chunk_index),
            "chunk_text": _preview(r.chunk_text),
            "score": _cosine(query_vec, r.embedding),
        }
        for r in rows2
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


async def search_capabilities(
    session: AsyncSession,
    *,
    embedder: Embedder,
    query_text: str,
    top_k: int = 5,
    model_id: str | None = None,
) -> list[dict[str, Any]]:
    """Same contract as :func:`search_sow`, keyed against
    ``capability_catalog``. Skips rows without an embedding."""

    if not query_text or top_k <= 0:
        return []

    query_vec = embedder.embed(
        query_text, model_id=model_id or DEFAULT_MODEL_ID
    )
    dialect = session.bind.dialect.name if session.bind is not None else ""

    if dialect == "postgresql":
        stmt = text(
            "SELECT id, name, description, tags, "
            "1 - (embedding <=> CAST(:qv AS vector)) AS score "
            "FROM capability_catalog "
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:qv AS vector) "
            "LIMIT :limit"
        )
        rows = (
            await session.execute(
                stmt, {"qv": _pgvector_literal(query_vec), "limit": top_k}
            )
        ).all()
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "description": _preview(r.description),
                "tags": list(r.tags or []),
                "score": float(r.score),
            }
            for r in rows
        ]

    stmt2 = select(CapabilityCatalog).where(CapabilityCatalog.embedding.isnot(None))
    rows2 = (await session.execute(stmt2)).scalars().all()
    scored = [
        {
            "id": str(r.id),
            "name": r.name,
            "description": _preview(r.description),
            "tags": list(r.tags or []),
            "score": _cosine(query_vec, r.embedding),
        }
        for r in rows2
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _preview(chunk: str, limit: int = 280) -> str:
    """Trim long chunks for the retrieved payload — keeps
    ``adviser_estimate.retrieved`` compact even on very long SOWs."""

    if chunk is None:
        return ""
    text_ = str(chunk).strip()
    if len(text_) <= limit:
        return text_
    return text_[: limit - 1].rstrip() + "…"


__all__ = [
    "EMBEDDING_DIM",
    "chunk_text",
    "embed_capability",
    "embed_sow_version",
    "search_capabilities",
    "search_sow",
]
