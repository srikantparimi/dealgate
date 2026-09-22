"""NDA + MSA hard block before signature and release (S14b).

Blueprint §2 (hard rule): "No valid NDA + MSA → SOW cannot move to
signature." Coverage state was tracked in :func:`app.services.clients.coverage_state`
since Sprint 2 but nothing enforced it at the transition. This module
holds the gate the signature service checks; functional review does not
require coverage.

Contract:

- Raises :class:`app.services.approvals.ApprovalError` (409) when either
  NDA or MSA is not in ``executed`` state, or is executed but expired.
- Message shape is exactly ``"MSA + NDA required (missing: ...)"`` so the
  UI can render the missing pieces without parsing.
- The check prefers entity-level: if the opportunity has ``client_id``
  set, look for NDA + MSA across the client's legal_entities. Since the
  ``Opportunity`` model does not carry a ``legal_entity_id`` link, we
  treat "the client has both across entities" as satisfying the rule
  (blueprint §6.2 Legal coverage model). Legacy sow_versions without a
  client link fall through to the same check (client=None → all missing).

No side effects: no audit row, no notification, no partial write. The
caller runs this before ``session.flush`` so a 409 leaves the transaction
untouched.
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
