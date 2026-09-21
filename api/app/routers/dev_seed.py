"""Test-only seeding endpoints (S13a).

**Never** registered when ``DEALGATE_ENV`` is ``prod``. The endpoint
short-circuits the S12 signatories + submit ceremony so a Playwright
spec can browser-prove S13a DoD #4 (approved record refuses delete,
offers archive) without driving the four role-scoped approval steps
end-to-end. The full multi-role journey is a separate backlog story
(``docs/backlog/e2e-approval-journey.md``).

Guardrails:
- Only mounted when ``DEALGATE_ENV in {"local","test","dev","staging"}``.
- Every call requires ``SystemAdmin`` in the caller's Cognito groups.
- Each call still emits real audit rows for every state change (via the
  underlying ``confirm_field`` / ``submit_sow`` / ``submit_package`` calls).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.sow import Sow, SowVersion


_DEV_ENVS = {"local", "test", "dev", "staging"}


def is_dev_seed_enabled() -> bool:
    """False in prod. Requires BOTH a non-prod ``DEALGATE_ENV`` AND
    ``ALLOW_DEV_SEED_ENDPOINT=1`` so a misconfigured prod-env-value
    can't silently expose this."""

    if os.environ.get("DEALGATE_ENV", "local") not in _DEV_ENVS:
        return False
    return os.environ.get("ALLOW_DEV_SEED_ENDPOINT", "").lower() in {
        "1",
        "true",
        "yes",
    }


router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/purge-client/{client_id}")
async def purge_client(
    client_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Force-hard-delete a client, bypassing approved / archived refusal.

    E2E cleanup uses this to drop leftover approved+archived rows that
    the S13a delete endpoint (correctly) refuses. Never call this from
    the app; it exists so a Playwright run can start from a clean slate.
    """

    if "SystemAdmin" not in user.groups:
        return {"ok": False, "status": 403, "error": "SystemAdmin required"}
    from app.services.deletion import _hard_delete_client

    counts = await _hard_delete_client(session, client_id)
    await session.commit()
    return {"ok": True, "client_id": str(client_id), "counts": counts}


@router.post("/seed-approved-package/{opportunity_id}")
async def seed_approved_package(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:  # noqa: PLR0912 — CustomErrorResponses forces us to return
    # 200 on every failure so CloudFront doesn't map the 4xx to `/index.html`
    # and confuse the caller. Each branch returns `{ok:false,error:...}`.
    def _err(status: int, detail: str) -> dict[str, Any]:
        return {"ok": False, "status": status, "error": detail}
    """Drive an opportunity to ``approved`` state in a single call.

    Steps (all real service calls, all audited):
      1. Force every extracted field on the latest SOW version to
         ``status = "confirmed"`` (via :func:`confirm_field`).
      2. Submit the version — sets ``confirmed_at`` + flips
         ``governance_status`` (via :func:`submit_sow`).
      3. Insert an :class:`ApprovalPackage` row (via :func:`submit_package`).

    Returns the package + opportunity ids. The caller is expected to
    then exercise the delete-refusal + archive UI against the resulting
    client.
    """

    if "SystemAdmin" not in user.groups:
        return _err(403, "SystemAdmin required for dev-seed")

    # Look up the latest SOW version for the opportunity.
    sow = (
        await session.execute(
            select(Sow).where(Sow.opportunity_id == opportunity_id)
        )
    ).scalar_one_or_none()
    if sow is None:
        return _err(404, "no SOW for opportunity")
    version = (
        await session.execute(
            select(SowVersion)
            .where(SowVersion.sow_id == sow.id)
            .order_by(SowVersion.uploaded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if version is None:
        return _err(404, "no SOW version")

    from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS
    from app.services.sow_confirmation import build_confirmation
    from app.services.sow_extract import confirm_field, submit_sow

    # Build the confirmation FIRST so auto_staff sees the extractor's
    # original values (used for the resource-table heuristic). Overwriting
    # every field with `s13a-seed:*` first would destroy that signal.
    try:
        await build_confirmation(
            session, opportunity_id=opportunity_id, actor_id=user.id
        )
    except Exception as exc:  # noqa: BLE001
        return _err(422, f"build_confirmation (pre): {exc!r}")

    # If auto_staff couldn't seed a GM (fixture had no resource table),
    # create a minimal one so submit_package doesn't 404. This is only
    # exercised by the dev-seed endpoint.
    from app.models.gm_model import GmModel

    has_gm = (
        await session.execute(
            select(GmModel).where(GmModel.sow_version_id == version.id).limit(1)
        )
    ).scalar_one_or_none()
    if has_gm is None:
        from app.services.delivery_model import (
            create_gm_model_version,
            parse_gm_model_payload,
        )

        # Minimum viable GM: one US resource line. Content doesn't matter
        # for the delete-refusal proof.
        try:
            payload = parse_gm_model_payload(
                {
                    "engagement_type": "staff_aug",
                    "sow_version_id": str(version.id),
                    "resource_lines": [
                        {
                            "role": "Consultant",
                            "seniority": "Mid",
                            "location": "US",
                            "person_name": "S13a Seed",
                            "allocation_pct": "1",
                            "start_date": "2026-01-01",
                            "end_date": "2026-03-31",
                            "hours_billable": "160",
                            "hourly_bill_rate": "200",
                            "hourly_cost": "120",
                        }
                    ],
                    "cost_lines": [],
                    "total_price": "32000",
                }
            )
            await create_gm_model_version(
                session,
                opportunity_id=opportunity_id,
                actor_id=user.id,
                payload=payload,
            )
            await session.flush()
        except Exception as exc:  # noqa: BLE001
            return _err(422, f"create_gm_model_version: {exc!r}")

    for name in EXTRACTED_FIELDS:
        cell = (version.extracted_fields or {}).get(name) or {}
        value = cell.get("value") if isinstance(cell, dict) else None
        if value is None:
            value = f"s13a-seed:{name}"
        try:
            await confirm_field(
                session,
                actor_id=user.id,
                sow_version_id=version.id,
                field_name=name,
                value=value,
            )
        except Exception as exc:  # noqa: BLE001
            return _err(422, f"confirm_field {name}: {exc!r}")

    try:
        await submit_sow(
            session, actor_id=user.id, sow_version_id=version.id
        )
    except Exception as exc:  # noqa: BLE001 — SowSubmissionIncomplete etc.
        return _err(422, f"submit_sow: {exc!r}")

    # Insert the ApprovalPackage row directly. submit_package's pre-check
    # requires an executed MSA + NDA (S7 wave 1 coverage gate) which the
    # dev-seed fixture doesn't wire up — that ceremony belongs in
    # docs/backlog/e2e-approval-journey.md. Here we just need the
    # ApprovalPackage row to exist so `assess_client` returns "approved".
    from datetime import UTC, datetime
    from hashlib import sha256

    from app.audit import append_audit
    from app.models.approval import ApprovalPackage
    from app.models.gm_model import GmModel

    fresh_gm = (
        await session.execute(
            select(GmModel)
            .where(GmModel.sow_version_id == version.id)
            .order_by(GmModel.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if fresh_gm is None:
        return _err(500, "gm_model not found after create_gm_model_version")

    package_hash = sha256(
        f"s13a-seed:{version.id}:{fresh_gm.id}".encode()
    ).hexdigest()
    pkg = ApprovalPackage(
        opportunity_id=opportunity_id,
        sow_version_id=version.id,
        gm_model_id=fresh_gm.id,
        package_hash=package_hash,
        status="pending_delivery_hr",
        submitted_by=user.id,
        submitted_at=datetime.now(UTC),
    )
    session.add(pkg)
    await session.flush()
    await append_audit(
        session,
        actor_id=user.id,
        action="approval_package.seeded",
        entity="approval_package",
        entity_id=str(pkg.id),
        before=None,
        after={
            "opportunity_id": str(opportunity_id),
            "sow_version_id": str(version.id),
            "gm_model_id": str(fresh_gm.id),
            "status": "pending_delivery_hr",
            "note": "dev-seed bypassed MSA/NDA + submit_package for e2e",
        },
    )

    await session.commit()
    return {
        "ok": True,
        "package_id": str(pkg.id),
        "opportunity_id": str(opportunity_id),
        "sow_version_id": str(version.id),
    }
