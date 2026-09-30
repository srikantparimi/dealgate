"""S20 W7 · project lifecycle (T24).

Create-or-link the `project` row when the release gate passes. Idempotent:
a re-run of the release flow (or a duplicate webhook) finds the existing
row and returns it — the unique constraint on `package_id` is the
contract.

Baseline snapshot is frozen at creation. Forecast + actuals write to
their own tables keyed on `gm_model_id` (existing) plus `project_id`
(added in requests.md #W7-2026-09-30-04). The baseline is never touched
again — Rule 4 (CLAUDE.md).

Deterioration handling: forecast writes that drop below policy floors
already file a `forecast.recovery` task in
:mod:`app.services.forecast`. W7 extends that path (via
:func:`recovery_notification`) to identify the named recovery owner and
queue an `escalation` notification. See T24.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.sow import SowVersion
from app.services.provenance import value_of


# ---- baseline builder ----------------------------------------------------


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _baseline_snapshot(
    *,
    package: ApprovalPackage,
    opportunity: Opportunity,
    sow_version: SowVersion,
    gm_model: GmModel,
) -> dict[str, Any]:
    """Build the frozen baseline snapshot captured at release.

    Every field is copied by value — mutating the source records after
    release must not affect the baseline. Numeric values become strings
    so the JSON payload round-trips deterministically.
    """

    fields = sow_version.extracted_fields or {}
    return {
        "package_id": str(package.id),
        "opportunity_id": str(opportunity.id),
        "sow_version_id": str(sow_version.id),
        "gm_model_id": str(gm_model.id),
        "sow_version_no": sow_version.version_no,
        "gm_version": gm_model.version,
        "engagement_type": gm_model.engagement_type,
        "delivery_pattern": gm_model.delivery_pattern,
        "contingency_pct": _decimal_str(gm_model.contingency_pct),
        "warranty_days": gm_model.warranty_days,
        "revenue_us": _decimal_str(gm_model.revenue_us),
        "revenue_india": _decimal_str(gm_model.revenue_india),
        "price": value_of(fields.get("price")),
        "currency": value_of(fields.get("currency")),
        "term_start": value_of(fields.get("term_start")),
        "term_end": value_of(fields.get("term_end")),
        "scope_summary": value_of(fields.get("scope_summary")),
        "resource_lines": [
            {
                "id": str(line.id),
                "role": line.role,
                "seniority": line.seniority,
                "location": line.location,
                "allocation_pct": _decimal_str(line.allocation_pct),
                "billable_hours": _decimal_str(line.billable_hours),
                "hourly_bill_rate": _decimal_str(line.hourly_bill_rate),
                "hourly_cost": _decimal_str(line.hourly_cost),
                "start_date": (
                    line.start_date.isoformat() if line.start_date else None
                ),
                "end_date": line.end_date.isoformat() if line.end_date else None,
            }
            for line in (gm_model.resource_lines or [])
        ],
    }


def _default_title(
    *,
    client: Client | None,
    opportunity: Opportunity,
    fields: dict[str, Any] | None,
) -> str:
    fields = fields or {}
    for key in ("sow_title", "project_title", "title"):
        v = value_of(fields.get(key))
        if v:
            return str(v)[:255]
    client_name = client.name if client and client.name else "Project"
    deal = opportunity.hubspot_deal_id or str(opportunity.id)[:8]
    return f"{client_name} — {deal}"[:255]


# ---- create-or-link ------------------------------------------------------


async def existing_for_package(
    session: AsyncSession, package_id: uuid.UUID
) -> Project | None:
    stmt = select(Project).where(Project.package_id == package_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_or_link(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package: ApprovalPackage,
) -> tuple[Project, bool]:
    """Return the project for this package; create it if absent.

    Return value is (project, created) where `created=True` on first
    call and `False` on every subsequent call for the same package —
    the idempotency guard called out in T23.

    Neither call path mutates `baseline_snapshot_json` after creation
    (rule 4).
    """

    existing = await existing_for_package(session, package.id)
    if existing is not None:
        await append_audit(
            session,
            actor_id=actor_id,
            action="project.linked",
            entity="project",
            entity_id=str(existing.id),
            before=None,
            after={
                "package_id": str(package.id),
                "linked_only": True,
            },
        )
        return existing, False

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == package.opportunity_id)
        )
    ).scalar_one()
    client = None
    if opp.client_id is not None:
        client = (
            await session.execute(
                select(Client).where(Client.id == opp.client_id)
            )
        ).scalar_one_or_none()
    sow_version = (
        await session.execute(
            select(SowVersion).where(SowVersion.id == package.sow_version_id)
        )
    ).scalar_one()
    gm_model = (
        await session.execute(
            select(GmModel)
            .options(selectinload(GmModel.resource_lines))
            .where(GmModel.id == package.gm_model_id)
        )
    ).scalar_one()

    baseline = _baseline_snapshot(
        package=package,
        opportunity=opp,
        sow_version=sow_version,
        gm_model=gm_model,
    )

    project = Project(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=sow_version.id,
        gm_model_id=gm_model.id,
        package_id=package.id,
        client_id=opp.client_id,
        title=_default_title(
            client=client,
            opportunity=opp,
            fields=sow_version.extracted_fields,
        ),
        baseline_snapshot_json=baseline,
        created_by=actor_id,
    )
    session.add(project)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="project.created",
        entity="project",
        entity_id=str(project.id),
        before=None,
        after={
            "package_id": str(package.id),
            "opportunity_id": str(opp.id),
            "sow_version_id": str(sow_version.id),
            "gm_model_id": str(gm_model.id),
            "title": project.title,
            "baseline_hash_len": len(str(baseline)),
        },
    )
    return project, True


def serialize(project: Project) -> dict[str, Any]:
    return {
        "id": str(project.id),
        "opportunity_id": str(project.opportunity_id),
        "sow_version_id": str(project.sow_version_id),
        "gm_model_id": str(project.gm_model_id),
        "package_id": str(project.package_id),
        "client_id": str(project.client_id) if project.client_id else None,
        "title": project.title,
        "baseline_snapshot_json": project.baseline_snapshot_json,
        "created_at": (
            project.created_at.isoformat() if project.created_at else None
        ),
        "created_by": (
            str(project.created_by) if project.created_by else None
        ),
        "archived_at": (
            project.archived_at.isoformat() if project.archived_at else None
        ),
    }


__all__ = [
    "create_or_link",
    "existing_for_package",
    "serialize",
]
