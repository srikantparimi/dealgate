"""Async engine + session factory. Reads `POSTGRES_URL` from env, defaults to a
local SQLite file so tests and first-run dev do not need a Postgres.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL: str = os.environ.get(
    "POSTGRES_URL",
    "sqlite+aiosqlite:///./dev.db",
)

# `future=True` is default in SA 2.0; keep echo off to avoid leaking payloads.
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an `AsyncSession` and closes it."""

    async with session_factory() as session:
        yield session
