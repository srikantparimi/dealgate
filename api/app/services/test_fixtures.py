"""Server-issued fixture provenance; names and request metadata confer no trust.

The existing append-only audit store records issuance atomically with a NEW
client. No API accepts an existing business client to adopt as a fixture.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.audit import append_audit
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User

E2E_USER_GROUP = "officeapp-e2e"
ISSUED = "test.fixture_created"


def is_test_user(user):
    return bool(user and E2E_USER_GROUP in (user.groups or []))


def runtime_scope():
    return os.environ.get("DEALGATE_ENV", "local"), os.environ.get("DEALGATE_TENANT_ID")


async def create_fixture(session, *, actor_id, label, reviewer_ids, hours=4, pipeline_deal=None):
    """Create isolated account/deal, never an approved state. Caller commits.

    ``pipeline_deal`` (S23-PL2 T12) fills the fields HubSpot owns on a real
    deal — stage, amount, close/created/activity dates, region, HubSpot owner —
    so the Pipeline specs exercise populated rows. With ``draft_sow`` it also
    adds a SOW with no version or package (state "Draft"); it never creates an
    approval package, so nothing is routed to a real approver.
    """
    from app.routers.dev_seed import is_dev_seed_enabled

    actor = await session.get(User, actor_id)
    environment, tenant_id = runtime_scope()
    if not is_dev_seed_enabled() or not is_test_user(actor) or "SystemAdmin" not in actor.groups:
        raise HTTPException(403, "Fixture issuance requires an enabled test administrator")
    if not tenant_id:
        raise HTTPException(409, "Configure an explicit fixture tenant before issuing test data")
    if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 24:
        raise HTTPException(422, "Fixture validity must be 1-24 hours")
    participants = {uuid.UUID(str(i)) for i in reviewer_ids} | {actor_id}
    users = list((await session.scalars(select(User).where(User.id.in_(participants)))).all())
    if {u.id for u in users} != participants or not all(is_test_user(u) for u in users):
        raise HTTPException(422, "Every fixture participant must be a known test identity")
    run_id = uuid.uuid4()
    client = Client(id=uuid.uuid4(), name=f"S21 e2e {run_id} {label.strip()}"[:255])
    session.add(client)
    await session.flush()
    deal = Opportunity(
        id=uuid.uuid4(),
        client_id=client.id,
        owner_id=actor_id,
        source="sow_upload",
        name=client.name,
        governance_status="Intake",
    )
    session.add(deal)
    populated = None
    if pipeline_deal is not None:
        populated = await _populate_pipeline_deal(session, deal, pipeline_deal, run_id=run_id)
    expires_at = datetime.now(UTC) + timedelta(hours=hours)
    await append_audit(
        session,
        actor_id=actor_id,
        action=ISSUED,
        entity="client",
        entity_id=str(client.id),
        before=None,
        after={
            "run_id": str(run_id),
            "environment": environment,
            "tenant_id": tenant_id,
            "owner_id": str(actor_id),
            "participant_ids": sorted(str(i) for i in participants),
            "expires_at": expires_at.isoformat(),
            "opportunity_id": str(deal.id),
            **({"pipeline_deal": populated} if populated is not None else {}),
        },
        correlation_id=str(run_id),
    )
    return {
        "run_id": run_id,
        "client_id": client.id,
        "opportunity_id": deal.id,
        "expires_at": expires_at,
    }


_FIXTURE_ZONE = "America/Los_Angeles"


async def _populate_pipeline_deal(session, deal, spec, *, run_id):
    """Give a fixture deal the HubSpot-owned fields of a real one (S23-PL2 T12).

    The stage comes from the mirrored pipeline (its ``stage``-th live stage by
    display order); the region is recorded the way intake records it, so the
    business-unit map applies; the HubSpot owner is the first active mirrored
    owner (``active``), an id no mirror holds (``former``) or none (``none``).
    No HubSpot deal or company id is set: a fixture bound to a CRM identity
    loses its grant (``account_scope``).
    """

    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
    from app.services.hubspot_owners import HubspotOwner
    from app.services.hubspot_properties import HubspotPropertyMapping

    pipeline = await session.scalar(
        select(HubspotPipeline).where(HubspotPipeline.archived.is_(False))
        .order_by(HubspotPipeline.display_order, HubspotPipeline.id).limit(1))
    if pipeline is None:
        raise HTTPException(409, "No HubSpot pipeline is mirrored to place a fixture deal in")
    stages = list((await session.scalars(
        select(HubspotStage).where(HubspotStage.pipeline_id == pipeline.id, HubspotStage.archived.is_(False))
        .order_by(HubspotStage.display_order, HubspotStage.id))).all())
    if not 1 <= spec["stage"] <= len(stages):
        raise HTTPException(422, f"stage must be between 1 and {len(stages)}")
    stage = stages[spec["stage"] - 1]
    probability = Decimal(str(stage.probability)) if stage.probability is not None else None
    deal.hubspot_pipeline_id = pipeline.id
    deal.hubspot_stage_id = stage.id
    deal.sales_stage = stage.id
    deal.stage_label = stage.label
    deal.stage_order = stage.display_order
    deal.is_closed_won = bool(stage.is_closed and probability == Decimal("1"))
    deal.is_closed_lost = bool(stage.is_closed and probability == Decimal("0"))

    now = datetime.now(UTC)
    today = now.astimezone(ZoneInfo(_FIXTURE_ZONE)).date()
    if spec.get("amount") is not None:
        deal.amount = Decimal(str(spec["amount"]))
        deal.currency = "USD"
    if spec.get("close_in_days") is not None:
        deal.close_date = today + timedelta(days=spec["close_in_days"])
    deal.hubspot_created_at = now - timedelta(days=spec.get("created_days_ago") or 0)
    if spec.get("activity_days_ago") is not None:
        deal.hubspot_last_activity_at = now - timedelta(days=spec["activity_days_ago"])

    region = spec.get("region")
    if region:
        deal.business_unit_value = region
        mapping = await session.get(HubspotPropertyMapping, "business_unit")
        if mapping is not None and mapping.object_type == "deal" and mapping.availability_state == "configured":
            deal.business_unit_mapping_version = mapping.mapping_version
            deal.business_unit_observed_at = now

    owner = spec.get("owner", "active")
    if owner == "active":
        active = await session.scalar(
            select(HubspotOwner.id).where(HubspotOwner.archived.is_(False)).order_by(HubspotOwner.id).limit(1))
        if active is None:
            raise HTTPException(409, "No active HubSpot owner is mirrored to own a fixture deal")
        deal.hubspot_owner_id = active
    elif owner == "former":
        deal.hubspot_owner_id = f"e2e-former-{run_id.hex[:12]}"
    else:
        deal.hubspot_owner_id = None

    if spec.get("draft_sow"):
        session.add(Sow(id=uuid.uuid4(), opportunity_id=deal.id))
    await session.flush()
    return {
        "stage": spec["stage"],
        "stage_id": stage.id,
        "amount": str(deal.amount) if deal.amount is not None else None,
        "region": region,
        "owner": owner,
        "draft_sow": bool(spec.get("draft_sow")),
    }


async def reviewer_scope(session, version):
    """None = ordinary business record; empty set = invalid/expired fixture.

    Expired or foreign-environment fixtures NEVER fall back to real reviewers.
    """
    if version is None:
        return frozenset()
    sow = await session.get(Sow, version.sow_id)
    deal = await session.get(Opportunity, sow.opportunity_id) if sow else None
    # Legacy deals may have no client link. They have no fixture grant and
    # remain business records: real users allowed, test identities denied.
    if deal is not None and deal.client_id is None:
        return None
    client = await session.get(Client, deal.client_id) if deal and deal.client_id else None
    if client is None:
        return frozenset()
    scope = await account_scope(session, client.id, opportunity_id=deal.id)
    if scope is not None and (sow.archived_at is not None or version.uploaded_by not in scope):
        return frozenset()
    return scope


async def account_scope(session, client_id, *, opportunity_id=None):
    """Revalidate account fixture provenance for non-SOW consumers such as planning."""
    client = await session.get(Client, client_id)
    if client is None or client.archived_at is not None:
        return frozenset()
    grant = await session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.action == ISSUED,
            AuditEvent.entity == "client",
            AuditEvent.entity_id == str(client.id),
        )
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    if grant is None:
        return None
    data = grant.after or {}
    environment, tenant_id = runtime_scope()
    try:
        expiry = datetime.fromisoformat(data["expires_at"])
        participants = frozenset(uuid.UUID(i) for i in data["participant_ids"])
        deal = await session.get(Opportunity, uuid.UUID(data["opportunity_id"]))
    except (ValueError, TypeError, KeyError):
        return frozenset()
    if (
        not tenant_id
        or (environment, tenant_id) != (data.get("environment"), data.get("tenant_id"))
        or expiry.tzinfo is None
        or expiry <= datetime.now(UTC)
        or grant.actor_id is None
        or str(grant.actor_id) != data.get("owner_id")
        or deal is None
        or deal.client_id != client.id
        or (opportunity_id is not None and deal.id != opportunity_id)
        or deal.owner_id != grant.actor_id
        or client.hubspot_company_id is not None
        or deal.hubspot_deal_id is not None
        or client.archived_at is not None
    ):
        return frozenset()
    issuer = await session.get(User, grant.actor_id)
    if not is_test_user(issuer) or "SystemAdmin" not in issuer.groups:
        return frozenset()
    return participants


def user_allowed(user, scope):
    if user is None:
        return False
    if scope is None:
        return not is_test_user(user)
    return is_test_user(user) and user.id in scope


async def allowed_for_package(session, user_id, package):
    version = await session.get(SowVersion, package.sow_version_id)
    return user_allowed(await session.get(User, user_id), await reviewer_scope(session, version))


async def notification_block_reason(session, *, user_id, related_entity, related_entity_id):
    if related_entity not in {"approval_package", "task"}:
        return None
    from app.models.approval import ApprovalPackage

    user = await session.get(User, user_id)
    if related_entity == "task":
        from app.models.approval_routing import ApprovalAssignment
        from app.models.task import Task

        try:
            task_id = uuid.UUID(str(related_entity_id))
        except (ValueError, TypeError):
            return "Invalid task reference" if is_test_user(user) else None
        task = await session.get(Task, task_id)
        if task is None:
            return "Task unavailable" if is_test_user(user) else None
        if task.category not in {"approval.awaiting", "approval.routing"}:
            return None
        if task.status in {"done", "cancelled"}:
            return "Approval task is no longer active"
        package_ids = set(
            (
                await session.scalars(
                    select(ApprovalAssignment.package_id).where(
                        ApprovalAssignment.task_id == task_id,
                    )
                )
            ).all()
        )
        if len(package_ids) > 1:
            return "Ambiguous approval task reference"
        if package_ids:
            related_entity_id = str(next(iter(package_ids)))
        else:
            # Pre-assignment tasks carry their authoritative parent in the
            # server-written audit record, not in editable subject/body text.
            event = await session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.entity == "task",
                    AuditEvent.entity_id == str(task_id),
                    AuditEvent.action == "task.created",
                )
                .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
                .limit(1)
            )
            parent = event.after if event else None
            if not parent or parent.get("related_entity") != "approval_package":
                return "Unproven approval task scope" if is_test_user(user) else None
            related_entity_id = parent.get("related_entity_id")
    try:
        package_id = uuid.UUID(str(related_entity_id))
    except (ValueError, TypeError):
        return "Invalid approval reference" if is_test_user(user) else None
    package = await session.get(ApprovalPackage, package_id)
    if package is None:
        return "Approval package unavailable" if is_test_user(user) else None
    if not await allowed_for_package(session, user_id, package):
        return "Test identity or fixture is outside the trusted approval scope"
    return None
