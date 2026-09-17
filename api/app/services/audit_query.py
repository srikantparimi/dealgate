"""Audit log query + verification helpers for S1-E1.

The router calls into this module so it stays a thin adapter. Two concerns
live here:

- Building the filtered, paginated select over `audit_event` joined against
  `user` for the actor email.
- Running `verify_chain` (from `app.audit`) against a filtered slice. When
  filters are supplied we validate only the rows that match, so a Finance
  reviewer can confirm the sub-chain they are looking at. When no filters
  are supplied we validate the entire chain.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.audit import AuditEvent
from app.models.user import User


@dataclass(frozen=True)
class AuditFilters:
    entity: str | None = None
    entity_id: str | None = None
    actor_id: uuid.UUID | None = None
    action: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    page: int = 1
    size: int = 25

    def any_set(self) -> bool:
        return any(
            v is not None
            for v in (
                self.entity,
                self.entity_id,
                self.actor_id,
                self.action,
                self.since,
                self.until,
            )
        )


def _apply_filters(stmt: Select, filters: AuditFilters) -> Select:
    if filters.entity:
        stmt = stmt.where(AuditEvent.entity == filters.entity)
    if filters.entity_id:
        stmt = stmt.where(AuditEvent.entity_id == filters.entity_id)
    if filters.actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == filters.actor_id)
    if filters.action:
        stmt = stmt.where(AuditEvent.action == filters.action)
    if filters.since is not None:
        stmt = stmt.where(AuditEvent.ts >= filters.since)
    if filters.until is not None:
        stmt = stmt.where(AuditEvent.ts <= filters.until)
    return stmt


def build_list_query(filters: AuditFilters) -> Select:
    """Newest-first list with actor email joined in.

    Left outer join so system-authored rows (`actor_id IS NULL`) still show.
    """

    actor = aliased(User)
    stmt = (
        select(AuditEvent, actor.email)
        .join(actor, actor.id == AuditEvent.actor_id, isouter=True)
    )
    stmt = _apply_filters(stmt, filters)
    stmt = stmt.order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
    offset = max(0, (filters.page - 1) * filters.size)
    stmt = stmt.offset(offset).limit(filters.size)
    return stmt


def build_count_query(filters: AuditFilters) -> Select:
    stmt = select(func.count(AuditEvent.id))
    stmt = _apply_filters(stmt, filters)
    return stmt


# --- verification -----------------------------------------------------------
#
# `app.audit.verify_chain` walks the entire table. For the filtered-slice
# case we replicate that walk here (same hashing rules) but limited to the
# rows the user is currently looking at, and we return structured detail —
# the endpoint reports whether the slice is intact, how many rows were
# checked, and the id of the first row where recomputation disagrees.


def _ts_to_canonical(ts: datetime) -> str:
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts.isoformat(timespec="microseconds")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _row_fields(row: AuditEvent) -> dict[str, Any]:
    return {
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "action": row.action,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "before": row.before,
        "after": row.after,
        "ts": _ts_to_canonical(row.ts),
        "correlation_id": row.correlation_id,
    }


def _recompute_hash(prev_hash: str | None, row: AuditEvent) -> str:
    body = (prev_hash or "") + _canonical_json(_row_fields(row))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    first_broken_row: uuid.UUID | None
    checked: int
    message: str


async def verify_slice(
    session: AsyncSession, filters: AuditFilters
) -> VerifyResult:
    """Verify a filtered slice (or the whole chain if no filters set).

    Read-only: no writes are ever issued, regardless of outcome.
    """

    stmt = select(AuditEvent)
    if filters.any_set():
        stmt = _apply_filters(stmt, filters)
    stmt = stmt.order_by(AuditEvent.ts, AuditEvent.id)
    rows = list((await session.execute(stmt)).scalars())

    if not rows:
        return VerifyResult(
            ok=True,
            first_broken_row=None,
            checked=0,
            message="No rows in scope; chain is trivially valid.",
        )

    # Whole-chain check: prev_hash of first row must be NULL (genesis).
    # Sliced check: seed with the actual prev_hash of the first row and only
    # confirm each row's own hash + linkage from there on.
    expected_prev: str | None
    if filters.any_set():
        expected_prev = rows[0].prev_hash
    else:
        expected_prev = None
        if rows[0].prev_hash is not None:
            return VerifyResult(
                ok=False,
                first_broken_row=rows[0].id,
                checked=1,
                message="Chain broken: first row has a non-null prev_hash.",
            )

    for idx, row in enumerate(rows):
        if row.prev_hash != expected_prev:
            return VerifyResult(
                ok=False,
                first_broken_row=row.id,
                checked=idx + 1,
                message=f"Chain broken at row {row.id}: prev_hash does not match.",
            )
        if _recompute_hash(expected_prev, row) != row.row_hash:
            return VerifyResult(
                ok=False,
                first_broken_row=row.id,
                checked=idx + 1,
                message=f"Chain broken at row {row.id}: row_hash does not match recomputed value.",
            )
        expected_prev = row.row_hash

    scope = "slice" if filters.any_set() else "full chain"
    return VerifyResult(
        ok=True,
        first_broken_row=None,
        checked=len(rows),
        message=f"Chain valid across {len(rows)} rows ({scope}).",
    )
