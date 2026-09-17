"""Alembic env — sync driver derived from the app's async URL.

Alembic runs migrations sync; we translate `+aiosqlite` -> `` and
`+asyncpg`/`+psycopg` -> `+psycopg` for the migration connection.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import DATABASE_URL, Base
from app import models  # noqa: F401 — registers mappers on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg", 1)
    return url


target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", _sync_url(DATABASE_URL))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(target_metadata=target_metadata, connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
