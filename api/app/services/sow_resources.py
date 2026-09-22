"""Resources on a SOW: view and edit them at any point in its life (S10-08).

Staffing used to be editable only at the gate, on the way to the confirmation
screen. That is the one moment it is least likely to be right: the plan gets
firmer during negotiation, and it changes again once delivery starts.

The rule that makes editing safe is the signature, not the screen:

- **Before the SOW is signed** a plan is a proposal. Edit it as often as you
  like; each save is a new immutable GM version (CLAUDE.md rule 4 — never
  UPDATE) and nobody is notified, because nobody has committed to anything.

- **After it is signed** the margin was part of a decision. The edit is still
  allowed — people leave projects, scope moves — but it carries an effective
  date and everyone who approved the original is told, with the old and new
  margin side by side. A margin that silently moves after Finance approved it
  is the thing this whole product exists to prevent.

Utilization: ``allocation_pct`` scales revenue *and* cost in the pure
library, so a person at 50% costs half and bills half for the same calendar
hours. That is the only number needed to express part-time staffing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.approval import ApprovalPackage
from app.models.gm_model import GmModel
from app.models.signed_sow import SignedSowUpload
from app.services.approvers import resolve_all
from app.services.notifications import queue_notification

__all__ = [
    "ResourceChangeResult",
    "SowResourceError",
    "current_resources",
    "is_signed",
    "update_resources",
]


class SowResourceError(Exception):
    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ResourceChangeResult:
    gm_model_id: uuid.UUID
    previous_gm_model_id: uuid.UUID | None
    requires_notice: bool
    effective_from: date | None
    notified: list[str]
    before_margin: dict[str, Any]
    after_margin: dict[str, Any]


async def is_signed(session: AsyncSession, opportunity_id: uuid.UUID) -> bool:
    """True once a signed SOW has been uploaded against an approval package.

    Signature, not approval, is the line. A package can be approved and then
    renegotiated before anyone signs; until the client has signed, the plan is
    still a proposal.
    """

    row = (
        await session.execute(
            select(SignedSowUpload.id)
            .join(ApprovalPackage, ApprovalPackage.id == SignedSowUpload.package_id)
            .where(ApprovalPackage.opportunity_id == opportunity_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def _latest_gm(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> GmModel | None:
    """Most recent GM version, with its children loaded.

    Eager-loaded on purpose: every caller reads the resource lines, and a
    lazy relationship touched from async code raises MissingGreenlet rather
    than quietly issuing a second query.
    """

    from sqlalchemy.orm import selectinload

    return (
        (
            await session.execute(
                select(GmModel)
                .where(GmModel.opportunity_id == opportunity_id)
                .options(
                    selectinload(GmModel.resource_lines),
                    selectinload(GmModel.cost_lines),
                    selectinload(GmModel.phases),
                )
                .order_by(GmModel.created_at.desc(), GmModel.version.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


def _margin_snapshot(model: GmModel | None) -> dict[str, Any]:
    """The numbers a reader compares before and after a change."""

    if model is None:
        return {"gm_model_id": None}
    from app.services.sow_confirmation import _compute_floors

    floors = _compute_floors(model)
    return {
        **floors,
        "gm_model_id": str(model.id),
        "gm_us": floors.get("gm_us"),
        "gm_india": floors.get("gm_india"),
        "gm_blended": floors.get("gm_blended"),
        "us_pass": floors.get("us_pass"),
        "india_pass": floors.get("india_pass"),
        "requires_ceo": floors.get("requires_ceo"),
    }


async def current_resources(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> dict[str, Any]:
    """The committed plan plus everything the screen needs to decide what to
    offer: whether editing needs a notice, and what the margin is now."""

    from app.services.delivery_model import serialize_cost_line, serialize_resource_line

    model = await _latest_gm(session, opportunity_id)
    signed = await is_signed(session, opportunity_id)
    proposals = []
    if model is not None and not model.direct_costs_reviewed and model.sow_version_id:
        from app.models.sow import SowVersion
        from app.services.direct_cost_proposals import propose_direct_costs
        version = (await session.execute(select(SowVersion).where(SowVersion.id == model.sow_version_id))).scalar_one_or_none()
        if version is not None:
            proposals = propose_direct_costs(version.extracted_fields or {})
    lines: list[dict[str, Any]] = []
    if model is not None:
        for r in model.resource_lines:
            lines.append(
                {
                    "id": str(r.id),
                    "role": r.role,
                    "seniority": r.seniority,
                    "location": r.location,
                    "person_name": r.person_name,
                    # Surfaced as a percentage: the grid asks for "50", the
                    # library stores 0.5.
                    "utilization_pct": format(
                        (r.allocation_pct or Decimal("1")) * 100, "f"
                    ),
                    # `format(None, "f")` raises TypeError, which would
                    # take the whole resources tab down for one bad row.
                    # These columns are NOT NULL in the model, but the row
                    # below already guards its own nullable columns and the
                    # asymmetry is not worth the risk.
                    "hours_billable": (
                        format(r.billable_hours, "f")
                        if r.billable_hours is not None
                        else "0"
                    ),
                    "hourly_bill_rate": (
                        format(r.hourly_bill_rate, "f")
                        if r.hourly_bill_rate is not None
                        else "0"
                    ),
                    "hourly_cost": (
                        format(r.hourly_cost, "f")
                        if r.hourly_cost is not None
                        else None
                    ),
                    "start_date": r.start_date.isoformat() if r.start_date else None,
                    "end_date": r.end_date.isoformat() if r.end_date else None,
                }
            )
    return {
        "opportunity_id": str(opportunity_id),
        "gm_model_id": str(model.id) if model else None,
        "engagement_type": model.engagement_type if model else None,
        "is_signed": signed,
        # Editing is always allowed. After signature it just costs a notice.
        "editable": True,
        "requires_notice_on_change": signed,
        "resources": lines,
        "resource_lines": [serialize_resource_line(r) for r in model.resource_lines] if model else [],
        "cost_lines": [serialize_cost_line(c) for c in model.cost_lines] if model else [],
        "direct_cost_proposals": proposals,
        "direct_costs_reviewed": model.direct_costs_reviewed if model else False,
        "total_price": format(model.revenue_us + model.revenue_india, "f") if model else None,
        "margin": _margin_snapshot(model),
    }


async def update_resources(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    payload: dict[str, Any],
    effective_from: date | None = None,
    reason: str | None = None,
) -> ResourceChangeResult:
    """Save a new resource plan as a new immutable GM version.

    After signature an ``effective_from`` and a ``reason`` are required, and
    everyone who approved is notified with both margins. Before it, neither
    is needed and nobody is told.
    """

    from app.services.delivery_model import (
        create_gm_model_version,
        parse_gm_model_payload,
    )
    from app.services.sow_extract import latest_version_for as _latest_sow
    from app.models.opportunity import Opportunity

    await session.execute(select(Opportunity.id).where(Opportunity.id == opportunity_id).with_for_update())
    signed = await is_signed(session, opportunity_id)
    previous = await _latest_gm(session, opportunity_id)
    before = _margin_snapshot(previous)
    cost_only = previous is not None and "resource_lines" not in payload
    if previous is not None and "resource_lines" not in payload:
        from app.services.delivery_model import serialize_gm_model
        retained = serialize_gm_model(previous)
        phase_names = {str(phase.id): phase.name for phase in previous.phases}
        for line in retained["resource_lines"] + retained["cost_lines"]:
            line["phase_name"] = phase_names.get(line.get("phase_id"))
        retained["total_price"] = format(previous.revenue_us + previous.revenue_india, "f")
        payload = {**retained, **payload}
    if previous is not None and "cost_lines" not in payload:
        from app.services.delivery_model import serialize_cost_line
        payload = {**payload, "cost_lines": [serialize_cost_line(c) for c in previous.cost_lines]}
    if previous is not None and "resource_lines" in payload:
        from app.services.delivery_model import serialize_resource_line
        previous_lines = {str(line.id): line for line in previous.resource_lines}
        phase_names = {str(phase.id): phase.name for phase in previous.phases}
        resources = []
        for line in payload["resource_lines"]:
            original = previous_lines.get(str(line.get("id")))
            if original is not None:
                saved = serialize_resource_line(original)
                line = {**{key: saved[key] for key in ("hourly_cost", "validated_by")},
                        "phase_name": phase_names.get(saved["phase_id"]), **line}
            resources.append(line)
        payload = {**payload, "resource_lines": resources}

    if signed:
        if effective_from is None:
            raise SowResourceError(
                "this SOW is signed — an effective date is required so the "
                "margin change can be dated",
                status_code=422,
            )
        if not reason or not reason.strip():
            raise SowResourceError(
                "this SOW is signed — a reason is required; it is what the "
                "approvers will read",
                status_code=422,
            )

    # sow_version_id MUST always be populated — without it, build_confirmation
    # cannot correlate the saved plan to the extracted SOW, and the confirm
    # screen falls back to the auto-plan (the bug this whole story fixes).
    # If the client didn't send one, use the latest SOW version for the deal.
    latest_sow_state = None
    if not payload.get("sow_version_id"):
        latest_sow_state = await _latest_sow(session, opportunity_id)
        if latest_sow_state is not None:
            payload = {**payload, "sow_version_id": str(latest_sow_state.id)}

    # Fixed-price revenue: the SOW extraction owns the price. If the frontend
    # did not carry it into the payload, look it up here — the GM engine
    # treats missing total_price as 0 on a fixed-fee engagement, which is what
    # produced "GM Unavailable" on a $50,000 SOW.
    engagement_type = payload.get("engagement_type") or ""
    if engagement_type in ("fixed_price", "assessment") and not payload.get(
        "total_price"
    ):
        if latest_sow_state is None:
            latest_sow_state = await _latest_sow(session, opportunity_id)
        if latest_sow_state is not None:
            from app.services.sow_confirmation import _extracted_price
            from sqlalchemy import select as _select
            from app.models.sow import SowVersion as _SowVersion

            version = (
                await session.execute(
                    _select(_SowVersion).where(_SowVersion.id == latest_sow_state.id)
                )
            ).scalar_one_or_none()
            if version is not None:
                price = _extracted_price(version)
                if price is not None:
                    payload = {**payload, "total_price": format(price, "f")}

    parsed = parse_gm_model_payload(payload)
    if cost_only:
        parsed = replace(parsed, resolve_missing_rates=False)
    model = await create_gm_model_version(
        session,
        opportunity_id=opportunity_id,
        actor_id=actor_id,
        payload=parsed,
    )
    after = _margin_snapshot(model)

    await append_audit(
        session,
        actor_id=actor_id,
        action="sow_resources.updated",
        entity="gm_model",
        entity_id=str(model.id),
        before={"gm_model_id": str(previous.id) if previous else None, **before},
        after={
            **after,
            "signed_at_change": signed,
            "effective_from": effective_from.isoformat() if effective_from else None,
            "reason": reason,
        },
    )

    notified: list[str] = []
    if signed:
        notified = await _notify_approvers(
            session,
            opportunity_id=opportunity_id,
            before=before,
            after=after,
            effective_from=effective_from,
            reason=reason or "",
        )

    return ResourceChangeResult(
        gm_model_id=model.id,
        previous_gm_model_id=previous.id if previous else None,
        requires_notice=signed,
        effective_from=effective_from,
        notified=notified,
        before_margin=before,
        after_margin=after,
    )


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{Decimal(str(value)) * 100:.1f}%"
    except Exception:  # noqa: BLE001 — a display helper must not raise
        return str(value)


async def _notify_approvers(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    before: dict[str, Any],
    after: dict[str, Any],
    effective_from: date | None,
    reason: str,
) -> list[str]:
    """Tell everyone who approved that the margin they approved has moved.

    Both margins go in the body. A notice saying only "the staffing changed"
    puts the burden on the reader to go and find out whether it mattered.
    """

    approvers = await resolve_all(session)
    subject = f"Resource change on a signed SOW — margin now {_pct(after.get('gm_blended'))}"
    body = (
        f"The staffing on a signed SOW has changed"
        f"{f', effective {effective_from.isoformat()}' if effective_from else ''}.\n\n"
        f"Blended margin: {_pct(before.get('gm_blended'))} → "
        f"{_pct(after.get('gm_blended'))}\n"
        f"US: {_pct(before.get('gm_us'))} → {_pct(after.get('gm_us'))}\n"
        f"India: {_pct(before.get('gm_india'))} → {_pct(after.get('gm_india'))}\n\n"
        f"Reason: {reason}\n"
    )
    if after.get("requires_ceo") and not before.get("requires_ceo"):
        # A change that pushes the deal below a floor is not just an FYI.
        body += (
            "\nThis change takes the engagement below a margin floor, which "
            "would require CEO approval on a new SOW.\n"
        )

    sent: list[str] = []
    seen: set[uuid.UUID] = set()
    for function, resolved in approvers.items():
        user_id = getattr(resolved, "user_id", None)
        if user_id is None or user_id in seen:
            continue
        seen.add(user_id)
        await queue_notification(
            session,
            user_id=user_id,
            category="resource_change",
            subject=subject,
            body_md=body,
            related_entity="opportunity",
            related_entity_id=str(opportunity_id),
        )
        sent.append(function)
    return sent
