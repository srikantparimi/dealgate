"""Rate card versions — publish, list, lookup.

S2 E4. Publishing is atomic: one ``rate_card_version`` + N immutable
``rate_card_row`` records + one ``rate_card.published`` audit row all land in
the same transaction. Once written, rows are never updated — Finance
publishes a new version to change bands.

The service is deliberately UI-agnostic: it takes validated Python payloads,
raises 422 on shape/value problems and returns the ORM version object with
its rows eagerly loaded. Callers (router, importer, seed script) share this
same path so the audit + immutability guarantees hold everywhere.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.models.rate_card import RateCardRow, RateCardVersion

# Sanity threshold: cost bands under this get a warning in the create response
# but pass validation (Finance can override with `confirm=True` in the router).
SANITY_COST_FLOOR: Decimal = Decimal("5.00")

ALLOWED_LOCATIONS: frozenset[str] = frozenset({"US", "India"})


@dataclass(frozen=True)
class RateCardRowInput:
    role: str
    seniority: str
    location: str
    cost_low: Decimal
    cost_base: Decimal
    cost_high: Decimal


def _validate_row(row: RateCardRowInput, idx: int) -> None:
    if not row.role.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].role is required",
        )
    if not row.seniority.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].seniority is required",
        )
    if row.location not in ALLOWED_LOCATIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].location must be one of {sorted(ALLOWED_LOCATIONS)}",
        )
    for name, value in (
        ("cost_low", row.cost_low),
        ("cost_base", row.cost_base),
        ("cost_high", row.cost_high),
    ):
        if value <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"rows[{idx}].{name} must be > 0",
            )
    if not (row.cost_low <= row.cost_base <= row.cost_high):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}]: cost_low <= cost_base <= cost_high required",
        )


def _sanity_warnings(rows: Sequence[RateCardRowInput]) -> list[str]:
    """Return human-readable warnings for cost bands below the sanity floor.

    Warnings are informational — the caller decides whether to require
    ``confirm=True`` before continuing. Returning a list (not raising) keeps
    the router logic simple.
    """

    warnings: list[str] = []
    for idx, row in enumerate(rows):
        if row.cost_low < SANITY_COST_FLOOR:
            warnings.append(
                f"rows[{idx}] ({row.role} / {row.seniority} / {row.location}): "
                f"cost_low ${row.cost_low} < ${SANITY_COST_FLOOR}"
            )
    return warnings


async def publish_rate_card(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    rows: Sequence[RateCardRowInput],
    effective_from: date,
    notes: str | None = None,
) -> RateCardVersion:
    """Create one immutable ``rate_card_version`` with its rows + audit.

    Raises 422 if any row fails validation. Empty ``rows`` is rejected — a
    version with no bands is never useful and hides Finance mistakes.
    """

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rows must not be empty",
        )
    for idx, row in enumerate(rows):
        _validate_row(row, idx)

    version = RateCardVersion(
        id=uuid.uuid4(),
        effective_from=effective_from,
        published_by=actor_id,
        notes=notes,
    )
    session.add(version)

    for row in rows:
        session.add(
            RateCardRow(
                id=uuid.uuid4(),
                rate_card_version_id=version.id,
                role=row.role.strip(),
                seniority=row.seniority.strip(),
                location=row.location,
                cost_low=row.cost_low,
                cost_base=row.cost_base,
                cost_high=row.cost_high,
            )
        )
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="rate_card.published",
        entity="rate_card_version",
        entity_id=str(version.id),
        before=None,
        after={
            "effective_from": effective_from.isoformat(),
            "row_count": len(rows),
            "notes": notes,
        },
    )
    await session.commit()

    # Re-fetch with rows eagerly loaded so callers can serialize immediately.
    return await _load_version_with_rows(session, version.id)


async def _load_version_with_rows(
    session: AsyncSession, version_id: uuid.UUID
) -> RateCardVersion:
    stmt = (
        select(RateCardVersion)
        .options(selectinload(RateCardVersion.rows))
        .where(RateCardVersion.id == version_id)
    )
    return (await session.execute(stmt)).scalar_one()


async def list_rate_cards(session: AsyncSession) -> list[RateCardVersion]:
    """Return all versions newest-first, with rows eagerly loaded.

    Sprint 2 volumes are tiny (a handful of versions per year), so we skip
    pagination. Add it when Finance publishes hundreds.
    """

    stmt = (
        select(RateCardVersion)
        .options(selectinload(RateCardVersion.rows))
        .order_by(RateCardVersion.effective_from.desc(), RateCardVersion.published_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_rate_card(session: AsyncSession, version_id: uuid.UUID) -> RateCardVersion:
    stmt = (
        select(RateCardVersion)
        .options(selectinload(RateCardVersion.rows))
        .where(RateCardVersion.id == version_id)
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rate card version not found"
        )
    return version


async def active_rate_card(
    session: AsyncSession, at: date | None = None
) -> RateCardVersion | None:
    """The version whose ``effective_from`` <= ``at`` (default today).

    Returns ``None`` when no rate card exists yet — callers decide what to do
    (usually surface an "unpriced" marker rather than fabricating a cost).
    """

    from datetime import date as _date

    cutoff = at or _date.today()
    stmt = (
        select(RateCardVersion)
        .options(selectinload(RateCardVersion.rows))
        .where(RateCardVersion.effective_from <= cutoff)
        .order_by(RateCardVersion.effective_from.desc(), RateCardVersion.published_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@dataclass(frozen=True)
class CostBand:
    low: Decimal
    base: Decimal
    high: Decimal


def lookup_cost(
    role: str,
    seniority: str,
    location: str,
    rate_card_version: RateCardVersion,
) -> CostBand | None:
    """Return the (low, base, high) cost band for a role/seniority/location.

    Case- and whitespace-insensitive on ``role``/``seniority`` since those
    strings are free-form. Returns ``None`` when the version has no matching
    row — the caller decides whether that is a validation error (Sales) or a
    "TBD" marker (Delivery model builder).
    """

    if location not in ALLOWED_LOCATIONS:
        raise ValueError(f"location must be one of {sorted(ALLOWED_LOCATIONS)}")
    role_key = role.strip().casefold()
    seniority_key = seniority.strip().casefold()
    for row in rate_card_version.rows:
        if (
            row.role.strip().casefold() == role_key
            and row.seniority.strip().casefold() == seniority_key
            and row.location == location
        ):
            return CostBand(low=row.cost_low, base=row.cost_base, high=row.cost_high)
    return None


def serialize_row(row: RateCardRow) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "seniority": row.seniority,
        "location": row.location,
        "cost_low": row.cost_low,
        "cost_base": row.cost_base,
        "cost_high": row.cost_high,
    }


def serialize_version(version: RateCardVersion, *, include_rows: bool) -> dict:
    payload: dict = {
        "id": version.id,
        "effective_from": version.effective_from,
        "published_at": version.published_at,
        "published_by": version.published_by,
        "notes": version.notes,
        "row_count": len(version.rows),
    }
    if include_rows:
        payload["rows"] = [serialize_row(r) for r in version.rows]
    return payload


__all__ = [
    "CostBand",
    "RateCardRowInput",
    "SANITY_COST_FLOOR",
    "active_rate_card",
    "get_rate_card",
    "list_rate_cards",
    "lookup_cost",
    "publish_rate_card",
    "serialize_row",
    "serialize_version",
    "_sanity_warnings",
    "_validate_row",
]
