"""Frozen project authorization survives parent detachment, not scope changes."""

import copy
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.audit import append_audit
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Client
from app.services.commercial_models import save_commercial_model
from app.services.project_lifecycle import create_or_link
from tests.test_approval_routing import fixture
from tests.test_s21_commercial_persistence import wire


@pytest_asyncio.fixture
async def canonical(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "source-tenant")
    monkeypatch.setenv("DEALGATE_ENV", "local")
    owner, deal, version, old, _ = await fixture(session)
    gm = await save_commercial_model(session, opportunity_id=deal.id, actor_id=owner.id,
        sow_version_id=version.id, expected_gm_model_id=old.id, inputs=wire(version),
        change_reason="Confirmed source for retained delivery")
    package = ApprovalPackage(opportunity_id=deal.id, sow_version_id=version.id,
        gm_model_id=gm.id, package_hash="a" * 64, status="released", submitted_by=owner.id)
    session.add(package)
    await session.flush()
    return owner, deal, version, gm, package


async def capture(session, data):
    from app.services.project_source import capture_project_scope
    _, deal, version, gm, _ = data
    return await capture_project_scope(session, opportunity=deal, sow_version=version, gm_model=gm)


async def issued(session, data, **overrides):
    owner, deal, _, _, _ = data
    owner.groups = ["SystemAdmin", "officeapp-e2e"]
    deal.hubspot_deal_id = None
    deal.source = "sow_upload"
    (await session.get(Client, deal.client_id)).hubspot_company_id = None
    run = str(uuid.uuid4())
    body = dict(environment="local", tenant_id="source-tenant", owner_id=str(owner.id),
        participant_ids=[str(owner.id)], opportunity_id=str(deal.id), run_id=run,
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    body.update(overrides)
    await append_audit(session, actor_id=owner.id, action="test.fixture_created",
        entity="client", entity_id=str(deal.client_id), before=None, after=body,
        correlation_id=run)
    await session.flush()
    return await session.scalar(select(AuditEvent).where(AuditEvent.action == "test.fixture_created"))


async def project(session, data):
    owner, _, _, _, package = data
    return (await create_or_link(session, actor_id=owner.id, package=package))[0]


def detach(p):
    p.retained_source = {key: str(getattr(p, key)) for key in
        ("opportunity_id", "sow_version_id", "gm_model_id", "package_id", "client_id")}
    p.source_deleted_at = datetime.now(UTC)
    p.opportunity_id = p.sow_version_id = p.gm_model_id = p.package_id = p.client_id = None


async def test_release_captures_exact_scope_and_replay_never_rewrites(session, canonical, monkeypatch):
    from app.services.project_source import project_scope_allowed
    owner, deal, version, gm, _ = canonical
    p = await project(session, canonical)
    scope = p.baseline_snapshot_json["source_scope"]
    assert scope["tenant_id"] == "source-tenant" and scope["environment"] == "local"
    assert scope["account_id"] == str(deal.client_id) and scope["owner_id"] == str(owner.id)
    assert scope["gm_model_id"] == str(gm.id) and scope["sow_version_id"] == str(version.id)
    assert scope["fixture_grant_id"] is None and len(scope["source_hash"]) == 64
    frozen = copy.deepcopy(p.baseline_snapshot_json)
    detach(p)
    assert await project_scope_allowed(session, actor=owner, project=p)
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert not await project_scope_allowed(session, actor=owner, project=p)
    assert p.baseline_snapshot_json == frozen


@pytest.mark.parametrize("mutation", ["tenant", "environment", "gm_deal", "gm_sow", "component", "schedule"])
async def test_capture_rejects_conflicting_canonical_scope(session, canonical, mutation):
    _, _, _, gm, _ = canonical
    if mutation in ("tenant", "environment"):
        gm.commercial_snapshot = {**gm.commercial_snapshot,
            "tenant_id" if mutation == "tenant" else "environment": "foreign"}
    elif mutation == "gm_deal":
        gm.opportunity_id = uuid.uuid4()
    elif mutation == "gm_sow":
        gm.sow_version_id = uuid.uuid4()
    elif mutation == "component":
        gm.commercial_inputs = {**gm.commercial_inputs, "source_id": str(uuid.uuid4())}
    else:
        gm.commercial_snapshot = {**gm.commercial_snapshot, "schedule": {}}
    with pytest.raises(ValueError):
        await capture(session, canonical)


async def test_legacy_scope_stays_unresolved_and_release_conflict_is_409(session, canonical):
    from app.services.project_source import project_scope_allowed
    _, _, _, gm, _ = canonical
    original = gm.commercial_snapshot
    gm.commercial_snapshot = {**original, "tenant_id": None}
    assert await capture(session, canonical) is None
    p = await project(session, canonical)
    assert p.baseline_snapshot_json["source_scope"] is None
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)
    gm.commercial_snapshot = {**original, "tenant_id": "foreign"}
    # Idempotent linking preserves the unresolved original baseline.
    same = await project(session, canonical)
    assert same is p and same.baseline_snapshot_json["source_scope"] is None


@pytest.mark.parametrize("mutation", ["hash", "lineage", "missing", "test_flag", "not_dict"])
async def test_retained_baseline_tampering_is_denied(session, canonical, mutation):
    from app.services.project_source import project_scope_allowed
    p = await project(session, canonical)
    detach(p)
    if mutation == "hash":
        p.baseline_snapshot_json["commercial_inputs"]["source_version"] = str(uuid.uuid4())
    elif mutation == "lineage":
        p.retained_source["gm_model_id"] = str(uuid.uuid4())
    elif mutation == "missing":
        p.baseline_snapshot_json.pop("source_scope")
    elif mutation == "not_dict":
        p.baseline_snapshot_json["source_scope"] = []
    else:
        p.baseline_snapshot_json["source_scope"] = {"test_fixture": True}
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)


async def test_authoritative_fixture_grant_survives_detachment_but_never_crosses_identity(session, canonical):
    from app.models.user import User
    from app.services.project_source import project_scope_allowed
    grant = await issued(session, canonical)
    p = await project(session, canonical)
    assert p.baseline_snapshot_json["source_scope"]["fixture_grant_id"] == str(grant.id)
    detach(p)
    assert await project_scope_allowed(session, actor=canonical[0], project=p)
    other = User(id=uuid.uuid4(), email="outsider@example.test", groups=["officeapp-e2e"])
    assert not await project_scope_allowed(session, actor=other, project=p)
    ordinary = User(id=uuid.uuid4(), email="ordinary@example.test", groups=["SystemAdmin"])
    assert not await project_scope_allowed(session, actor=ordinary, project=p)
    canonical[0].groups = ["officeapp-e2e"]
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)


@pytest.mark.parametrize("changes", [
    {"expires_at": "2020-01-01T00:00:00+00:00"}, {"expires_at": "2030-01-01T00:00:00"},
    {"participant_ids": "bad"}, {"tenant_id": "foreign"}, {"owner_id": str(uuid.uuid4())},
])
async def test_invalid_fixture_never_falls_back_to_ordinary(session, canonical, changes):
    await issued(session, canonical, **changes)
    with pytest.raises(ValueError):
        await capture(session, canonical)


async def test_fixture_grant_cannot_be_erased_or_forged_after_release(session, canonical):
    from app.services.project_source import project_scope_allowed
    await issued(session, canonical)
    p = await project(session, canonical)
    detach(p)
    scope = p.baseline_snapshot_json["source_scope"]
    scope["fixture_grant_id"] = None
    canonical[0].groups = ["SystemAdmin"]
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)
    scope["fixture_grant_id"] = str(uuid.uuid4())
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)


async def test_release_foreign_scope_returns_conflict_before_project_creation(session, canonical):
    canonical[3].commercial_snapshot = {**canonical[3].commercial_snapshot, "tenant_id": "foreign"}
    with pytest.raises(HTTPException) as error:
        await project(session, canonical)
    assert error.value.status_code == 409


async def test_retained_fixture_expiry_rechecked_without_rewriting_grant(session, canonical, monkeypatch):
    from app.services import project_source
    await issued(session, canonical)
    p = await project(session, canonical)
    detach(p)
    frozen = copy.deepcopy(p.baseline_snapshot_json)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=2)

    monkeypatch.setattr(project_source, "datetime", Later)
    assert not await project_source.project_scope_allowed(session, actor=canonical[0], project=p)
    assert p.baseline_snapshot_json == frozen


async def test_real_project_never_visible_to_test_identity_or_foreign_environment(session, canonical, monkeypatch):
    from app.services.project_source import project_scope_allowed
    p = await project(session, canonical)
    assert await project_scope_allowed(session, actor=canonical[0], project=p)
    canonical[0].groups = ["officeapp-e2e", "SystemAdmin"]
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)
    canonical[0].groups = ["SystemAdmin"]
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)


async def test_test_owned_source_cannot_claim_real_scope_without_grant(session, canonical):
    canonical[0].groups = ["SystemAdmin", "officeapp-e2e"]
    with pytest.raises(ValueError):
        await capture(session, canonical)


@pytest.mark.parametrize("change", ["company", "deal", "owner"])
async def test_fixture_cannot_borrow_contaminated_live_parent(session, canonical, change):
    from app.services.project_source import project_scope_allowed
    await issued(session, canonical)
    p = await project(session, canonical)
    if change == "company":
        (await session.get(Client, canonical[1].client_id)).hubspot_company_id = "real-company"
    elif change == "deal":
        canonical[1].hubspot_deal_id = "real-deal"
    else:
        canonical[1].owner_id = None
    assert not await project_scope_allowed(session, actor=canonical[0], project=p)
