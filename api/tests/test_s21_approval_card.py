"""T40: current in-review SOW packages, never assignments or Deal counts."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth import current_user
from app.db import get_session
from app.models.approval import ApprovalPackage
from app.models.approval_routing import ApprovalAssignment
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.routers.approvals import router
from app.services.test_fixtures import create_fixture


@pytest.fixture
async def population(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "approval-card")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    users = [
        User(email=f"{uuid.uuid4()}@example.test", name=name, groups=groups)
        for name, groups in [
            ("Administrator", ["SystemAdmin"]), ("Owner", ["Sales"]),
            ("Reviewer", ["Sales"]), ("Restricted", ["Sales"]),
            ("Fixture issuer", ["SystemAdmin", "officeapp-e2e"]),
            ("Fixture participant", ["Sales", "officeapp-e2e"]),
            ("Other test", ["SystemAdmin", "officeapp-e2e"]),
        ]
    ]
    session.add_all(users)
    account = Client(name="Ordinary local business")
    session.add(account)
    await session.flush()
    deal = Opportunity(client_id=account.id, owner_id=users[1].id,
                       source="sow_upload", name="Two genuine SOWs", governance_status="Intake")
    session.add(deal)
    await session.flush()
    return users, account, deal


async def package(session, deal, user, status="pending_delivery_hr", *, sow=None, age=0):
    if sow is None:
        sow = Sow(opportunity_id=deal.id)
        session.add(sow)
        await session.flush()
    version = SowVersion(sow_id=sow.id, uploaded_by=user.id,
                         file_s3_key=f"isolated/{uuid.uuid4()}.pdf", file_hash="a" * 64)
    session.add(version)
    await session.flush()
    gm = GmModel(opportunity_id=deal.id, sow_id=sow.id, sow_version_id=version.id,
                 engagement_type="fixed_assignment")
    session.add(gm)
    await session.flush()
    row = ApprovalPackage(opportunity_id=deal.id, sow_version_id=version.id,
                          gm_model_id=gm.id, package_hash="b" * 64, status=status,
                          submitted_by=user.id,
                          submitted_at=datetime(2026, 10, 1, tzinfo=UTC) + timedelta(seconds=age))
    session.add(row)
    await session.flush()
    return row, sow, version


async def listing(session, user, *, expected_status=200, **params):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/approvals/packages", params={"status": "in_review", **params})
    assert response.status_code == expected_status, response.text
    return response.json()


@pytest.mark.asyncio
async def test_exact_current_sows_not_reviewer_multiplicity_or_deal_count(session, population):
    users, _, deal = population
    first, _, _ = await package(session, deal, users[1])
    second, _, _ = await package(session, deal, users[1], "pending_finance_legal", age=1)
    await package(session, deal, users[1], "ready_to_sign")
    await package(session, deal, users[1], "released")
    await package(session, deal, users[1], "rejected")
    session.add(Sow(opportunity_id=deal.id))  # Unsubmitted draft is not a package.
    for function in ("delivery", "hr", "sales", "finance", "legal"):
        session.add(ApprovalAssignment(package_id=first.id, function=function,
                                      approver_id=users[2].id, due_date=date(2026, 10, 5)))
    await session.flush()
    one = await listing(session, users[0], page=1, size=1)
    two = await listing(session, users[0], page=2, size=1)
    empty = await listing(session, users[0], page=3, size=1)
    assert one["total"] == two["total"] == empty["total"] == 2
    assert [row["id"] for row in one["items"] + two["items"]] == [str(second.id), str(first.id)]
    assert empty["items"] == []
    assert (await listing(session, users[3]))["total"] == 0
    assert (await listing(session, users[1]))["total"] == 2
    assigned = await listing(session, users[2])
    assert assigned["total"] == 1 and assigned["items"][0]["id"] == str(first.id)


@pytest.mark.asyncio
async def test_newest_nonvoided_per_sow_selected_before_status_filter(session, population):
    users, _, deal = population
    _, old_sow, _ = await package(session, deal, users[1])
    await package(session, deal, users[1], "ready_to_sign", sow=old_sow, age=1)
    current, live_sow, _ = await package(session, deal, users[1], "pending_ceo_exception")
    await package(session, deal, users[1], "voided", sow=live_sow, age=2)
    data = await listing(session, users[0])
    assert data["total"] == 1 and [row["id"] for row in data["items"]] == [str(current.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden", ["sow", "deal", "client", "version_discarded", "version_superseded", "package_superseded"])
async def test_nonlive_or_superseded_source_never_counts(session, population, hidden):
    users, account, deal = population
    row, sow, version = await package(session, deal, users[1])
    if hidden in {"sow", "deal", "client"}:
        {"sow": sow, "deal": deal, "client": account}[hidden].archived_at = datetime.now(UTC)
    elif hidden == "version_discarded":
        version.discarded_at = datetime.now(UTC)
    elif hidden == "version_superseded":
        version.superseded_by = uuid.uuid4()
    else:
        row.superseded_by = uuid.uuid4()
    await session.flush()
    assert (await listing(session, users[0]))["total"] == 0


@pytest.mark.asyncio
async def test_closed_stage_does_not_hide_pending_local_business_or_legacy_clientless(session, population):
    users, _, deal = population
    deal.stage_id = "closedwon"
    current, _, _ = await package(session, deal, users[1])
    legacy = Opportunity(owner_id=users[1].id, source="sow_upload", name="Legacy clientless")
    session.add(legacy)
    await session.flush()
    other, _, _ = await package(session, legacy, users[1])
    data = await listing(session, users[0])
    assert data["total"] == 2
    assert {row["id"] for row in data["items"]} == {str(current.id), str(other.id)}
    filtered = await listing(session, users[0], opportunity_id=str(deal.id))
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == str(current.id)


@pytest.fixture
async def granted(session, population):
    users, _, deal = population
    issued = await create_fixture(session, actor_id=users[4].id,
                                  label="Approval population", reviewer_ids=[users[5].id])
    fixture = await session.get(Opportunity, issued["opportunity_id"])
    expected, _, _ = await package(session, fixture, users[4])
    session.add(ApprovalAssignment(package_id=expected.id, function="sales",
                                  approver_id=users[5].id, due_date=date(2026, 10, 5)))
    sibling = Opportunity(client_id=fixture.client_id, owner_id=users[4].id,
                          source="sow_upload", name="Not issued")
    session.add(sibling)
    await session.flush()
    await package(session, sibling, users[4])
    real, _, _ = await package(session, deal, users[1])
    return users, fixture, expected, real


@pytest.mark.asyncio
async def test_exact_fixture_scope_applies_before_count_and_page(session, granted):
    users, _, expected, real = granted
    for actor in (users[4], users[5]):
        data = await listing(session, actor, size=1)
        assert data["total"] == 1 and data["items"][0]["id"] == str(expected.id)
    assert (await listing(session, users[6]))["total"] == 0
    normal = await listing(session, users[0])
    assert normal["total"] == 1 and normal["items"][0]["id"] == str(real.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["expired", "tenant", "environment", "owner", "issuer", "forged", "uploader"])
async def test_invalid_provenance_never_grants_count_or_rows(session, granted, monkeypatch, damage):
    users, fixture, expected, _ = granted
    if damage == "expired":
        grant = await session.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(fixture.client_id)))
        grant.after = {**grant.after, "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    elif damage in {"tenant", "environment"}:
        monkeypatch.setenv("DEALGATE_TENANT_ID" if damage == "tenant" else "DEALGATE_ENV", "wrong")
    elif damage == "owner":
        fixture.owner_id = users[5].id
    elif damage == "issuer":
        users[4].groups = ["officeapp-e2e"]
    elif damage == "uploader":
        version = await session.get(SowVersion, expected.sow_version_id)
        version.uploaded_by = users[6].id
    else:
        client = Client(name="S21 e2e forged fixture")
        session.add(client)
        await session.flush()
        fixture.client_id = client.id
    await session.flush()
    data = await listing(session, users[5])
    assert data["total"] == 0 and data["items"] == []


@pytest.mark.asyncio
async def test_existing_exact_status_semantics_remain_unchanged(session, population):
    users, _, deal = population
    older, sow, _ = await package(session, deal, users[1])
    await package(session, deal, users[1], "ready_to_sign", sow=sow, age=1)
    data = await listing(session, users[0], status="pending_delivery_hr")
    assert data["total"] == 1 and data["items"][0]["id"] == str(older.id)


@pytest.mark.asyncio
async def test_unchanged_pages_share_full_population_revision(session, population):
    users, _, deal = population
    first, _, _ = await package(session, deal, users[1], age=1)
    second, _, _ = await package(session, deal, users[1])
    one = await listing(session, users[0], page=1, size=1)
    revision = one["population_revision"]
    assert len(revision) == 64 and int(revision, 16) >= 0
    two = await listing(session, users[0], page=2, size=1, population_revision=revision)
    all_rows = await listing(session, users[0], size=200, population_revision=revision)
    assert one["total"] == two["total"] == all_rows["total"] == 2
    assert two["population_revision"] == all_rows["population_revision"] == revision
    assert [r["id"] for r in one["items"] + two["items"]] == [str(first.id), str(second.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("page", [1, 2])
async def test_equal_count_membership_swap_rejects_stale_page_or_card(session, population, page):
    users, _, deal = population
    outgoing, _, _ = await package(session, deal, users[1], age=2)
    stable, _, _ = await package(session, deal, users[1], age=1)
    incoming, _, _ = await package(session, deal, users[1], "ready_to_sign")
    initial = await listing(session, users[0], size=1)
    outgoing.status = "ready_to_sign"
    incoming.status = "pending_delivery_hr"
    await session.flush()
    stale = await listing(session, users[0], page=page, size=1,
                          population_revision=initial["population_revision"], expected_status=409)
    assert "refresh" in stale["detail"].lower()
    refreshed = await listing(session, users[0])
    assert refreshed["total"] == initial["total"] == 2
    assert {r["id"] for r in refreshed["items"]} == {str(stable.id), str(incoming.id)}
    assert refreshed["population_revision"] != initial["population_revision"]


@pytest.mark.asyncio
async def test_pending_state_change_invalidates_revision_without_membership_change(session, population):
    users, _, deal = population
    row, _, _ = await package(session, deal, users[1])
    initial = await listing(session, users[0])
    row.status = "pending_finance_legal"
    await session.flush()
    await listing(session, users[0], population_revision=initial["population_revision"], expected_status=409)


@pytest.mark.asyncio
async def test_revision_binds_viewer_and_opportunity_scope(session, population):
    users, _, deal = population
    await package(session, deal, users[1])
    initial = await listing(session, users[0])
    await listing(session, users[1], population_revision=initial["population_revision"], expected_status=409)
    await listing(session, users[0], opportunity_id=str(deal.id),
                  population_revision=initial["population_revision"], expected_status=409)


@pytest.mark.asyncio
async def test_empty_revision_and_legacy_list_contract(session, population):
    users, _, _ = population
    empty = await listing(session, users[0])
    assert empty["total"] == 0 and len(empty["population_revision"]) == 64
    unchanged = await listing(session, users[0], population_revision=empty["population_revision"])
    assert unchanged["population_revision"] == empty["population_revision"]
    legacy = await listing(session, users[0], status="pending_delivery_hr")
    assert legacy["total"] == 0 and legacy["population_revision"] is None
