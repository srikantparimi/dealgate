"""Declarative Base for all ORM models.

`JSONB` is used on Postgres and falls back to generic `JSON` on SQLite so the
same models work for local tests without needing a Postgres container.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class JsonB(TypeDecorator):  # type: ignore[type-arg]
    """`JSONB` on Postgres, `JSON` elsewhere. Keeps tests portable."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    pass
