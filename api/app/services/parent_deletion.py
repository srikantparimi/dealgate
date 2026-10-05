"""Parent deletion composes retained SOW deletion and durable exact-key jobs."""

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select, update

from app.audit import append_audit
from app.models.actual import FinancialActual
from app.models.approval import ApprovalPackage
from app.models.client import Agreement, AgreementFileVersion, Client, LegalEntity
from app.models.client_alias import ClientAlias
from app.models.client_contact import ClientContact
from app.models.client_rate_card import ClientRateCard, ClientRateCardRow
from app.models.deal_comment import DealComment
from app.models.deletion import DeletionFence, DeletionJob
from app.models.forecast import ForecastConversion, ForecastJob, ForecastPlan, ForecastPlanVersion, ForecastSchedule
from app.models.gm_model import GmModel
from app.models.hubspot_writeback import HubspotWritebackJob
from app.models.import_batch import ImportFile
from app.models.next_action import NextAction, NextActionEvent
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.renewal import Renewal
from app.models.sow import Sow
from app.models.sow_upload_job import SowUploadJob
from app.services.deletion import DeletionError, request_sow_deletion
from app.services.deletion_fences import lock_source
from app.services.deletion_storage import agreement_bucket, key_is_referenced, sow_bucket
from app.services.test_fixtures import account_scope


def _scope():
    environment = os.environ.get("DEALGATE_ENV", "local")
    tenant = os.environ.get("DEALGATE_TENANT_ID")
    if not tenant and environment not in {"local", "test"}:
        raise DeletionError("Deletion requires an explicit tenant")
    return tenant or "local", environment


async def _previous(session, kind, identity):
    tenant, environment = _scope()
    await lock_source(session, kind, identity)
    return await session.scalar(select(DeletionJob).where(
        DeletionJob.tenant_id == tenant, DeletionJob.environment == environment,
        DeletionJob.subject_type == kind, DeletionJob.subject_id == identity))


async def _new_job(session, kind, identity, actor_id, account_id, title):
    tenant, environment = _scope()
    fixture = await account_scope(session, account_id) if account_id else None
    job = DeletionJob(id=uuid.uuid4(), tenant_id=tenant, environment=environment,
        subject_type=kind, subject_id=identity, actor_id=actor_id, account_id=account_id,
        objects=[], summary={"sow_title": title, "test_fixture": fixture is not None}, status="pending")
    session.add(job)
    await session.flush()
    session.add(DeletionFence(tenant_id=tenant, environment=environment,
        subject_type=kind, subject_id=identity, job_id=job.id))
    return job


async def _finish(session, job, children, counts):
    job.objects = [item for item in job.objects if item["key"] and
        not await key_is_referenced(session, item["bucket"], item["key"])]
    job.summary = {**job.summary, "source_deleted": True, "counts": counts,
        "child_job_ids": [str(child.id) for child in children]}
    if not job.objects and all(child.status == "done" for child in children):
        job.status, job.completed_at = "done", datetime.now(UTC)
    await append_audit(session, actor_id=job.actor_id, action=f"{job.subject_type}.deleted",
        entity=job.subject_type, entity_id=str(job.subject_id), before={
            "name": job.summary["sow_title"], "counts": counts}, after={"job_id": str(job.id)})
    await session.flush()
    return job


def _add_counts(counts, child):
    for key, value in child.summary.get("counts", {}).items():
        counts[key] = counts.get(key, 0) + value


async def request_agreement_deletion(session, *, actor_id, agreement):
    """Caller holds Client then Agreement locks and has checked current authority."""
    job = await _new_job(session, "agreement", agreement.id, actor_id,
        agreement.client_id, agreement.filename)
    versions = (await session.scalars(select(AgreementFileVersion)
        .where(AgreementFileVersion.agreement_id == agreement.id))).all()
    keys = {agreement.file_key, *(version.file_key for version in versions)}
    job.objects = [{"bucket": agreement_bucket(), "key": key} for key in sorted(keys)]
    await session.execute(delete(AgreementFileVersion).where(AgreementFileVersion.agreement_id == agreement.id))
    await session.delete(agreement)
    await session.flush()
    return await _finish(session, job, [], {"agreements": 1, "agreement_versions": len(versions)})


async def request_opportunity_deletion(session, *, actor_id, opportunity_id):
    previous = await _previous(session, "opportunity", opportunity_id)
    if previous:
        return previous
    deal = await session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id).with_for_update())
    if deal is None:
        raise DeletionError("opportunity not found", status_code=404)
    client = await session.get(Client, deal.client_id) if deal.client_id else None
    if deal.hubspot_deal_id is not None or deal.source == "hubspot" or (client and client.hubspot_company_id is not None):
        raise DeletionError("Cannot delete a mirrored opportunity or client")
    tenant, environment = _scope()
    if await session.scalar(select(ForecastPlan.id).where(ForecastPlan.opportunity_id == deal.id,
        or_(ForecastPlan.tenant_id != tenant, ForecastPlan.environment != environment)).limit(1)):
        raise DeletionError("Opportunity has records outside the deletion runtime scope", status_code=404)
    job = await _new_job(session, "opportunity", deal.id, actor_id, deal.client_id, deal.name or "Untitled deal")
    sow_ids = (await session.scalars(select(Sow.id).where(Sow.opportunity_id == deal.id))).all()
    children, counts = [], {"sows": len(sow_ids)}
    for sow_id in sow_ids:
        child = await request_sow_deletion(session, actor_id=actor_id, sow_id=sow_id)
        children.append(child)
        _add_counts(counts, child)
    if await session.scalar(select(ApprovalPackage.id).where(ApprovalPackage.opportunity_id == deal.id).limit(1)):
        raise DeletionError("Deal has a package outside its owned SOW graph")
    projects = (await session.scalars(select(Project).where(Project.opportunity_id == deal.id).with_for_update())).all()
    for project in projects:
        if not project.source_deleted_at:
            raise DeletionError("Project source ownership must be resolved before deleting its deal")
        project.opportunity_id = None
    action_ids = (await session.scalars(select(NextAction.id).where(NextAction.opportunity_id == deal.id))).all()
    renewal_ids = (await session.scalars(select(Renewal.id).where(Renewal.opportunity_id == deal.id))).all()
    uploads = (await session.scalars(select(SowUploadJob).where(SowUploadJob.opportunity_id == deal.id).with_for_update())).all()
    job.objects = [{"bucket": sow_bucket(), "key": row.s3_key} for row in uploads if row.s3_key]
    for kind, identities in (("next_action", action_ids), ("renewal", renewal_ids), ("sow_upload_job", [row.id for row in uploads])):
        for identity in sorted(identities):
            await lock_source(session, kind, identity)
            session.add(DeletionFence(tenant_id=job.tenant_id, environment=job.environment,
                subject_type=kind, subject_id=identity, job_id=job.id))
        await session.execute(delete(Notification).where(Notification.related_entity == kind,
            Notification.related_entity_id.in_([str(value) for value in identities])))
    await session.execute(delete(Notification).where(Notification.related_entity == "opportunity",
        Notification.related_entity_id == str(deal.id)))
    await session.execute(delete(NextActionEvent).where(NextActionEvent.next_action_id.in_(action_ids)))
    await session.execute(delete(NextAction).where(NextAction.id.in_(action_ids)))
    await session.execute(delete(Renewal).where(Renewal.id.in_(renewal_ids)))
    await session.execute(delete(DealComment).where(DealComment.opportunity_id == deal.id))
    await session.execute(delete(HubspotWritebackJob).where(HubspotWritebackJob.opportunity_id == deal.id))
    await session.execute(delete(SowUploadJob).where(SowUploadJob.opportunity_id == deal.id))
    await session.execute(update(ImportFile).where(ImportFile.opportunity_id == deal.id).values(opportunity_id=None))
    await session.execute(update(GmModel).where(GmModel.opportunity_id == deal.id).values(opportunity_id=None))
    await session.execute(update(ForecastPlan).where(ForecastPlan.opportunity_id == deal.id).values(opportunity_id=None))
    await session.flush()
    await session.execute(delete(Opportunity).where(Opportunity.id == deal.id))
    counts.update({"actions": len(action_ids), "renewals": len(renewal_ids), "unbound_uploads": len(uploads)})
    return await _finish(session, job, children, counts)


async def request_client_deletion(session, *, actor_id, client_id):
    previous = await _previous(session, "client", client_id)
    if previous:
        return previous
    client = await session.scalar(select(Client).where(Client.id == client_id).with_for_update())
    if client is None:
        raise DeletionError("client not found", status_code=404)
    if client.hubspot_company_id is not None:
        raise DeletionError("Cannot delete a mirrored client")
    deals = (await session.scalars(select(Opportunity).where(Opportunity.client_id == client_id).with_for_update())).all()
    if any(deal.hubspot_deal_id is not None or deal.source == "hubspot" for deal in deals):
        raise DeletionError("Cannot delete a client containing a mirrored opportunity")
    tenant, environment = _scope()
    for model in (FinancialActual, ForecastPlan):
        if await session.scalar(select(model.id).where(model.account_id == client_id,
            or_(model.tenant_id != tenant, model.environment != environment)).limit(1)):
            raise DeletionError("Client has records outside the deletion runtime scope", status_code=404)
    job = await _new_job(session, "client", client.id, actor_id, client.id, client.name)
    children, counts = [], {"opportunities": len(deals)}
    for deal in deals:
        child = await request_opportunity_deletion(session, actor_id=actor_id, opportunity_id=deal.id)
        children.append(child)
        _add_counts(counts, child)
    projects = (await session.scalars(select(Project).where(Project.client_id == client_id).with_for_update())).all()
    for project in projects:
        if not project.source_deleted_at:
            raise DeletionError("Project source ownership must be resolved before deleting its client")
        project.client_id = None
    await session.execute(update(FinancialActual).where(FinancialActual.account_id == client_id).values(account_id=None))
    plans = (await session.scalars(select(ForecastPlan.id).where(ForecastPlan.account_id == client_id))).all()
    versions = select(ForecastPlanVersion.id).where(ForecastPlanVersion.plan_id.in_(plans))
    await session.execute(delete(ForecastJob).where(ForecastJob.plan_version_id.in_(versions)))
    await session.execute(delete(ForecastSchedule).where(ForecastSchedule.plan_version_id.in_(versions)))
    await session.execute(delete(ForecastConversion).where(ForecastConversion.plan_id.in_(plans)))
    await session.execute(delete(ForecastPlanVersion).where(ForecastPlanVersion.plan_id.in_(plans)))
    await session.execute(delete(ForecastPlan).where(ForecastPlan.id.in_(plans)))
    agreements = (await session.scalars(select(Agreement).where(Agreement.client_id == client_id))).all()
    agreement_ids = [agreement.id for agreement in agreements]
    agreement_versions = (await session.scalars(select(AgreementFileVersion)
        .where(AgreementFileVersion.agreement_id.in_(agreement_ids)))).all()
    keys = {row.file_key for row in [*agreements, *agreement_versions]}
    job.objects = [{"bucket": agreement_bucket(), "key": key} for key in sorted(keys)]
    await session.execute(delete(AgreementFileVersion).where(AgreementFileVersion.agreement_id.in_(agreement_ids)))
    await session.execute(delete(Agreement).where(Agreement.client_id == client_id))
    await session.execute(delete(ClientContact).where(ClientContact.client_id == client_id))
    await session.execute(delete(ClientAlias).where(ClientAlias.client_id == client_id))
    cards = select(ClientRateCard.id).where(ClientRateCard.client_id == client_id)
    await session.execute(delete(ClientRateCardRow).where(ClientRateCardRow.client_rate_card_id.in_(cards)))
    await session.execute(delete(ClientRateCard).where(ClientRateCard.client_id == client_id))
    await session.execute(delete(LegalEntity).where(LegalEntity.client_id == client_id))
    await session.execute(update(ImportFile).where(ImportFile.matched_client_id == client_id).values(matched_client_id=None))
    await session.execute(update(Opportunity).where(Opportunity.primary_client_id == client_id).values(primary_client_id=None))
    await session.execute(delete(Notification).where(Notification.related_entity == "client",
        Notification.related_entity_id == str(client_id)))
    await session.flush()
    await session.execute(delete(Client).where(Client.id == client_id))
    counts.update({"agreements": len(agreements), "agreement_versions": len(agreement_versions), "forecast_plans": len(plans)})
    return await _finish(session, job, children, counts)
