"""Margin policy versions — publish, list, active lookup.

Blueprint §2 sets the sensible defaults: US 35%, India 50%. Until Finance
publishes a ``policy_version``, ``active_policy`` returns an in-memory
sentinel with those values so GM calculations and the UI never crash on a
missing row. Once Finance publishes, callers must freeze the returned
version's id on any persisted GM snapshot.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.gm.policy import INDIA_FLOOR as DEFAULT_INDIA_FLOOR
from app.gm.policy import US_FLOOR as DEFAULT_US_FLOOR
from app.models.policy import PolicyVersion

ALLOWED_FX_CONVENTIONS: frozenset[str] = frozenset({"fixed_at_sow_date", "monthly_average"})
DEFAULT_FX_CONVENTION: str = "fixed_at_sow_date"


@dataclass(frozen=True)
class ActivePolicy:
    """A read-only snapshot of the currently effective margin policy.

    ``id`` is ``None`` for the sentinel used when no version exists yet — a
    persisted GM snapshot with ``policy_version_id=None`` means "computed
    against blueprint defaults", not "missing data".
    """

    id: uuid.UUID | None
    effective_from: date | None
    us_floor: Decimal
    india_floor: Decimal
    fx_convention: str
    is_default: bool


def _sentinel() -> ActivePolicy:
    return ActivePolicy(
        id=None,
        effective_from=None,
        us_floor=DEFAULT_US_FLOOR,
        india_floor=DEFAULT_INDIA_FLOOR,
        fx_convention=DEFAULT_FX_CONVENTION,
        is_default=True,
    )


def _validate_publish(us_floor: Decimal, india_floor: Decimal, fx_convention: str) -> None:
    if not (Decimal(0) < us_floor < Decimal(1)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="us_floor must satisfy 0 < us_floor < 1",
        )
    if not (Decimal(0) < india_floor < Decimal(1)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="india_floor must satisfy 0 < india_floor < 1",
        )
    # Blueprint §2: India floor is the strict-higher offshore floor.
    if not (us_floor < india_floor):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="us_floor must be strictly less than india_floor",
        )
    if fx_convention not in ALLOWED_FX_CONVENTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"fx_convention must be one of {sorted(ALLOWED_FX_CONVENTIONS)}",
        )


async def publish_policy(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    us_floor: Decimal,
    india_floor: Decimal,
    fx_convention: str,
    effective_from: date,
    notes: str | None = None,
) -> PolicyVersion:
    """Insert a new immutable ``policy_version`` + emit ``policy.published``.

    Existing versions are never touched. Callers that persist a GM snapshot
    should record ``policy_version_id`` alongside the numbers so history
    stays reproducible.
    """

    _validate_publish(us_floor, india_floor, fx_convention)

    version = PolicyVersion(
        id=uuid.uuid4(),
        effective_from=effective_from,
        us_floor=us_floor,
        india_floor=india_floor,
        fx_convention=fx_convention,
        published_by=actor_id,
        notes=notes,
    )
    session.add(version)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="policy.published",
        entity="policy_version",
        entity_id=str(version.id),
        before=None,
        after={
            "effective_from": effective_from.isoformat(),
            "us_floor": str(us_floor),
            "india_floor": str(india_floor),
            "fx_convention": fx_convention,
            "notes": notes,
        },
    )
    await session.commit()
    await session.refresh(version)
    return version


async def list_policies(session: AsyncSession) -> list[PolicyVersion]:
    """All versions, newest-first. Tiny table — no pagination in Sprint 2."""

    stmt = select(PolicyVersion).order_by(
        PolicyVersion.effective_from.desc(), PolicyVersion.published_at.desc()
    )
    return list((await session.execute(stmt)).scalars().all())


async def active_policy(
    session: AsyncSession, at: date | None = None
) -> ActivePolicy:
    """The version whose ``effective_from`` <= ``at``; sentinel if none.

    The sentinel keeps the two acceptance tests passing simultaneously:
    ``check_floors`` still works with 0.35 / 0.50 defaults on day one, and
    Finance can publish new floors without any migration surgery.
    """

    from datetime import date as _date

    cutoff = at or _date.today()
    stmt = (
        select(PolicyVersion)
        .where(PolicyVersion.effective_from <= cutoff)
        .order_by(PolicyVersion.effective_from.desc(), PolicyVersion.published_at.desc())
        .limit(1)
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        return _sentinel()
    return ActivePolicy(
        id=version.id,
        effective_from=version.effective_from,
        us_floor=version.us_floor,
        india_floor=version.india_floor,
        fx_convention=version.fx_convention,
        is_default=False,
    )


def serialize_version(version: PolicyVersion) -> dict:
    return {
        "id": version.id,
        "effective_from": version.effective_from,
        "us_floor": version.us_floor,
        "india_floor": version.india_floor,
        "fx_convention": version.fx_convention,
        "published_at": version.published_at,
        "published_by": version.published_by,
        "notes": version.notes,
    }


def serialize_active(active: ActivePolicy) -> dict:
    return {
        "id": active.id,
        "effective_from": active.effective_from,
        "us_floor": active.us_floor,
        "india_floor": active.india_floor,
        "fx_convention": active.fx_convention,
        "is_default": active.is_default,
    }


__all__ = [
    "ALLOWED_FX_CONVENTIONS",
    "ActivePolicy",
    "DEFAULT_FX_CONVENTION",
    "active_policy",
    "list_policies",
    "publish_policy",
    "serialize_active",
    "serialize_version",
]
