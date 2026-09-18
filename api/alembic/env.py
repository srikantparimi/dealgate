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

# Scheduler ledger table lives outside `app.models` (owned by other agents)
# but still binds to `Base` — import so autogenerate + `create_all` see it.
from app.scheduler import ledger as _scheduler_ledger  # noqa: F401, E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg", 1)
    return url


# Naming convention lets SQLite batch mode re-emit anonymous constraints
# (needed by 0007's `batch_alter_table("gm_model")` where an unnamed FK is
# added alongside existing rows). Applied here so every migration inherits
# the convention without needing to pass it explicitly.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
Base.metadata.naming_convention = _NAMING_CONVENTION  # type: ignore[assignment]

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", _sync_url(DATABASE_URL))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
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
        context.configure(
            target_metadata=target_metadata,
            connection=connection,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
