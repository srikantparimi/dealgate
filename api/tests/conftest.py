"""Shared fixtures.

Uses an in-memory SQLite database with `StaticPool` so multiple sessions in the
same test share the same schema. Alembic is not run here — we `create_all` from
metadata because the migration and the models are 1:1 (mismatches are caught
by the model round-trip tests).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app import models  # noqa: F401 — register mappers

# Keep the auth stub in "local" mode for the test session.
os.environ.setdefault("DEALGATE_ENV", "local")


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
