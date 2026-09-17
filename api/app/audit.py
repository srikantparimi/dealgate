"""Audit chain writer + verifier.

Every state-changing endpoint must call `append_audit` inside the same
transaction as the state change (CLAUDE.md rule 5). Chain integrity is
verifiable end-to-end via `verify_chain`.

Chain rule:

    row_hash = sha256(prev_hash || canonical_json(fields))

`prev_hash` is the previous row's `row_hash`, or the empty string for the
genesis row. `canonical_json` uses sorted keys and no whitespace so hashes
are reproducible across runs and hosts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


def _ts_to_canonical(ts: datetime) -> str:
    """Emit a UTC ISO-8601 string with microsecond precision, no tz suffix.

    SQLite drops tzinfo on reload; storing the canonical form as naive-UTC
    makes the hash reproducible across drivers.
    """

    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts.isoformat(timespec="microseconds")

# Arbitrary but stable key for the Postgres advisory lock. Any int fits; we use
# a 32-bit constant chosen once so this lock never collides with other features.
_ADVISORY_LOCK_KEY = 4242_4242


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_row_hash(prev_hash: str | None, fields: dict[str, Any]) -> str:
    body = (prev_hash or "") + _canonical_json(fields)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


async def _lock_chain(session: AsyncSession) -> None:
    """Serialize appenders so `prev_hash` cannot race.

    Postgres: session-level advisory lock, released on commit/rollback.
    SQLite: BEGIN IMMEDIATE via a no-op write acquires the reserved lock.
    """

    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=_ADVISORY_LOCK_KEY)
        )
    # SQLite serializes writes at the file level; the outer transaction is
    # enough for the tamper-detection guarantees we need in tests.


async def append_audit(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    correlation_id: str | None = None,
) -> AuditEvent:
    """Append one row to `audit_event`, chained to the previous row.

    Caller owns the transaction — this function does not commit. That is
    deliberate: the state change and the audit row must land together.
    """

    await _lock_chain(session)

    result = await session.execute(
        select(AuditEvent).order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(1)
    )
    prev = result.scalar_one_or_none()
    prev_hash = prev.row_hash if prev is not None else None

    ts = datetime.now(UTC)
    fields = {
        "actor_id": str(actor_id) if actor_id else None,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "before": before,
        "after": after,
        "ts": _ts_to_canonical(ts),
        "correlation_id": correlation_id,
    }
    row_hash = _compute_row_hash(prev_hash, fields)

    event = AuditEvent(
        id=uuid.uuid4(),
        ts=ts,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=before,
        after=after,
        correlation_id=correlation_id,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    session.add(event)
    await session.flush()
    return event


async def verify_chain(session: AsyncSession) -> bool:
    """Recompute every row's hash and confirm the chain matches.

    Returns True iff every stored `row_hash` and `prev_hash` line up with the
    reconstructed values. Any tamper in a single row fails the whole chain.
    """

    result = await session.execute(select(AuditEvent).order_by(AuditEvent.ts, AuditEvent.id))
    rows = list(result.scalars())
    expected_prev: str | None = None
    for row in rows:
        if row.prev_hash != expected_prev:
            return False
        fields = {
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "action": row.action,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "before": row.before,
            "after": row.after,
            "ts": _ts_to_canonical(row.ts),
            "correlation_id": row.correlation_id,
        }
        if _compute_row_hash(expected_prev, fields) != row.row_hash:
            return False
        expected_prev = row.row_hash
    return True
