"""Immutable release provenance, independent of role or portfolio projection."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.user import User
from app.services.commercial_models import COMPONENT, SCHEDULE
from app.services.test_fixtures import ISSUED, is_test_user, runtime_scope


def _identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Invalid project source identity")
    return value


def _hash(inputs, snapshot):
    encoded = json.dumps({"commercial_inputs": inputs, "commercial_snapshot": snapshot},
        sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _canonical(inputs, snapshot, sow_id, version_id):
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != "commercial-model-v1":
        raise ValueError("Invalid canonical commercial snapshot")
    component = COMPONENT.validate_python(inputs)
    schedule = SCHEDULE.validate_python(snapshot["schedule"])
    if schedule.component != component:
        raise ValueError("Commercial schedule differs from its source")

    def bound(source):
        if (source.source_id, source.source_version) != (sow_id, version_id):
            raise ValueError("Commercial source lineage conflicts with release")
        for child in getattr(source.pricing, "components", ()):
            bound(child)

    bound(component)


async def _grants(session, account_id):
    return list((await session.scalars(select(AuditEvent).where(
        AuditEvent.action == ISSUED, AuditEvent.entity == "client",
        AuditEvent.entity_id == account_id))).all())


async def _participants(session, grant, scope):
    """Validate issuance without requiring source parents to still exist."""
    data = grant.after
    if not isinstance(data, dict) or not isinstance(data.get("participant_ids"), list):
        raise ValueError("Malformed fixture issuance")
    participants = {_identity(value) for value in data["participant_ids"]}
    expiry = datetime.fromisoformat(data["expires_at"])
    if (grant.action != ISSUED or grant.entity != "client"
        or grant.entity_id != scope["account_id"]
        or str(grant.actor_id) != scope["owner_id"]
        or data.get("owner_id") != scope["owner_id"]
        or data.get("opportunity_id") != scope["opportunity_id"]
        or data.get("environment") != scope["environment"]
        or data.get("tenant_id") != scope["tenant_id"]
        or _identity(data.get("run_id")) != grant.correlation_id
        or scope["owner_id"] not in participants
        or expiry.tzinfo is None or expiry <= datetime.now(UTC)):
        raise ValueError("Fixture issuance is outside the retained source scope")
    issuer = await session.get(User, grant.actor_id)
    if not is_test_user(issuer) or "SystemAdmin" not in issuer.groups:
        raise ValueError("Fixture issuer is no longer an authorized test administrator")
    return participants


async def capture_project_scope(session, *, opportunity, sow_version, gm_model) -> dict | None:
    snapshot, inputs = gm_model.commercial_snapshot, gm_model.commercial_inputs
    if snapshot is None and inputs is None:
        return None
    if not isinstance(snapshot, dict):
        raise ValueError("Malformed canonical project source")
    if (gm_model.opportunity_id != opportunity.id or gm_model.sow_id != sow_version.sow_id
        or gm_model.sow_version_id != sow_version.id):
        raise ValueError("GM and SOW release lineage conflict")
    try:
        _canonical(inputs, snapshot, str(sow_version.sow_id), str(sow_version.id))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid canonical project source") from exc
    # Older snapshots without scope stay unresolved; current runtime cannot adopt them.
    if snapshot.get("tenant_id") is None or snapshot.get("environment") is None:
        return None
    environment, tenant = runtime_scope()
    if not tenant or (snapshot["environment"], snapshot["tenant_id"]) != (environment, tenant):
        raise ValueError("Canonical project source belongs to another runtime")
    sow = await session.get(Sow, sow_version.sow_id)
    client = await session.get(Client, opportunity.client_id) if opportunity.client_id else None
    if (sow is None or sow.opportunity_id != opportunity.id or client is None
        or client.archived_at is not None or opportunity.owner_id is None):
        raise ValueError("Project source account, owner or SOW lineage is unavailable")
    scope = dict(schema_version="project-source-v1", tenant_id=snapshot["tenant_id"],
        environment=snapshot["environment"], opportunity_id=str(opportunity.id),
        sow_id=str(sow.id), sow_version_id=str(sow_version.id), gm_model_id=str(gm_model.id),
        account_id=str(client.id), owner_id=str(opportunity.owner_id),
        source_hash=_hash(inputs, snapshot), fixture_grant_id=None)
    grants = await _grants(session, scope["account_id"])
    if grants:
        if (len(grants) != 1 or client.hubspot_company_id is not None
            or opportunity.hubspot_deal_id is not None or opportunity.source == "hubspot"):
            raise ValueError("Conflicting fixture source provenance")
        try:
            participants = await _participants(session, grants[0], scope)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid fixture source provenance") from exc
        if str(sow_version.uploaded_by) not in participants:
            raise ValueError("SOW uploader is outside the fixture issuance")
        scope["fixture_grant_id"] = str(grants[0].id)
    elif is_test_user(await session.get(User, opportunity.owner_id)):
        raise ValueError("Test-owned source has no authoritative fixture issuance")
    return scope


async def project_scope_allowed(session, *, actor, project) -> bool:
    if actor is None:
        return False
    try:
        baseline = project.baseline_snapshot_json
        if not isinstance(baseline, dict):
            return False
        scope = baseline.get("source_scope")
        if not isinstance(scope, dict) or scope.get("schema_version") != "project-source-v1":
            return False
        environment, tenant = runtime_scope()
        if not tenant or (scope["environment"], scope["tenant_id"]) != (environment, tenant):
            return False
        for field in ("opportunity_id", "sow_id", "sow_version_id", "gm_model_id", "account_id", "owner_id"):
            _identity(scope[field])
        snapshot, inputs = baseline["commercial_snapshot"], baseline["commercial_inputs"]
        if (snapshot["environment"], snapshot["tenant_id"]) != (environment, tenant):
            return False
        if _hash(inputs, snapshot) != scope["source_hash"]:
            return False
        _canonical(inputs, snapshot, scope["sow_id"], scope["sow_version_id"])
        retained = project.retained_source or {}
        for field in ("opportunity_id", "sow_version_id", "gm_model_id", "client_id"):
            source = scope["account_id" if field == "client_id" else field]
            if field != "client_id" and baseline[field] != source:
                return False
            current = getattr(project, field)
            if current is not None and str(current) != source:
                return False
            if current is None and (project.source_deleted_at is None or retained.get(field) != source):
                return False
            if field in retained and retained[field] != source:
                return False
        if (scope.get("fixture_grant_id") is not None and "owner_id" in retained
            and retained["owner_id"] != scope["owner_id"]):
            return False
        if project.package_id is not None and baseline["package_id"] != str(project.package_id):
            return False
        if project.package_id is None and (project.source_deleted_at is None
            or retained.get("package_id") != baseline["package_id"]):
            return False
        if "package_id" in retained and retained["package_id"] != baseline["package_id"]:
            return False
        grants = await _grants(session, scope["account_id"])
        grant_id = scope["fixture_grant_id"]
        if "test_fixture" in retained and retained["test_fixture"] is not (grant_id is not None):
            return False
        if grant_id is None:
            return not grants and not is_test_user(actor)
        _identity(grant_id)
        if len(grants) != 1 or str(grants[0].id) != grant_id:
            return False
        participants = await _participants(session, grants[0], scope)
        # Detached parents need not exist, but surviving parents cannot become real CRM.
        client = await session.get(Client, uuid.UUID(scope["account_id"]))
        deal = await session.get(Opportunity, uuid.UUID(scope["opportunity_id"]))
        if client is not None and (client.hubspot_company_id is not None or client.archived_at is not None):
            return False
        if deal is not None and (deal.hubspot_deal_id is not None or deal.source == "hubspot"
            or str(deal.client_id) != scope["account_id"]
            or str(deal.owner_id) != scope["owner_id"]):
            return False
        return is_test_user(actor) and str(actor.id) in participants
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
