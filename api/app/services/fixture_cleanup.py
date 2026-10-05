"""Fail-closed cleanup manifests from server-issued fixture grants."""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.models.user import User
from app.services.deletion import assess_client
from app.services.test_fixtures import ISSUED, is_test_user, runtime_scope


def _utc(value):
    # SQLite stores UTC timestamps without tzinfo; PostgreSQL preserves it.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def cleanup_manifest(session, *, now=None, min_age=timedelta(hours=24),
                           run_id=None, owner_id=None, lock=False):
    if min_age < timedelta(0) or (min_age == timedelta(0) and not (run_id and owner_id)):
        raise ValueError("Zero-age cleanup requires an exact run and owner; negative age is invalid")
    if bool(run_id) != bool(owner_id):
        raise ValueError("Bounded cleanup requires both run and owner")
    environment, tenant = runtime_scope()
    if environment not in {"dev", "staging"} or not tenant:
        return []
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Cleanup time requires an explicit timezone")
    grants = (await session.scalars(select(AuditEvent).where(
        AuditEvent.action == ISSUED, AuditEvent.entity == "client",
    ).order_by(AuditEvent.entity_id, AuditEvent.id))).all()
    grant_counts = Counter(grant.entity_id for grant in grants)
    targets = []
    for grant in grants:
        if grant_counts[grant.entity_id] != 1 or not isinstance(grant.after, dict):
            continue
        data = grant.after
        if not isinstance(data.get("participant_ids"), list):
            continue
        try:
            client_id = uuid.UUID(grant.entity_id)
            granted_run = uuid.UUID(data["run_id"])
            granted_owner = uuid.UUID(data["owner_id"])
            deal_id = uuid.UUID(data["opportunity_id"])
            participants = {uuid.UUID(value) for value in data["participant_ids"]}
            expiry = datetime.fromisoformat(data["expires_at"])
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        if (
            (data.get("environment"), data.get("tenant_id")) != (environment, tenant)
            or grant.actor_id != granted_owner or grant.correlation_id != str(granted_run)
            or granted_owner not in participants or expiry.tzinfo is None or expiry > now
            or _utc(grant.ts) > now - min_age or expiry <= _utc(grant.ts)
            or (run_id and str(run_id) != str(granted_run))
            or (owner_id and str(owner_id) != str(granted_owner))
        ):
            continue
        issuer = await session.get(User, granted_owner, populate_existing=True)
        if not is_test_user(issuer) or "SystemAdmin" not in issuer.groups:
            continue
        users = (await session.scalars(select(User).where(User.id.in_(participants))
            .execution_options(populate_existing=True))).all()
        if {user.id for user in users} != participants or not all(is_test_user(user) for user in users):
            continue
        client_query = select(Client).where(Client.id == client_id).execution_options(populate_existing=True)
        if lock:
            client_query = client_query.with_for_update()
        client = await session.scalar(client_query)
        if (client is None or client.hubspot_company_id is not None or client.created_at is None
                or _utc(client.created_at) > now - min_age):
            continue
        deals_query = select(Opportunity).where(Opportunity.client_id == client_id).execution_options(populate_existing=True)
        if lock:
            deals_query = deals_query.with_for_update()
        deals = (await session.scalars(deals_query)).all()
        if (len(deals) != 1 or deals[0].id != deal_id or deals[0].owner_id != granted_owner
                or deals[0].hubspot_deal_id is not None or deals[0].source == "hubspot"):
            continue
        uploaders = (await session.scalars(select(SowVersion.uploaded_by).join(Sow,
            Sow.id == SowVersion.sow_id).where(Sow.opportunity_id == deal_id))).all()
        uploaders += (await session.scalars(select(Agreement.uploaded_by).where(
            Agreement.client_id == client_id))).all()
        uploaders += (await session.scalars(select(AgreementFileVersion.uploaded_by)
            .join(Agreement, Agreement.id == AgreementFileVersion.agreement_id)
            .where(Agreement.client_id == client_id))).all()
        uploaders += (await session.scalars(select(SowUploadJob.uploader_id).where(
            SowUploadJob.opportunity_id == deal_id))).all()
        if any(uploader not in participants for uploader in uploaders):
            continue
        assessment = await assess_client(session, client.id)
        targets.append({"client_id": str(client.id), "client_name": client.name,
            "run_id": str(granted_run), "owner_id": str(granted_owner),
            "environment": environment, "tenant_id": tenant, "counts": assessment.counts})
    return targets
