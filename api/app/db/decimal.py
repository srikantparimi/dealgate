"""Exact Python Decimal round trips with PostgreSQL NUMERIC and local SQLite."""
from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator


class ExactNumeric(TypeDecorator):
    impl = Numeric
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(String(128) if dialect.name == "sqlite" else Numeric())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("ExactNumeric requires a finite Decimal")
        return format(value, "f") if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            raise ValueError("A binary float cannot establish exact decimal evidence")
        return Decimal(value)
