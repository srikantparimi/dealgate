"""S4 E7 — void-on-change hook.

Bridges the SOW and Delivery Model services into the approvals state
machine without either of them importing the approvals package
directly. Both callers pass ``opportunity_id`` + a short reason string;
this module resolves the active package and voids it if one exists.

Rule 4 (immutable versions): the ``ApprovalPackage`` row is not
rebuilt — its ``status`` is flipped to ``voided`` in place; a fresh
package with a new sha256 is what the account owner resubmits.

Idempotent: if there is no active package (no submission yet, or the
current one is already voided/rejected), the hook is a no-op.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.approvals import void_on_change


async def on_sow_version_created(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    new_sow_version_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> None:
    """A brand-new sow_version landed — void any active package.

    Called from :func:`app.services.sow_extract.create_sow_version` when
    a second (or later) version replaces the pinned one.
    """

    await void_on_change(
        session,
        opportunity_id=opportunity_id,
        reason=f"sow_version changed (new version {new_sow_version_id})",
        actor_id=actor_id,
    )


async def on_gm_model_created(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    new_gm_model_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> None:
    """A brand-new gm_model landed — void any active package.

    Called from :func:`app.services.delivery_model.create_gm_model_version`
    once the fresh version has been persisted.
    """

    await void_on_change(
        session,
        opportunity_id=opportunity_id,
        reason=f"gm_model changed (new version {new_gm_model_id})",
        actor_id=actor_id,
    )


__all__ = ["on_gm_model_created", "on_sow_version_created"]
