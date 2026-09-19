"""Approver resolution (Sprint 9 wave 1).

Given a function (delivery / hr / finance / legal) and a business unit,
return the accountable user. Resolution order:

1. ``function_owner`` row with matching function + business_unit +
   ``is_default=true``.
2. ``function_owner`` row with matching function + business_unit (any).
3. ``function_owner`` row with matching function + ``business_unit IS NULL``.
4. First member of the corresponding Cognito group.

Every read is audit-free — this is a lookup, not a mutation. The
services that consume the resolver (approvals, ceo_exception) already
audit the transition they perform.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.function_owner import ALLOWED_FUNCTIONS, FunctionOwner
from app.models.user import User


# One-to-one mapping of function → Cognito group (fallback path).
_FUNCTION_TO_GROUP: dict[str, str] = {
    "delivery": "Delivery",
    "hr": "HR",
    "finance": "Finance",
    "legal": "Legal",
}


@dataclass(frozen=True)
class ResolvedApprover:
    """The resolver's answer for one function."""

    function: str
    user_id: uuid.UUID | None
    source: str  # "owner_row" | "owner_row_default" | "group_fallback" | "none"
    business_unit: str | None = None


async def resolve(
    session: AsyncSession,
    *,
    function: str,
    business_unit: str | None = None,
) -> ResolvedApprover:
    """Resolve the accountable user for one function + business unit."""

    if function not in ALLOWED_FUNCTIONS:
        raise ValueError(
            f"function must be one of {sorted(ALLOWED_FUNCTIONS)}; got {function!r}"
        )

    # 1 + 2: rows matching the business unit exactly.
    if business_unit is not None:
        exact = (
            (
                await session.execute(
                    select(FunctionOwner)
                    .where(FunctionOwner.function == function)
                    .where(FunctionOwner.business_unit == business_unit)
                    .order_by(
                        FunctionOwner.is_default.desc(),
                        FunctionOwner.created_at.desc(),
                    )
                )
            )
            .scalars()
            .first()
        )
        if exact is not None:
            return ResolvedApprover(
                function=function,
                user_id=exact.user_id,
                source=(
                    "owner_row_default" if exact.is_default else "owner_row"
                ),
                business_unit=business_unit,
            )

    # 3: fall through to rows with business_unit IS NULL.
    fallback_row = (
        (
            await session.execute(
                select(FunctionOwner)
                .where(FunctionOwner.function == function)
                .where(FunctionOwner.business_unit.is_(None))
                .order_by(
                    FunctionOwner.is_default.desc(),
                    FunctionOwner.created_at.desc(),
                )
            )
        )
        .scalars()
        .first()
    )
    if fallback_row is not None:
        return ResolvedApprover(
            function=function,
            user_id=fallback_row.user_id,
            source=(
                "owner_row_default" if fallback_row.is_default else "owner_row"
            ),
            business_unit=None,
        )

    # 4: pick the first member of the group.
    group = _FUNCTION_TO_GROUP[function]
    rows = list((await session.execute(select(User))).scalars().all())
    for u in rows:
        if group in (u.groups or []):
            return ResolvedApprover(
                function=function,
                user_id=u.id,
                source="group_fallback",
                business_unit=business_unit,
            )
    return ResolvedApprover(
        function=function,
        user_id=None,
        source="none",
        business_unit=business_unit,
    )


async def resolve_all(
    session: AsyncSession, *, business_unit: str | None = None
) -> dict[str, ResolvedApprover]:
    """Convenience: resolve every function for one business unit."""

    out: dict[str, ResolvedApprover] = {}
    for fn in ("delivery", "hr", "finance", "legal"):
        out[fn] = await resolve(
            session, function=fn, business_unit=business_unit
        )
    return out


# --- admin CRUD -----------------------------------------------------------


async def upsert_owner(
    session: AsyncSession,
    *,
    function: str,
    business_unit: str | None,
    user_id: uuid.UUID,
    is_default: bool = True,
) -> FunctionOwner:
    """Set or replace the owner row for (function, business_unit).

    Idempotent: a duplicate insert with the same target user is a no-op
    (returns the existing row). The service inserts a fresh row when the
    target user changes; the resolver picks the most-recently-created
    row so old rows still resolve historically without a hard delete.
    """

    if function not in ALLOWED_FUNCTIONS:
        raise ValueError(f"function must be one of {sorted(ALLOWED_FUNCTIONS)}")

    dup = (
        (
            await session.execute(
                select(FunctionOwner)
                .where(FunctionOwner.function == function)
                .where(
                    FunctionOwner.business_unit.is_(None)
                    if business_unit is None
                    else FunctionOwner.business_unit == business_unit
                )
                .where(FunctionOwner.user_id == user_id)
                .where(FunctionOwner.is_default == is_default)
            )
        )
        .scalars()
        .first()
    )
    if dup is not None:
        return dup

    row = FunctionOwner(
        id=uuid.uuid4(),
        function=function,
        business_unit=business_unit,
        user_id=user_id,
        is_default=is_default,
    )
    session.add(row)
    await session.flush()
    return row


async def list_owners(session: AsyncSession) -> list[FunctionOwner]:
    return list(
        (
            await session.execute(
                select(FunctionOwner).order_by(
                    FunctionOwner.function,
                    FunctionOwner.business_unit.is_(None).desc(),
                    FunctionOwner.created_at.desc(),
                )
            )
        )
        .scalars()
        .all()
    )


async def delete_owner(session: AsyncSession, *, owner_id: uuid.UUID) -> bool:
    row = (
        await session.execute(
            select(FunctionOwner).where(FunctionOwner.id == owner_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


__all__ = [
    "ResolvedApprover",
    "delete_owner",
    "list_owners",
    "resolve",
    "resolve_all",
    "upsert_owner",
]
