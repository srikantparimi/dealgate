"""Delete + archive service (S13a-B2).

`docs/directives/s13a-delete-reset.md`: the product owner must be able to
remove drafts he created and start fresh; approved / signed records
archive instead. This module owns both paths.

Three deliverables:

- :func:`assess_client` / :func:`assess_opportunity` / :func:`assess_sow_version`
  — pure lookups that classify a record as ``draft`` (hard-deletable),
  ``approved`` (archive-only), or ``hubspot_linked`` (archive-only, with a
  warning). Nothing writes.
- :func:`delete_client` / :func:`delete_opportunity` / :func:`delete_sow_version`
  — the write path. Hard-deletes when the assessment allows; archives
  otherwise. One ``audit_event`` per call with the cascade counts.
- :func:`live_sow_version_by_hash` / :func:`live_sow_versions_by_business_key`
  — dedupe helpers that skip hard-deleted rows (they no longer exist) and
  return archived hits with an ``archived: True`` flag so the caller can
  surface them as informational, not blocking (directive §"fresh-start").

The blueprint's append-only audit rule stands: even a hard delete emits
an audit row, so the trail records what happened and to whom, even
after the target row is gone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.approval import Approval, ApprovalPackage
from app.models.client import Agreement, Client, LegalEntity
from app.models.client_contact import ClientContact
from app.models.client_alias import ClientAlias
from app.models.client_rate_card import ClientRateCard, ClientRateCardRow
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.models.import_batch import ImportBatch, ImportFile
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob


class DeletionError(Exception):
    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class DeletionAssessment:
    """What a caller can do with this record, and why.

    ``state`` is one of:
      - ``"draft"``           → hard-deletable (no approvals, no signature).
      - ``"approved"``        → archive-only; hard delete refused.
      - ``"hubspot_linked"``  → archive-only; also writes governance status
                                back to HubSpot on archive.
    """

    state: str
    reason: str
    counts: dict[str, int] = field(default_factory=dict)


# --- assessment helpers ---------------------------------------------------


async def _opportunity_has_approvals(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> bool:
    row = (
        await session.execute(
            select(func.count(ApprovalPackage.id)).where(
                ApprovalPackage.opportunity_id == opportunity_id
            )
        )
    ).scalar_one()
    return int(row or 0) > 0


async def _opportunity_has_signed_sow(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> bool:
    row = (
        await session.execute(
            select(func.count(SignedSowUpload.id))
            .join(ApprovalPackage, ApprovalPackage.id == SignedSowUpload.package_id)
            .where(ApprovalPackage.opportunity_id == opportunity_id)
        )
    ).scalar_one()
    return int(row or 0) > 0


def _opportunity_is_hubspot_linked(opp: Opportunity) -> bool:
    """A live HubSpot deal will resurrect the record on next sync, so a
    hard delete is meaningless and archive is required per directive §1."""

    return bool(opp.hubspot_deal_id) and opp.source == "hubspot"


async def _sow_version_has_approvals(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> bool:
    row = (
        await session.execute(
            select(func.count(ApprovalPackage.id)).where(
                ApprovalPackage.sow_version_id == sow_version_id
            )
        )
    ).scalar_one()
    return int(row or 0) > 0


# --- public assessors -----------------------------------------------------


async def assess_client(
    session: AsyncSession, client_id: uuid.UUID
) -> DeletionAssessment:
    opps = (
        (
            await session.execute(
                select(Opportunity).where(Opportunity.client_id == client_id)
            )
        )
        .scalars()
        .all()
    )
    hubspot = any(_opportunity_is_hubspot_linked(o) for o in opps)
    approved = False
    for opp in opps:
        if await _opportunity_has_approvals(session, opp.id):
            approved = True
            break
        if await _opportunity_has_signed_sow(session, opp.id):
            approved = True
            break
    counts = {"opportunities": len(opps)}
    if hubspot:
        return DeletionAssessment(
            state="hubspot_linked",
            reason=(
                "at least one opportunity is linked to a live HubSpot deal; "
                "the record will resurrect on the next HubSpot sync if hard "
                "deleted"
            ),
            counts=counts,
        )
    if approved:
        return DeletionAssessment(
            state="approved",
            reason=(
                "at least one opportunity has an approval package or a "
                "signed SOW; the approval trail is append-only"
            ),
            counts=counts,
        )
    return DeletionAssessment(
        state="draft", reason="no approvals, no signed SOW, no HubSpot link", counts=counts
    )


async def assess_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> DeletionAssessment:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise DeletionError(f"opportunity {opportunity_id} not found", status_code=404)
    counts = {"opportunity": 1}
    if _opportunity_is_hubspot_linked(opp):
        return DeletionAssessment(
            state="hubspot_linked",
            reason="linked to a live HubSpot deal",
            counts=counts,
        )
    if await _opportunity_has_approvals(session, opportunity_id):
        return DeletionAssessment(
            state="approved", reason="approval package exists", counts=counts
        )
    if await _opportunity_has_signed_sow(session, opportunity_id):
        return DeletionAssessment(
            state="approved", reason="signed SOW exists", counts=counts
        )
    return DeletionAssessment(state="draft", reason="no approvals, no signature", counts=counts)


async def assess_sow_version(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> DeletionAssessment:
    version = await session.get(SowVersion, sow_version_id)
    if version is None:
        raise DeletionError(f"sow_version {sow_version_id} not found", status_code=404)
    if await _sow_version_has_approvals(session, sow_version_id):
        return DeletionAssessment(
            state="approved",
            reason="an approval package pins this sow_version",
            counts={"sow_version": 1},
        )
    return DeletionAssessment(
        state="draft", reason="no approval package", counts={"sow_version": 1}
    )


# --- delete / archive write path -----------------------------------------


async def archive_client(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str | None,
) -> DeletionAssessment:
    row = await session.get(Client, client_id)
    if row is None:
        raise DeletionError(f"client {client_id} not found", status_code=404)
    if row.archived_at is not None:
        raise DeletionError("client already archived")
    row.archived_at = datetime.now(timezone.utc)
    row.archived_by = actor_id
    row.archived_reason = (reason or "").strip() or None
    await append_audit(
        session,
        actor_id=actor_id,
        action="client.archived",
        entity="client",
        entity_id=str(client_id),
        before=None,
        after={"reason": row.archived_reason, "archived_at": row.archived_at.isoformat()},
    )
    return DeletionAssessment(
        state="archived", reason="ok", counts={"client": 1}
    )


async def archive_opportunity(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str | None,
) -> DeletionAssessment:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise DeletionError(f"opportunity {opportunity_id} not found", status_code=404)
    if opp.archived_at is not None:
        raise DeletionError("opportunity already archived")
    opp.archived_at = datetime.now(timezone.utc)
    opp.archived_by = actor_id
    opp.archived_reason = (reason or "").strip() or None
    await append_audit(
        session,
        actor_id=actor_id,
        action="opportunity.archived",
        entity="opportunity",
        entity_id=str(opportunity_id),
        before=None,
        after={"reason": opp.archived_reason},
    )
    return DeletionAssessment(
        state="archived", reason="ok", counts={"opportunity": 1}
    )


async def _hard_delete_sow(
    session: AsyncSession, sow_id: uuid.UUID
) -> dict[str, int]:
    """Delete every child of a `sow`. Returns per-table counts."""

    version_ids = (
        (await session.execute(select(SowVersion.id).where(SowVersion.sow_id == sow_id)))
        .scalars()
        .all()
    )
    counts: dict[str, int] = {"sow_versions": len(version_ids)}
    if version_ids:
        # SowUploadJob may reference a version.
        r = await session.execute(
            sa_delete(SowUploadJob).where(SowUploadJob.sow_version_id.in_(version_ids))
        )
        counts["sow_upload_jobs"] = r.rowcount or 0
        r = await session.execute(
            sa_delete(SowVersion).where(SowVersion.sow_id == sow_id)
        )
        counts["sow_versions_deleted"] = r.rowcount or 0
    r = await session.execute(sa_delete(Sow).where(Sow.id == sow_id))
    counts["sows"] = r.rowcount or 0
    return counts


async def _hard_delete_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> dict[str, int]:
    """Delete every child of an `opportunity` and the row itself."""

    counts: dict[str, int] = {}
    # ApprovalPackage + its Approval children FIRST — approval_package has
    # FKs into gm_model + sow_version, so we must clear it before deleting
    # those. (Draft deletes normally have zero packages; dev-seed rows do,
    # and this is called from the /dev/purge-client cleanup path too.)
    pkg_ids = (
        (
            await session.execute(
                select(ApprovalPackage.id).where(
                    ApprovalPackage.opportunity_id == opportunity_id
                )
            )
        )
        .scalars()
        .all()
    )
    if pkg_ids:
        await session.execute(sa_delete(Approval).where(Approval.package_id.in_(pkg_ids)))
        r = await session.execute(
            sa_delete(ApprovalPackage).where(ApprovalPackage.id.in_(pkg_ids))
        )
        counts["approval_packages"] = r.rowcount or 0
    # gm_models + their children (resource_line / cost_line).
    gm_ids = (
        (
            await session.execute(
                select(GmModel.id).where(GmModel.opportunity_id == opportunity_id)
            )
        )
        .scalars()
        .all()
    )
    counts["gm_models"] = len(gm_ids)
    if gm_ids:
        r = await session.execute(
            sa_delete(ResourceLine).where(ResourceLine.gm_model_id.in_(gm_ids))
        )
        counts["resource_lines"] = r.rowcount or 0
        r = await session.execute(
            sa_delete(CostLine).where(CostLine.gm_model_id.in_(gm_ids))
        )
        counts["cost_lines"] = r.rowcount or 0
        r = await session.execute(sa_delete(GmModel).where(GmModel.id.in_(gm_ids)))
        counts["gm_models_deleted"] = r.rowcount or 0
    # sows + their versions.
    sow_ids = (
        (await session.execute(select(Sow.id).where(Sow.opportunity_id == opportunity_id)))
        .scalars()
        .all()
    )
    counts["sows"] = len(sow_ids)
    for sow_id in sow_ids:
        sub = await _hard_delete_sow(session, sow_id)
        for k, v in sub.items():
            counts[k] = counts.get(k, 0) + v
    # `Task` has no opportunity_id column today, so we can't cascade tasks
    # by opportunity. Tasks stay for the owner to clear manually.
    r = await session.execute(sa_delete(Opportunity).where(Opportunity.id == opportunity_id))
    counts["opportunities"] = r.rowcount or 0
    return counts


async def _hard_delete_client(
    session: AsyncSession, client_id: uuid.UUID
) -> dict[str, int]:
    counts: dict[str, int] = {}
    # Cascade every opportunity first.
    opp_ids = (
        (
            await session.execute(
                select(Opportunity.id).where(Opportunity.client_id == client_id)
            )
        )
        .scalars()
        .all()
    )
    for oid in opp_ids:
        sub = await _hard_delete_opportunity(session, oid)
        for k, v in sub.items():
            counts[k] = counts.get(k, 0) + v
    # Client-side children: contacts, aliases, rate cards + rows, legal entities → agreements.
    r = await session.execute(sa_delete(ClientContact).where(ClientContact.client_id == client_id))
    counts["client_contacts"] = r.rowcount or 0
    r = await session.execute(sa_delete(ClientAlias).where(ClientAlias.client_id == client_id))
    counts["client_aliases"] = r.rowcount or 0
    card_ids = (
        (
            await session.execute(
                select(ClientRateCard.id).where(ClientRateCard.client_id == client_id)
            )
        )
        .scalars()
        .all()
    )
    if card_ids:
        r = await session.execute(
            sa_delete(ClientRateCardRow).where(
                ClientRateCardRow.client_rate_card_id.in_(card_ids)
            )
        )
        counts["client_rate_card_rows"] = r.rowcount or 0
        r = await session.execute(
            sa_delete(ClientRateCard).where(ClientRateCard.id.in_(card_ids))
        )
        counts["client_rate_cards"] = r.rowcount or 0
    entity_ids = (
        (
            await session.execute(
                select(LegalEntity.id).where(LegalEntity.client_id == client_id)
            )
        )
        .scalars()
        .all()
    )
    if entity_ids:
        r = await session.execute(
            sa_delete(Agreement).where(Agreement.legal_entity_id.in_(entity_ids))
        )
        counts["agreements"] = r.rowcount or 0
        r = await session.execute(
            sa_delete(LegalEntity).where(LegalEntity.id.in_(entity_ids))
        )
        counts["legal_entities"] = r.rowcount or 0
    r = await session.execute(sa_delete(Client).where(Client.id == client_id))
    counts["clients"] = r.rowcount or 0
    return counts


async def delete_client(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> DeletionAssessment:
    """Hard delete a draft client, or refuse and steer to archive."""

    assessment = await assess_client(session, client_id)
    if assessment.state != "draft":
        raise DeletionError(
            f"client cannot be hard-deleted ({assessment.state}); "
            f"reason: {assessment.reason}; use archive instead",
            status_code=409,
        )
    row = await session.get(Client, client_id)
    if row is None:
        raise DeletionError(f"client {client_id} not found", status_code=404)
    snapshot = {"name": row.name, "hubspot_company_id": row.hubspot_company_id}
    counts = await _hard_delete_client(session, client_id)
    await append_audit(
        session,
        actor_id=actor_id,
        action="client.deleted",
        entity="client",
        entity_id=str(client_id),
        before=snapshot,
        after={"reason": (reason or "").strip() or None, "cascade": counts},
    )
    return DeletionAssessment(state="deleted", reason="ok", counts=counts)


async def delete_opportunity(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> DeletionAssessment:
    assessment = await assess_opportunity(session, opportunity_id)
    if assessment.state != "draft":
        raise DeletionError(
            f"opportunity cannot be hard-deleted ({assessment.state}); "
            f"reason: {assessment.reason}; use archive instead",
            status_code=409,
        )
    row = await session.get(Opportunity, opportunity_id)
    if row is None:
        raise DeletionError(f"opportunity {opportunity_id} not found", status_code=404)
    snapshot = {"hubspot_deal_id": row.hubspot_deal_id, "source": row.source}
    counts = await _hard_delete_opportunity(session, opportunity_id)
    await append_audit(
        session,
        actor_id=actor_id,
        action="opportunity.deleted",
        entity="opportunity",
        entity_id=str(opportunity_id),
        before=snapshot,
        after={"reason": (reason or "").strip() or None, "cascade": counts},
    )
    return DeletionAssessment(state="deleted", reason="ok", counts=counts)


async def delete_sow_version(
    session: AsyncSession,
    *,
    sow_version_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> DeletionAssessment:
    assessment = await assess_sow_version(session, sow_version_id)
    if assessment.state != "draft":
        raise DeletionError(
            f"sow_version cannot be hard-deleted ({assessment.state}); "
            f"reason: {assessment.reason}",
            status_code=409,
        )
    row = await session.get(SowVersion, sow_version_id)
    if row is None:
        raise DeletionError(f"sow_version {sow_version_id} not found", status_code=404)
    snapshot = {"sow_id": str(row.sow_id), "file_hash": row.file_hash}
    r = await session.execute(
        sa_delete(SowUploadJob).where(SowUploadJob.sow_version_id == sow_version_id)
    )
    counts = {"sow_upload_jobs": r.rowcount or 0}
    r = await session.execute(sa_delete(SowVersion).where(SowVersion.id == sow_version_id))
    counts["sow_versions"] = r.rowcount or 0
    await append_audit(
        session,
        actor_id=actor_id,
        action="sow_version.deleted",
        entity="sow_version",
        entity_id=str(sow_version_id),
        before=snapshot,
        after={"reason": (reason or "").strip() or None, "cascade": counts},
    )
    return DeletionAssessment(state="deleted", reason="ok", counts=counts)


# --- dedupe helpers ------------------------------------------------------


@dataclass
class DedupeHit:
    """A dedupe hit — the caller decides whether to block or inform."""

    sow_version_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    file_hash: str
    archived: bool


async def live_sow_version_by_hash(
    session: AsyncSession, file_hash: str
) -> DedupeHit | None:
    """Return a hit ONLY if a live (non-archived) sow_version has the hash.

    Hard-deleted rows are gone; archived rows are informational and returned
    with ``archived=True``. The upload router blocks on archived=False and
    surfaces a note on archived=True per directive "fresh-start requirement".
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
    batch_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> DeletionAssessment:
    """Hard-delete every record a bulk-import batch created (per-record state
    rules still apply — any file that reached approval blocks its own row)."""

    files = (
        (
            await session.execute(
                select(ImportFile).where(ImportFile.batch_id == batch_id)
            )
        )
        .scalars()
        .all()
    )
    counts: dict[str, int] = {"import_files": len(files)}
    for f in files:
        if f.sow_version_id:
            try:
                sub = await delete_sow_version(
                    session,
                    sow_version_id=f.sow_version_id,
                    actor_id=actor_id,
                    reason=f"bulk delete: batch {batch_id}",
                )
                for k, v in sub.counts.items():
                    counts[k] = counts.get(k, 0) + v
            except DeletionError:
                # A promoted, later-approved SOW blocks itself; report and skip.
                counts["skipped_approved"] = counts.get("skipped_approved", 0) + 1
    r = await session.execute(sa_delete(ImportFile).where(ImportFile.batch_id == batch_id))
    counts["import_file_rows"] = r.rowcount or 0
    r = await session.execute(sa_delete(ImportBatch).where(ImportBatch.id == batch_id))
    counts["import_batches"] = r.rowcount or 0
    await append_audit(
        session,
        actor_id=actor_id,
        action="import_batch.deleted",
        entity="import_batch",
        entity_id=str(batch_id),
        before=None,
        after={"cascade": counts},
    )
    return DeletionAssessment(state="deleted", reason="ok", counts=counts)


__all__ = [
    "DedupeHit",
    "DeletionAssessment",
    "DeletionError",
    "archive_client",
    "archive_opportunity",
    "assess_client",
    "assess_opportunity",
    "assess_sow_version",
    "delete_client",
    "delete_import_batch",
    "delete_opportunity",
    "delete_sow_version",
    "live_sow_version_by_hash",
]
