"""S20 W7 · delivery_acceptance service (T23).

Delivery ops sign off on the release once the executed document has been
verified and the setup checklist is complete. This is the third distinct
event (alongside internal signoff and client execution) that the release
gate requires. The review is explicit: `CRM Closed Won never authorizes
release`.

Public surface:
- :func:`record` — file a delivery_acceptance row. 403 if the actor is
  not in the Delivery group. 409 if the package already has one.
- :func:`latest_for` — the current row (if any) for a package.

Rule 4 (CLAUDE.md): the row is set-once; :func:`record` refuses to
overwrite. Rule 5: every insert writes a `delivery.accepted` audit line
in the same transaction.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.approval import ApprovalPackage
from app.models.delivery_acceptance import DeliveryAcceptance
from app.models.user import User


DELIVERY_ROLES: frozenset[str] = frozenset({"Delivery", "SystemAdmin"})


class DeliveryAcceptanceError(HTTPException):
    """Base error the router surfaces as-is."""


# ---- reads ---------------------------------------------------------------


async def latest_for(
    session: AsyncSession, package_id: uuid.UUID
) -> DeliveryAcceptance | None:
    """Return the single delivery_acceptance row for a package, if any."""

    stmt = select(DeliveryAcceptance).where(
        DeliveryAcceptance.package_id == package_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---- write ---------------------------------------------------------------


async def _load_actor(session: AsyncSession, actor_id: uuid.UUID) -> User:
    row = (
        await session.execute(select(User).where(User.id == actor_id))
    ).scalar_one_or_none()
    if row is None:
        raise DeliveryAcceptanceError(status_code=404, detail="actor not found")
    return row


async def _load_package(
    session: AsyncSession, package_id: uuid.UUID
) -> ApprovalPackage:
    row = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == package_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise DeliveryAcceptanceError(
            status_code=404, detail="approval_package not found"
        )
    return row


async def record(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package_id: uuid.UUID,
    notes: str | None = None,
    staffing_confirmed: bool = False,
    billing_setup_confirmed: bool = False,
    po_confirmed: bool = False,
) -> DeliveryAcceptance:
    """File the delivery_acceptance row for a package.

    Preconditions:
      - Actor is in `Delivery` (or `SystemAdmin`).
      - Package exists and is not `voided` / `rejected`.
      - No prior row exists (unique constraint on `package_id`).
    """

    actor = await _load_actor(session, actor_id)
    if not any(g in DELIVERY_ROLES for g in (actor.groups or [])):
        raise DeliveryAcceptanceError(
            status_code=403,
            detail=(
                "delivery_acceptance requires the Delivery role — "
                "internal signoff and client execution are separate events"
            ),
        )

    package = await _load_package(session, package_id)
    if package.status in ("voided", "rejected"):
        raise DeliveryAcceptanceError(
            status_code=409,
            detail=(
                f"package is {package.status!r}; a voided/rejected package "
                "cannot be accepted for delivery"
            ),
        )
    if package.superseded_by is not None:
        raise DeliveryAcceptanceError(
            status_code=409,
            detail=(
                "package has been superseded; the newer package must be "
                "accepted, not this one"
            ),
        )

    row = DeliveryAcceptance(
        id=uuid.uuid4(),
        package_id=package_id,
        accepted_by=actor_id,
        notes=notes,
        staffing_confirmed=staffing_confirmed,
        billing_setup_confirmed=billing_setup_confirmed,
        po_confirmed=po_confirmed,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DeliveryAcceptanceError(
            status_code=409,
            detail=(
                f"delivery_acceptance already recorded for package "
                f"{package_id}"
            ),
        ) from exc

    await append_audit(
        session,
        actor_id=actor_id,
        action="delivery.accepted",
        entity="delivery_acceptance",
        entity_id=str(row.id),
        before=None,
        after={
            "package_id": str(package_id),
            "accepted_by": str(actor_id),
            "staffing_confirmed": staffing_confirmed,
            "billing_setup_confirmed": billing_setup_confirmed,
            "po_confirmed": po_confirmed,
            "notes_present": bool(notes),
        },
    )
    await session.commit()
    await session.refresh(row)
    return row


def serialize(row: DeliveryAcceptance) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "package_id": str(row.package_id),
        "accepted_by": str(row.accepted_by),
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "notes": row.notes,
        "staffing_confirmed": row.staffing_confirmed,
        "billing_setup_confirmed": row.billing_setup_confirmed,
        "po_confirmed": row.po_confirmed,
    }


__all__ = [
    "DELIVERY_ROLES",
    "DeliveryAcceptanceError",
    "latest_for",
    "record",
    "serialize",
]
