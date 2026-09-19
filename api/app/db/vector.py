"""Portable pgvector column type.

Postgres: emits ``VECTOR(<dim>)`` so pgvector can index and query the
column with ``vector_cosine_ops``. SQLite: stores the vector as a JSON
list of floats — enough for the deterministic tests, which then use a
manual dot-product / cosine helper in :mod:`app.services.embeddings`.

Keeping the storage split behind a single ``TypeDecorator`` means models
can declare ``embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))``
without caring which dialect is on the other end. Migration 0023 is
still responsible for the pgvector extension + HNSW indexes; those
cannot be modelled through SQLAlchemy alone.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator, UserDefinedType


class _PgVector(UserDefinedType):  # type: ignore[type-arg]
    """Bare-bones VECTOR(N) column for Postgres — no ORM ops, just DDL.

    The service layer builds the ``ORDER BY embedding <=> :vec`` clause
    by hand using a text literal; SQLAlchemy sees the column as opaque.
    """

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_: Any) -> str:  # noqa: D401
        return f"VECTOR({self.dim})"

    def bind_processor(self, dialect):  # type: ignore[no-untyped-def]
        def process(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, (list, tuple)):
                # pgvector accepts the "[a,b,c]" text literal on INSERT.
                return "[" + ",".join(str(float(x)) for x in value) + "]"
            return value

        return process

    def result_processor(self, dialect, coltype):  # type: ignore[no-untyped-def]
        def process(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                # pgvector returns "[a,b,c]" as text on some drivers.
                stripped = value.strip().lstrip("[").rstrip("]")
                if not stripped:
                    return []
                return [float(x) for x in stripped.split(",")]
            return value

        return process


class Vector(TypeDecorator):  # type: ignore[type-arg]
    """``VECTOR(dim)`` on Postgres, JSON list of floats on SQLite."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if dialect.name == "postgresql":
            # Delegated to _PgVector.bind_processor; return raw so it can
            # format the text literal.
            return value
        # SQLite: persist as JSON string; keep the list intact for round-trip.
        if isinstance(value, (list, tuple)):
            return json.dumps([float(x) for x in value])
        return value

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value


__all__ = ["Vector"]
