"""S7 — DB-level append-only enforcement on ``audit_event`` (Postgres).

Guarded: only runs when ``DEALGATE_POSTGRES_URL`` is set. The default
test path uses SQLite, where grants + plpgsql triggers do not apply — the
application-level chain semantics are covered by ``test_audit.py``. CI /
staging exercises this test against a real Postgres instance.

The test does not re-run alembic (that path is exercised by the deploy
pipeline). Instead it verifies the guarantees the migration provides:
attempting an ``UPDATE`` or ``DELETE`` against ``audit_event`` under the
app role raises. The migration itself is asserted to have run by looking
for the trigger in ``pg_trigger``.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

_PG_URL = os.environ.get("DEALGATE_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not _PG_URL,
    reason="requires postgres; set DEALGATE_POSTGRES_URL to run",
)


def _async_url(url: str) -> str:
    # Accept the plain postgres URL or an explicit asyncpg driver spec.
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.mark.asyncio
async def test_trigger_blocks_update_and_delete() -> None:
    engine = create_async_engine(_async_url(_PG_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            trg = await conn.execute(
                text(
                    "SELECT 1 FROM pg_trigger WHERE tgname = "
                    "'audit_event_no_update_delete_trg'"
                )
            )
            assert trg.first() is not None, (
                "audit_event trigger missing — run `alembic upgrade head` first"
            )

            # Seed one row so UPDATE/DELETE have something to bite on.
            row_id = uuid.uuid4()
            await conn.execute(
                text(
                    "INSERT INTO audit_event "
                    "(id, actor_id, action, entity, entity_id, before, after, "
                    " correlation_id, prev_hash, row_hash) VALUES "
                    "(:id, NULL, 'test.seed', 'test', 'x', NULL, NULL, NULL, "
                    " NULL, :h)"
                ),
                {"id": row_id, "h": "0" * 64},
            )

        # Both mutations must raise. The trigger raises with
        # ``insufficient_privilege`` (SQLSTATE 42501); the grant path
        # raises with ``insufficient_privilege`` too. We don't pin the
        # SQLSTATE — DBAPIError is enough.
        with pytest.raises(DBAPIError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE audit_event SET action = 'tampered' "
                        "WHERE id = :id"
                    ),
                    {"id": row_id},
                )

        with pytest.raises(DBAPIError):
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM audit_event WHERE id = :id"),
                    {"id": row_id},
                )
    finally:
        await engine.dispose()
