"""One delete service every list endpoint routes through (S17).

Contract:

- :func:`delete_sow` removes a SOW at any stage — draft, submitted,
  approved, released or already-signed. Everything descended from the SOW
  goes with it in a single transaction: sow_versions, gm_models,
  approval_packages + approvals + assignments + condition evidence,
  ceo_exceptions, signed_sow_uploads, tasks pointing at the opportunity,
  notifications, sow_upload_jobs, S3 objects. Only one audit line is
  written per SOW deletion: {who, when, sow name, stage, price}.
- :func:`delete_opportunity` fans out to :func:`delete_sow` for every SOW
  on the opportunity, then removes the opportunity row itself.
- :func:`delete_client` fans out to :func:`delete_opportunity` for every
  opportunity on the client, drops the client's agreements, contacts,
  aliases, rate cards, legal entities, and the client itself.
- :func:`assess_client` / :func:`assess_opportunity` / :func:`assess_sow`
  are pure lookups that classify a record's cascade counts for the
  confirm-dialog. S17 always returns `state="draft"` (hard-deletable) —
  the S13a "approved → archive-only" refusal is gone per §2 of the
  directive.
- :func:`live_sow_version_by_hash` is a dedupe helper kept for the SOW
  upload router. Since S17 hard-deletes always, an archived row is
  effectively impossible; the return `archived=True` branch stays only as
  defence-in-depth against schema drift.

Blueprint's append-only audit rule (rule 5) stands: even a hard delete
emits one audit row per SOW, one per opportunity that had no SOWs, and
one per client. The row records what happened and to whom, even after
the target rows are gone.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.approval import Approval, ApprovalPackage
from app.models.approval_routing import (
    ApprovalAssignment,
    ApprovalConditionEvidence,
    ApprovalGroup,
)
from app.models.ceo_exception import CeoException
from app.models.client import Agreement, Client, LegalEntity
from app.models.client_alias import ClientAlias
from app.models.client_contact import ClientContact
from app.models.client_rate_card import ClientRateCard, ClientRateCardRow
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.models.import_batch import ImportBatch, ImportFile
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.models.task import Task

log = logging.getLogger("dealgate.deletion")


class DeletionError(Exception):
    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class DeletionAssessment:
    """Cascade counts for the confirm-dialog.

    S17 always allows hard delete, so ``state`` is always ``"draft"`` —
    kept as a field only because a couple of existing routers/UIs read it.
    """

    state: str = "draft"
    reason: str = ""
    counts: dict[str, int] = field(default_factory=dict)


# --- helpers --------------------------------------------------------------


async def _sow_ids_for_client(session: AsyncSession, client_id: uuid.UUID) -> list[uuid.UUID]:
    opp_ids = list(
        (
            await session.execute(
                select(Opportunity.id).where(Opportunity.client_id == client_id)
            )
        ).scalars()
    )
    if not opp_ids:
        return []
    return list(
        (
            await session.execute(
                select(Sow.id).where(Sow.opportunity_id.in_(opp_ids))
            )
        ).scalars()
    )


async def _s3_delete_sow_files(file_keys: list[str]) -> None:
    """Best-effort S3 cleanup. Failures do not roll back the DB delete —
    the row is the source of truth for existence."""

    if not file_keys:
        return
    try:
        from app.integrations.s3_sow import _client

        s3 = _client()
        # Prefer batched delete for efficiency; group by bucket by reading
        # the SOW bucket name from env.
        import os

        bucket = os.environ.get("SOW_BUCKET")
        if not bucket:
            return
        # S3 delete-objects caps at 1000 keys per call.
        for i in range(0, len(file_keys), 1000):
            chunk = file_keys[i : i + 1000]
            s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in chunk]},
            )
    except Exception as exc:  # noqa: BLE001 — best-effort
        log.info("s3_cleanup_failed", extra={"error": str(exc)[:200]})


async def _s3_delete_agreement_files(file_keys: list[str]) -> None:
    if not file_keys:
        return
    try:
        from app.integrations.s3_sow import _client

        s3 = _client()
        import os

        bucket = os.environ.get(
            "AGREEMENTS_BUCKET", ""
        )
        if not bucket:
            return
        for i in range(0, len(file_keys), 1000):
            chunk = file_keys[i : i + 1000]
            s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in chunk]},
            )
    except Exception as exc:  # noqa: BLE001
        log.info("s3_cleanup_failed_agreements", extra={"error": str(exc)[:200]})


def _price_from_sow(version: SowVersion | None) -> str | None:
    if version is None or not version.extracted_fields:
        return None
    fields = version.extracted_fields or {}
    price = fields.get("price")
    if isinstance(price, dict):
        return price.get("value") if isinstance(price.get("value"), str) else None
    if isinstance(price, str):
        return price
    return None


def _stage_from_opportunity(opp: Opportunity | None) -> str:
    if opp is None:
        return "unknown"
    return opp.governance_status or "unknown"


# --- SOW-scoped delete ---------------------------------------------------


@dataclass(frozen=True)
class SowDeletionSummary:
    sow_id: uuid.UUID
    sow_title: str
    stage: str
    price: str | None
    counts: dict[str, int]


async def _sow_cascade_counts(
    session: AsyncSession, sow_ids: list[uuid.UUID]
) -> dict[str, int]:
    if not sow_ids:
        return {}
    counts: dict[str, int] = {}
    version_ids = list(
        (
            await session.execute(select(SowVersion.id).where(SowVersion.sow_id.in_(sow_ids)))
        ).scalars()
    )
    counts["sow_versions"] = len(version_ids)
    if version_ids:
        gm_ids = list(
            (
                await session.execute(
                    select(GmModel.id).where(GmModel.sow_version_id.in_(version_ids))
                )
            ).scalars()
        )
        counts["gm_models"] = len(gm_ids)
        if gm_ids:
            counts["resource_lines"] = int(
                (
                    await session.execute(
                        select(func.count(ResourceLine.id)).where(
                            ResourceLine.gm_model_id.in_(gm_ids)
                        )
                    )
                ).scalar_one()
            )
            counts["cost_lines"] = int(
                (
                    await session.execute(
                        select(func.count(CostLine.id)).where(
                            CostLine.gm_model_id.in_(gm_ids)
                        )
                    )
                ).scalar_one()
            )
    opp_ids = list(
        (
            await session.execute(select(Sow.opportunity_id).where(Sow.id.in_(sow_ids)))
        ).scalars()
    )
    if opp_ids:
        pkg_ids_for_count = list(
            (
                await session.execute(
                    select(ApprovalPackage.id).where(
                        ApprovalPackage.opportunity_id.in_(opp_ids)
                    )
                )
            ).scalars()
        )
        counts["approval_packages"] = len(pkg_ids_for_count)
        if pkg_ids_for_count:
            counts["tasks"] = int(
                (
                    await session.execute(
                        select(func.count(ApprovalAssignment.task_id)).where(
                            ApprovalAssignment.package_id.in_(pkg_ids_for_count),
                            ApprovalAssignment.task_id.is_not(None),
                        )
                    )
                ).scalar_one()
            )
        else:
            counts["tasks"] = 0
    return counts


async def _sow_has_submitted_package(
    session: AsyncSession, sow_id: uuid.UUID
) -> bool:
    """S20 W3 D6 — a SOW is "submitted or later" when at least one
    approval_package exists for it (regardless of package status —
    a rejected package still means a decision was recorded)."""

    version_ids = list(
        (
            await session.execute(
                select(SowVersion.id).where(SowVersion.sow_id == sow_id)
            )
        ).scalars()
    )
    if not version_ids:
        return False
    row = (
        await session.execute(
            select(ApprovalPackage.id)
            .where(ApprovalPackage.sow_version_id.in_(version_ids))
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def archive_sow(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    sow_id: uuid.UUID,
    reason: str = "s20_w3_governed_archive",
) -> SowDeletionSummary:
    """S20 W3 D6 — archive a governed SOW.

    Any SOW that has been submitted for approval (approved, rejected,
    released, or voided) is a governed record and cannot be hard
    deleted (CLAUDE.md rule 4 + review §"Define deletion by state and
    authority"). Archiving marks ``sow.archived_at`` + ``archived_by``
    + ``archived_reason``; the rows and their audit trail survive.
    """

    sow = await session.get(Sow, sow_id)
    if sow is None:
        raise DeletionError("sow not found", status_code=404)
    if sow.archived_at is not None:
        # Idempotent — a repeat archive is a no-op summary.
        versions = list(
            (
                await session.execute(
                    select(SowVersion).where(SowVersion.sow_id == sow_id)
                )
            ).scalars()
        )
        counts = await _sow_cascade_counts(session, [sow_id])
        return SowDeletionSummary(
            sow_id=sow_id,
            sow_title=f"SOW {str(sow_id)[:8]} (already archived)",
            stage="archived",
            price=_price_from_sow(max(versions, key=lambda v: v.uploaded_at) if versions else None),
            counts=counts,
        )

    opp = await session.get(Opportunity, sow.opportunity_id)
    versions = list(
        (
            await session.execute(select(SowVersion).where(SowVersion.sow_id == sow_id))
        ).scalars()
    )
    latest_version = max(versions, key=lambda v: v.uploaded_at) if versions else None
    price = _price_from_sow(latest_version)
    stage = _stage_from_opportunity(opp)
    counts = await _sow_cascade_counts(session, [sow_id])

    before = {
        "archived_at": None,
        "archived_reason": None,
    }
    sow.archived_at = datetime.now(UTC)
    sow.archived_by = actor_id
    sow.archived_reason = reason
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="sow.archived",
        entity="sow",
        entity_id=str(sow_id),
        before=before,
        after={
            "archived_at": sow.archived_at.isoformat(),
            "archived_reason": reason,
            "stage": stage,
            "price": price,
        },
    )

    fields = (latest_version.extracted_fields or {}) if latest_version else {}
    title_cell = fields.get("sow_title") if isinstance(fields, dict) else None
    if isinstance(title_cell, dict):
        sow_title = str(title_cell.get("value") or "").strip() or f"SOW {str(sow_id)[:8]}"
    else:
        sow_title = f"SOW {str(sow_id)[:8]}"

    return SowDeletionSummary(
        sow_id=sow_id,
        sow_title=sow_title,
        stage=stage,
        price=price,
        counts=counts,
    )


async def delete_sow(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    sow_id: uuid.UUID,
    allow_governed: bool = False,
) -> SowDeletionSummary:
    sow = await session.get(Sow, sow_id)
    if sow is None:
        raise DeletionError("sow not found", status_code=404)

    # S20 W3 D6: hard delete is only permitted for a draft SOW that has
    # never been submitted for approval. A SOW with at least one
    # approval_package (in any status) is a governed record — the
    # caller must archive instead. Hard delete would erase decision
    # history that CLAUDE.md rule 4 says must survive.
    #
    # S21-1d · root-cause for client cascade: a non-mirror client
    # (hubspot_company_id IS NULL) is e2e / scratch data, not a
    # governed customer record. `delete_client` forwards
    # `allow_governed=True` for those; the governance check still
    # protects every mirror-sourced path.
    if not allow_governed and await _sow_has_submitted_package(session, sow_id):
        raise DeletionError(
            "this SOW has been submitted for approval and cannot be "
            "hard-deleted — archive it instead (retains history).",
            status_code=409,
        )

    opp = await session.get(Opportunity, sow.opportunity_id)
    versions = list(
        (
            await session.execute(select(SowVersion).where(SowVersion.sow_id == sow_id))
        ).scalars()
    )
    latest_version = max(versions, key=lambda v: v.uploaded_at) if versions else None
    price = _price_from_sow(latest_version)
    stage = _stage_from_opportunity(opp)
    fields = (latest_version.extracted_fields or {}) if latest_version else {}
    title_cell = fields.get("sow_title") if isinstance(fields, dict) else None
    if isinstance(title_cell, dict):
        sow_title = str(title_cell.get("value") or "").strip()
    else:
        sow_title = ""
    if not sow_title:
        title_cell = fields.get("title") if isinstance(fields, dict) else None
        if isinstance(title_cell, dict):
            sow_title = str(title_cell.get("value") or "").strip()
    if not sow_title:
        sow_title = f"SOW {str(sow_id)[:8]}"

    counts = await _sow_cascade_counts(session, [sow_id])

    # -- inside a single transaction --
    version_ids = [v.id for v in versions]
    file_keys = [v.file_s3_key for v in versions if v.file_s3_key]

    if opp is not None:
        opp_id = opp.id
        # approvals + assignments + evidence + exceptions + signed uploads
        pkg_ids = list(
            (
                await session.execute(
                    select(ApprovalPackage.id).where(ApprovalPackage.opportunity_id == opp_id)
                )
            ).scalars()
        )
        # Tasks tied to the opportunity: today they're linked via
        # ApprovalAssignment.task_id (S14b review tasks). Collect + drop
        # first so the assignment cascade can proceed.
        task_ids_via_assignment: list[uuid.UUID] = []
        if pkg_ids:
            task_ids_via_assignment = list(
                (
                    await session.execute(
                        select(ApprovalAssignment.task_id).where(
                            ApprovalAssignment.package_id.in_(pkg_ids),
                            ApprovalAssignment.task_id.is_not(None),
                        )
                    )
                ).scalars()
            )
            await session.execute(
                sa_delete(SignedSowUpload).where(SignedSowUpload.package_id.in_(pkg_ids))
            )
            await session.execute(
                sa_delete(ApprovalConditionEvidence).where(
                    ApprovalConditionEvidence.package_id.in_(pkg_ids)
                )
            )
            await session.execute(
                sa_delete(ApprovalAssignment).where(ApprovalAssignment.package_id.in_(pkg_ids))
            )
            await session.execute(
                sa_delete(Approval).where(Approval.package_id.in_(pkg_ids))
            )
            await session.execute(
                sa_delete(CeoException).where(CeoException.package_id.in_(pkg_ids))
            )
            await session.execute(
                sa_delete(ApprovalPackage).where(ApprovalPackage.id.in_(pkg_ids))
            )
        if task_ids_via_assignment:
            await session.execute(sa_delete(Task).where(Task.id.in_(task_ids_via_assignment)))
        # notifications tied to the opportunity/package
        await session.execute(
            sa_delete(Notification).where(
                Notification.related_entity.in_(("opportunity", "approval_package", "sow")),
                Notification.related_entity_id.in_(
                    [str(opp_id)] + [str(p) for p in pkg_ids]
                ),
            )
        )

    if version_ids:
        gm_ids = list(
            (
                await session.execute(
                    select(GmModel.id).where(GmModel.sow_version_id.in_(version_ids))
                )
            ).scalars()
        )
        if gm_ids:
            await session.execute(
                sa_delete(ResourceLine).where(ResourceLine.gm_model_id.in_(gm_ids))
            )
            await session.execute(
                sa_delete(CostLine).where(CostLine.gm_model_id.in_(gm_ids))
            )
            await session.execute(sa_delete(GmModel).where(GmModel.id.in_(gm_ids)))
        # SOW upload jobs referencing this SOW's versions/opportunity
        await session.execute(
            sa_delete(SowUploadJob).where(SowUploadJob.sow_version_id.in_(version_ids))
        )
        # Clear superseded_by pointers that reference deletables (SQLite has no ON DELETE SET NULL here)
        await session.execute(
            sa_delete(SowVersion).where(SowVersion.id.in_(version_ids))
        )

    await session.execute(sa_delete(Sow).where(Sow.id == sow_id))

    await append_audit(
        session,
        actor_id=actor_id,
        action="sow.deleted",
        entity="sow",
        entity_id=str(sow_id),
        before={
            "sow_id": str(sow_id),
            "sow_title": sow_title,
            "stage": stage,
            "price": price,
        },
        after=None,
    )

    await _s3_delete_sow_files(file_keys)

    return SowDeletionSummary(
        sow_id=sow_id,
        sow_title=sow_title,
        stage=stage,
        price=price,
        counts=counts,
    )


# --- Opportunity- and Client-scoped delete ------------------------------


async def delete_opportunity(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    opportunity_id: uuid.UUID,
    allow_governed: bool = False,
) -> DeletionAssessment:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise DeletionError("opportunity not found", status_code=404)
    sow_ids = list(
        (
            await session.execute(select(Sow.id).where(Sow.opportunity_id == opportunity_id))
        ).scalars()
    )
    counts: dict[str, int] = {"sows": len(sow_ids)}
    for sow_id in sow_ids:
        summary = await delete_sow(
            session, actor_id=actor_id, sow_id=sow_id, allow_governed=allow_governed
        )
        for k, v in summary.counts.items():
            counts[k] = counts.get(k, 0) + v
    await session.execute(sa_delete(Opportunity).where(Opportunity.id == opportunity_id))
    await append_audit(
        session,
        actor_id=actor_id,
        action="opportunity.deleted",
        entity="opportunity",
        entity_id=str(opportunity_id),
        before={"opportunity_id": str(opportunity_id), "counts": counts},
        after=None,
    )
    return DeletionAssessment(state="draft", reason="hard delete (S17)", counts=counts)


async def delete_client(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    client_id: uuid.UUID,
) -> DeletionAssessment:
    client = await session.get(Client, client_id)
    if client is None:
        raise DeletionError("client not found", status_code=404)
    # S21-1d root-cause fix: a client with no HubSpot mirror link is
    # scratch / e2e / rename-stage data, not a governed customer
    # record. Governed SOW guard on `delete_sow` is bypassed only on
    # this path. Mirror clients (hubspot_company_id IS NOT NULL) still
    # route through the governance gate — CLAUDE.md rule 4 holds for
    # anything that could reach HubSpot writeback (D2).
    allow_governed = client.hubspot_company_id is None
    counts: dict[str, int] = {}
    # Cascade to opportunities → SOWs.
    opp_ids = list(
        (
            await session.execute(
                select(Opportunity.id).where(Opportunity.client_id == client_id)
            )
        ).scalars()
    )
    counts["opportunities"] = len(opp_ids)
    for opp_id in opp_ids:
        summary = await delete_opportunity(
            session,
            actor_id=actor_id,
            opportunity_id=opp_id,
            allow_governed=allow_governed,
        )
        for k, v in summary.counts.items():
            counts[k] = counts.get(k, 0) + v
    # Client-scoped children.
    agreements = list(
        (
            await session.execute(select(Agreement).where(Agreement.client_id == client_id))
        ).scalars()
    )
    if agreements:
        await _s3_delete_agreement_files([a.file_key for a in agreements])
        await session.execute(sa_delete(Agreement).where(Agreement.client_id == client_id))
        counts["agreements"] = len(agreements)
    await session.execute(
        sa_delete(ClientContact).where(ClientContact.client_id == client_id)
    )
    await session.execute(sa_delete(ClientAlias).where(ClientAlias.client_id == client_id))
    # Rate cards + rows
    rate_card_ids = list(
        (
            await session.execute(
                select(ClientRateCard.id).where(ClientRateCard.client_id == client_id)
            )
        ).scalars()
    )
    if rate_card_ids:
        await session.execute(
            sa_delete(ClientRateCardRow).where(
                ClientRateCardRow.rate_card_id.in_(rate_card_ids)
            )
        )
        await session.execute(
            sa_delete(ClientRateCard).where(ClientRateCard.id.in_(rate_card_ids))
        )
    # Legal entities
    await session.execute(sa_delete(LegalEntity).where(LegalEntity.client_id == client_id))
    await session.execute(sa_delete(Client).where(Client.id == client_id))

    await append_audit(
        session,
        actor_id=actor_id,
        action="client.deleted",
        entity="client",
        entity_id=str(client_id),
        before={"client_id": str(client_id), "name": client.name, "counts": counts},
        after=None,
    )
    return DeletionAssessment(state="draft", reason="hard delete (S17)", counts=counts)


# --- assessment helpers (used by the confirm-dialog) -----------------------


async def assess_client(
    session: AsyncSession, client_id: uuid.UUID
) -> DeletionAssessment:
    sow_ids = await _sow_ids_for_client(session, client_id)
    counts = await _sow_cascade_counts(session, sow_ids)
    counts["sows"] = len(sow_ids)
    counts["opportunities"] = int(
        (
            await session.execute(
                select(func.count(Opportunity.id)).where(Opportunity.client_id == client_id)
            )
        ).scalar_one()
    )
    counts["agreements"] = int(
        (
            await session.execute(
                select(func.count(Agreement.id)).where(Agreement.client_id == client_id)
            )
        ).scalar_one()
    )
    return DeletionAssessment(state="draft", reason="hard delete (S17)", counts=counts)


async def assess_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> DeletionAssessment:
    sow_ids = list(
        (
            await session.execute(select(Sow.id).where(Sow.opportunity_id == opportunity_id))
        ).scalars()
    )
    counts = await _sow_cascade_counts(session, sow_ids)
    counts["sows"] = len(sow_ids)
    return DeletionAssessment(state="draft", reason="hard delete (S17)", counts=counts)


async def assess_sow(session: AsyncSession, sow_id: uuid.UUID) -> DeletionAssessment:
    """S20 W3 D6: report whether the SOW is hard-deletable (never
    submitted) or must be archived (submitted / approved / executed).

    ``state`` values:
      - ``"draft"`` — no approval_package exists; hard delete allowed.
      - ``"governed"`` — at least one approval_package; archive only.
    """

    counts = await _sow_cascade_counts(session, [sow_id])
    is_governed = await _sow_has_submitted_package(session, sow_id)
    return DeletionAssessment(
        state="governed" if is_governed else "draft",
        reason=(
            "governed record — archive retains audit history"
            if is_governed
            else "no approval submitted — hard delete allowed"
        ),
        counts=counts,
    )


# --- dedupe helper ---------------------------------------------------------


@dataclass(frozen=True)
class DedupeHit:
    sow_version_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    file_hash: str
    archived: bool


async def live_sow_version_by_hash(
    session: AsyncSession, file_hash: str
) -> DedupeHit | None:
    """Return a hit ONLY if a live sow_version has the hash.

    S17 hard-deletes always, so ``archived=True`` is no longer expected in
    practice; the field remains so upstream callers keep their shape.
    """

    stmt = (
        select(SowVersion, Sow.opportunity_id, Sow.archived_at.label("sow_arch"))
        .join(Sow, Sow.id == SowVersion.sow_id)
        .where(SowVersion.file_hash == file_hash)
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    version, opp_id, sow_archived = row
    return DedupeHit(
        sow_version_id=version.id,
        opportunity_id=opp_id,
        file_hash=version.file_hash,
        archived=sow_archived is not None,
    )


# --- batch cleanup -------------------------------------------------------


async def delete_import_batch(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    batch_id: uuid.UUID,
) -> DeletionAssessment:
    """Delete a bulk-import batch + its files. No SOW cascade — bulk import
    is a separate lineage."""

    batch = await session.get(ImportBatch, batch_id)
    if batch is None:
        raise DeletionError("import batch not found", status_code=404)
    counts = {
        "import_files": int(
            (
                await session.execute(
                    select(func.count(ImportFile.id)).where(ImportFile.batch_id == batch_id)
                )
            ).scalar_one()
        )
    }
    await session.execute(sa_delete(ImportFile).where(ImportFile.batch_id == batch_id))
    await session.execute(sa_delete(ImportBatch).where(ImportBatch.id == batch_id))
    await append_audit(
        session,
        actor_id=actor_id,
        action="import_batch.deleted",
        entity="import_batch",
        entity_id=str(batch_id),
        before={"counts": counts},
        after=None,
    )
    return DeletionAssessment(state="draft", reason="hard delete (S17)", counts=counts)


# --- back-compat aliases ---------------------------------------------------
# Some pre-S17 callers referenced the S13a assess/archive names. The
# archive endpoints now just hard-delete under the hood so the UI keeps
# working while it's rewritten to a single Delete action.


async def archive_client(
    session: AsyncSession, *, actor_id: uuid.UUID | None, client_id: uuid.UUID, reason: str
) -> DeletionAssessment:
    _ = reason
    return await delete_client(session, actor_id=actor_id, client_id=client_id)


async def archive_opportunity(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    opportunity_id: uuid.UUID,
    reason: str,
) -> DeletionAssessment:
    _ = reason
    return await delete_opportunity(session, actor_id=actor_id, opportunity_id=opportunity_id)


async def delete_sow_version(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    sow_version_id: uuid.UUID,
) -> DeletionAssessment:
    """S13a compat: delete a version. In S17 the coarser unit is the SOW;
    delete the whole SOW when asked to delete a version."""

    version = await session.get(SowVersion, sow_version_id)
    if version is None:
        raise DeletionError("sow_version not found", status_code=404)
    summary = await delete_sow(session, actor_id=actor_id, sow_id=version.sow_id)
    return DeletionAssessment(state="draft", reason="hard delete (S17)", counts=summary.counts)


__all__ = [
    "DedupeHit",
    "DeletionAssessment",
    "DeletionError",
    "SowDeletionSummary",
    "archive_client",
    "archive_opportunity",
    "archive_sow",
    "assess_client",
    "assess_opportunity",
    "assess_sow",
    "delete_client",
    "delete_import_batch",
    "delete_opportunity",
    "delete_sow",
    "delete_sow_version",
    "live_sow_version_by_hash",
]
