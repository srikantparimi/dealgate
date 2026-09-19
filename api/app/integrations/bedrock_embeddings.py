"""Bedrock text-embedding adapter (S7 wave 2).

Real requests go to Amazon Titan v2 (``amazon.titan-embed-text-v2:0``)
via boto3's ``bedrock-runtime`` client. Tests and local dev use the
:class:`StubEmbeddings` adapter — deterministic, hash-based, and free of
network calls.

Every adapter returns a fixed-size Python list of floats so the
downstream service can serialize it identically to Postgres (pgvector)
and SQLite (JSON string). See :mod:`app.db.vector`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, Protocol


# Blueprint §11: default Titan v2 at 1536 dims. Overridable per-tenant
# via ``BEDROCK_EMBEDDING_MODEL_ID``; the dim stays 1536 to match the
# migration column and pgvector index.
DEFAULT_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIM = 1536


class Embedder(Protocol):
    """Anything that can turn a string into a fixed-size vector."""

    def embed(self, text: str, model_id: str | None = None) -> list[float]: ...


class StubEmbeddings:
    """Deterministic stand-in for tests + local dev.

    Uses SHA-256 bytes as a seed for a stateless pseudo-random walk so
    the same input always maps to the same 1536-float vector. Two inputs
    that share a prefix produce vectors with a real cosine similarity
    (not just a hash-of-string) — that's what
    ``test_embeddings.test_search_sow_returns_ranked_results`` leans on
    for the ranking assertion.
    """

    def embed(self, text: str, model_id: str | None = None) -> list[float]:
        # Normalise: lowercase + collapse whitespace so "Foo" and "foo"
        # collide, which matches the search behaviour testers expect.
        seed = " ".join((text or "").lower().split()).encode("utf-8")
        if not seed:
            seed = b"\x00"

        # Bucket every whitespace-delimited token into a small number of
        # slots; each slot contributes +1 to one dimension of the output.
        # The result is a bag-of-words style vector — deterministic,
        # commutative in token order (fine for a stub), and gives
        # overlapping texts a genuine cosine similarity.
        vec = [0.0] * EMBEDDING_DIM
        for token in seed.decode("utf-8").split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
            # Second byte-slice gives a signed nudge so different tokens
            # in the same slot can amplify or cancel out (better than
            # every token adding +1 into the same collision bucket).
            sign = 1.0 if digest[4] & 1 else -1.0
            magnitude = 1.0 + (digest[5] / 255.0)
            vec[slot] += sign * magnitude

        # L2-normalise so cosine similarity equals plain dot-product.
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            # Fully collided; return a canonical unit vector so callers
            # never divide by zero when scoring.
            vec[0] = 1.0
            return vec
        return [x / norm for x in vec]


class BedrockEmbeddings:
    """Boto3-backed adapter. Kept small on purpose — the tests never
    reach this branch.

    The adapter is lazy about creating the client so importing this
    module in test suites (which pin ``DEALGATE_ENV=local``) doesn't
    force a network resolution against AWS.
    """

    def __init__(self, region_name: str | None = None) -> None:
        self._region_name = region_name or os.environ.get(
            "AWS_REGION", "us-east-1"
        )
        self._client: Any = None

    def _lazy_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3  # local import — heavy dep
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "boto3 is required for BedrockEmbeddings; falling back to "
                "StubEmbeddings in dev/test paths avoids this import."
            ) from exc
        self._client = boto3.client(
            "bedrock-runtime", region_name=self._region_name
        )
        return self._client

    def embed(self, text: str, model_id: str | None = None) -> list[float]:
        client = self._lazy_client()
        payload = json.dumps({"inputText": text or "", "dimensions": EMBEDDING_DIM})
        response = client.invoke_model(
            modelId=model_id or DEFAULT_MODEL_ID,
            body=payload,
            contentType="application/json",
            accept="application/json",
        )
        body = json.loads(response["body"].read())
        vector = body.get("embedding") or []
        if len(vector) != EMBEDDING_DIM:  # pragma: no cover — safety net
            raise ValueError(
                f"Bedrock returned {len(vector)} dims, expected {EMBEDDING_DIM}"
            )
        return [float(x) for x in vector]


def default_embedder() -> Embedder:
    """Pick an embedder based on env.

    Local / test → :class:`StubEmbeddings` so no AWS credentials are
    needed and every run is reproducible. Any other env boots the real
    Bedrock adapter.
    """

    env = os.environ.get("DEALGATE_ENV", "local")
    if env in ("local", "test"):
        return StubEmbeddings()
    return BedrockEmbeddings()


def embed(text: str, model_id: str | None = None) -> list[float]:
    """Module-level convenience wrapper — picks up the default adapter."""

    return default_embedder().embed(text, model_id=model_id)


__all__ = [
    "BedrockEmbeddings",
    "DEFAULT_MODEL_ID",
    "EMBEDDING_DIM",
    "Embedder",
    "StubEmbeddings",
    "default_embedder",
    "embed",
]
