"""NDA/MSA coverage gate for signature and release, never functional review.

Coverage is checked across the client legal entities, matching the existing
client-level policy. Missing or expired coverage raises ApprovalError (409).
Historical executed agreements retain the legacy expiry-date fallback.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Agreement, LegalEntity
from app.models.opportunity import Opportunity


_REQUIRED_KINDS: tuple[str, ...] = ("NDA", "MSA")


def _is_valid_executed(agreement: Agreement, today: date) -> bool:
    """True when the row is Executed and not expired.

    Expiry priority mirrors :func:`app.services.clients.coverage_state`:
    prefer the S2-E3 ``expiry`` column, fall back to the S1 ``expiry_date``.
    A row without an expiry set is still valid — Legal has not scheduled
    a renewal deadline yet.
    """

    if agreement.state != "executed":
        return False
    expiry = agreement.expiry or agreement.expiry_date
    if expiry is not None and expiry < today:
        return False
    return True


async def _load_client_agreements(
    session: AsyncSession, client_id: uuid.UUID
) -> list[Agreement]:
    entity_ids = list(
        (
            await session.execute(
                select(LegalEntity.id).where(LegalEntity.client_id == client_id)
            )
        ).scalars()
    )
    if not entity_ids:
        return []
    rows = list(
        (
            await session.execute(
                select(Agreement).where(Agreement.legal_entity_id.in_(entity_ids))
            )
        ).scalars()
    )
    return rows


def _missing_kinds(agreements: list[Agreement], today: date) -> list[str]:
    """Return the required kinds (NDA, MSA) that are not covered by any
    valid executed agreement."""

    missing: list[str] = []
    for kind in _REQUIRED_KINDS:
        # Any agreement of this kind in valid executed state satisfies the rule.
        if not any(
            a.kind == kind and _is_valid_executed(a, today) for a in agreements
        ):
            missing.append(kind)
    return missing


async def check_msa_and_nda_executed(
    session: AsyncSession,
    opportunity: Opportunity,
    *,
    today: date | None = None,
) -> None:
    """Raise :class:`ApprovalError` (409) if the opportunity's client lacks
    a valid Executed NDA and MSA.

    Import of ``ApprovalError`` is lazy so this module has no import cycle
    with :mod:`app.services.approvals`.
    """

    # Lazy import so approvals -> coverage_gate has no cycle when
    # coverage_gate -> approvals grows a dependency later.
    from app.services.approvals import ApprovalError

    when = today or date.today()

    if opportunity.client_id is None:
        # Legacy opportunity with no client link — treat as missing both.
        # The rollout rule still applies: no coverage, no signature.
        raise ApprovalError(
            status_code=409,
            detail="MSA + NDA required (missing: NDA, MSA)",
        )

    agreements = await _load_client_agreements(session, opportunity.client_id)
    missing = _missing_kinds(agreements, when)
    if missing:
        raise ApprovalError(
            status_code=409,
            detail=f"MSA + NDA required (missing: {', '.join(missing)})",
        )


__all__ = ["check_msa_and_nda_executed"]
