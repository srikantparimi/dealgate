"""S20 W7 · release / handoff gate (T23).

The release step needs **three distinct events**, all recorded and all
audited (not derived from CRM stage):

    1. Internal signoff.
       Delivery lead approves the package (approvals row where
       function='delivery', decision='approve'). This is feasibility
       sign-off; it happens *before* the client signs.

    2. Client execution.
       Verified executed pdf. `signed_sow_upload.verify_status='verified'`
       against the pinned `sow_version.extracted_fields`.

    3. Delivery acceptance.
       `delivery_acceptance` row filed by Delivery ops confirming
       staffing / billing / PO setup is ready.

The review's explicit prohibition (`CRM Closed Won never authorizes
release`) is enforced here: `Opportunity.is_closed_won` is *not read*
in this module.  A test proves it.

CEO exception conditions + approvals-currency checks are delegated to
:func:`app.services.approval_workflow.require_signature_eligibility`.
Package supersession is guarded server-side — a superseded package
returns 409 with a pointer to the newer package.

Rule 5 (CLAUDE.md): every gate check that fails logs the reason. The
successful path passes through :func:`app.services.signed_sow.release`
so the SES fan-out + kickoff/billing tasks + renewal + project link
all commit in one transaction and audit `handoff.gate_passed`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval, ApprovalPackage
from app.models.delivery_acceptance import DeliveryAcceptance
from app.models.signed_sow import SignedSowUpload


@dataclass(frozen=True)
class ReleaseGate:
    """Result of the three-event gate check.

    `ok` iff every named event has landed and the package is current.
    The failing list carries the human-readable reason for each
    missing event so the UI (and audit) can quote it verbatim.
    """

    ok: bool
    internal_signoff_ok: bool
    client_execution_ok: bool
    delivery_acceptance_ok: bool
    approvals_current_ok: bool
    superseded_ok: bool
    reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": {
                "internal_signoff": self.internal_signoff_ok,
                "client_execution": self.client_execution_ok,
                "delivery_acceptance": self.delivery_acceptance_ok,
                "approvals_current": self.approvals_current_ok,
                "not_superseded": self.superseded_ok,
            },
            "reasons": list(self.reasons),
        }


# ---- individual checks ----------------------------------------------------


async def _internal_signoff(
    session: AsyncSession, package_id: uuid.UUID
) -> tuple[bool, str | None]:
    """Delivery function approved this exact package?

    Internal signoff means the Delivery lead marked the package as
    feasible — a distinct decision from delivery *acceptance* (which
    happens after execution + setup).
    """

    stmt = (
        select(Approval)
        .where(Approval.package_id == package_id)
        .where(Approval.function == "delivery")
        .where(Approval.decision == "approve")
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False, (
            "internal_signoff missing — Delivery lead has not approved "
            "the package (function='delivery', decision='approve')"
        )
    return True, None


async def _client_execution(
    session: AsyncSession, package_id: uuid.UUID
) -> tuple[bool, str | None]:
    """A verified executed pdf exists for this package?

    "Verified" means the diff against `sow_version.extracted_fields`
    passed (:mod:`app.services.signed_sow`). Upload alone is never
    enough — the row must be `verify_status='verified'`.
    """

    stmt = (
        select(SignedSowUpload)
        .where(SignedSowUpload.package_id == package_id)
        .order_by(SignedSowUpload.uploaded_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False, (
            "client_execution missing — no signed_sow_upload for this "
            "package (upload alone is not execution — the file must "
            "verify against the approved terms)"
        )
    if row.verify_status != "verified":
        return False, (
            f"client_execution incomplete — latest upload verify_status "
            f"is {row.verify_status!r}"
            + (f" ({row.verify_reason})" if row.verify_reason else "")
        )
    return True, None


async def _delivery_acceptance(
    session: AsyncSession, package_id: uuid.UUID
) -> tuple[bool, str | None]:
    """Delivery ops filed the `delivery_acceptance` row for this package?"""

    stmt = select(DeliveryAcceptance).where(
        DeliveryAcceptance.package_id == package_id
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False, (
            "delivery_acceptance missing — Delivery ops has not filed "
            "the acceptance record for this package"
        )
    return True, None


async def _approvals_current(
    session: AsyncSession, package: ApprovalPackage
) -> tuple[bool, str | None]:
    """CEO conditions + expiry + status window (via approval_workflow)."""

    # Delegate to the existing helper so W3 remains the single owner of
    # the approval-workflow eligibility rules. It raises on failure —
    # we translate the raise into a boolean + reason.
    from app.services.approval_workflow import require_signature_eligibility
    from app.services.approvals import ApprovalError

    try:
        await require_signature_eligibility(session, package)
    except ApprovalError as exc:
        return False, f"approvals_current failed: {exc.detail}"
    if package.status not in ("ready_to_sign",):
        return False, (
            f"approvals_current failed: package status is "
            f"{package.status!r}; expected 'ready_to_sign'"
        )
    return True, None


def _not_superseded(package: ApprovalPackage) -> tuple[bool, str | None]:
    """The package has not been superseded by a newer submission?"""

    if package.superseded_by is not None:
        return False, (
            f"package has been superseded by {package.superseded_by}; "
            "release must target the newer package"
        )
    return True, None


# ---- combined gate -------------------------------------------------------


async def check_release_gate(
    session: AsyncSession, package: ApprovalPackage
) -> ReleaseGate:
    """Assemble the three-event gate + supporting checks.

    Never reads `Opportunity.is_closed_won` — CRM stage is not a signal
    for release authorisation. The regression test
    `test_release_ignores_closed_won` guards this contract.
    """

    reasons: list[str] = []

    signoff_ok, r = await _internal_signoff(session, package.id)
    if r:
        reasons.append(r)

    exec_ok, r = await _client_execution(session, package.id)
    if r:
        reasons.append(r)

    accept_ok, r = await _delivery_acceptance(session, package.id)
    if r:
        reasons.append(r)

    approvals_ok, r = await _approvals_current(session, package)
    if r:
        reasons.append(r)

    superseded_ok, r = _not_superseded(package)
    if r:
        reasons.append(r)

    ok = all(
        (signoff_ok, exec_ok, accept_ok, approvals_ok, superseded_ok)
    )
    return ReleaseGate(
        ok=ok,
        internal_signoff_ok=signoff_ok,
        client_execution_ok=exec_ok,
        delivery_acceptance_ok=accept_ok,
        approvals_current_ok=approvals_ok,
        superseded_ok=superseded_ok,
        reasons=reasons,
    )


__all__ = ["ReleaseGate", "check_release_gate"]
