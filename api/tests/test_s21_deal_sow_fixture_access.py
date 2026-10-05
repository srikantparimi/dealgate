"""Real ORM/ASGI isolation boundaries; storage is a deterministic provider stub."""
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.s3_sow import StubS3, get_sow_s3
from app.models.audit import AuditEvent
from app.models.approval import ApprovalPackage
from app.models.approval_routing import ApprovalAssignment
from app.models.client import Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User
from app.routers.deals import router as deals_router
from app.routers.sow import router as sow_router
from app.routers.sows_staffing import router as history_router
from app.services.test_fixtures import create_fixture


@pytest.fixture
async def scoped_api(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "deal-sow-scope")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    people = [User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name=name, groups=groups)
        for name, groups in [("Issuer", ["SystemAdmin", "officeapp-e2e"]),
                             ("Ordinary admin", ["SystemAdmin"]),
                             ("Unissued tester", ["SystemAdmin", "officeapp-e2e"]),
                             ("Sales owner", ["Sales"])]]
    session.add_all(people)
    await session.flush()
    issued = await create_fixture(session, actor_id=people[0].id, label="Private fixture", reviewer_ids=[])
    private = await session.get(Opportunity, issued["opportunity_id"])
    private.next_client_date = date(2026, 1, 1)
    real_client = Client(name="Ordinary synthetic account")
    session.add(real_client)
    await session.flush()
    real = Opportunity(client_id=real_client.id, owner_id=people[3].id, source="manual",
        name="Ordinary synthetic deal", governance_status="Intake", next_client_date=date(2026, 2, 1))
    sibling = Opportunity(client_id=private.client_id, owner_id=people[0].id, source="manual",
        name="Unissued sibling", governance_status="Intake", next_client_date=date(2026, 1, 2))
    session.add_all([real, sibling])
    await session.flush()
    versions = {}
    for key, deal, uploader in [("private", private, people[0]), ("real", real, people[3]), ("sibling", sibling, people[0])]:
        sow = Sow(opportunity_id=deal.id, version_counter=1)
        session.add(sow)
        await session.flush()
        version = SowVersion(sow_id=sow.id, uploaded_by=uploader.id,
            file_s3_key=f"synthetic/{key}.pdf", file_hash=key, version_no=1,
            extract_status="complete", extracted_fields={})
        session.add(version)
        versions[key] = version
    await session.commit()
    active = {"index": 0, "alias": None}
    storage = StubS3()
    app = FastAPI()
    for router in (deals_router, sow_router, history_router):
        app.include_router(router)

    async def db():
        yield session

    def actor():
        person = people[active["index"]]
        return AuthUser(active["alias"] or person.id, person.email, person.name, tuple(person.groups))

    app.dependency_overrides[get_session] = db
    app.dependency_overrides[current_user] = actor
    app.dependency_overrides[get_sow_s3] = lambda: storage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, active, people, private, real, sibling, versions, storage


def read_urls(deal, version):
    return [f"/deals/{deal.id}", f"/sow/opportunity/{deal.id}/current",
            f"/sow/versions/{version.id}", f"/sows/{deal.id}/versions"]


@pytest.mark.asyncio
@pytest.mark.parametrize("index,expected", [(0, "private"), (1, "real"), (2, None), (3, "real")])
async def test_list_scope_precedes_pagination_and_direct_reads(scoped_api, index, expected):
    client, active, _, private, real, sibling, versions, storage = scoped_api
    active["index"] = index
    wanted = {"private": private, "real": real}.get(expected)
    response = await client.get("/deals?size=1")
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["items"]] == ([str(wanted.id)] if wanted else [])
    assert response.json()["total"] == (1 if wanted else 0)
    assert (await client.get("/deals?size=1&page=2")).json()["items"] == []
    for key, deal in [("private", private), ("real", real), ("sibling", sibling)]:
        for url in read_urls(deal, versions[key]):
            before = list(storage.download_calls)
            result = await client.get(url)
            assert result.status_code == (200 if key == expected else 404), (url, result.text)
            if key != expected:
                assert str(deal.id) not in result.text
                assert storage.download_calls == before


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["expired", "tenant", "environment", "issuer", "owner", "mirror"])
async def test_invalid_provenance_denies_list_current_history_and_download(session, scoped_api, damage):
    client, _, people, private, _, _, versions, storage = scoped_api
    grant = await session.scalar(select(AuditEvent).where(AuditEvent.action == "test.fixture_created",
        AuditEvent.entity_id == str(private.client_id)))
    data = dict(grant.after)
    if damage == "expired":
        data["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    if damage == "tenant":
        data["tenant_id"] = "foreign"
    if damage == "environment":
        data["environment"] = "foreign"
    if damage == "issuer":
        grant.actor_id = people[1].id
    if damage == "owner":
        private.owner_id = people[2].id
    if damage == "mirror":
        private.hubspot_deal_id = "synthetic-mirror"
    grant.after = data
    await session.commit()
    assert (await client.get("/deals")).json()["total"] == 0
    for url in read_urls(private, versions["private"]):
        assert (await client.get(url)).status_code == 404, url
    assert storage.download_calls == []


@pytest.mark.asyncio
async def test_canonical_invited_identity_preserves_owner_access(scoped_api):
    client, active, _, private, _, _, versions, _ = scoped_api
    active["alias"] = uuid.uuid4()
    result = await client.get("/deals?owner=me")
    assert result.status_code == 200
    assert [row["id"] for row in result.json()["items"]] == [str(private.id)]
    for url in read_urls(private, versions["private"]):
        assert (await client.get(url)).status_code == 200, url


@pytest.mark.asyncio
async def test_regular_sow_read_roles_are_not_replaced_with_owner_only_policy(session, scoped_api):
    client, active, people, _, real, _, versions, _ = scoped_api
    other = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Other Sales", groups=["Sales"])
    session.add(other)
    await session.commit()
    people.append(other)
    active["index"] = len(people) - 1
    assert (await client.get(f"/deals/{real.id}")).status_code == 403
    for url in read_urls(real, versions["real"])[1:]:
        assert (await client.get(url)).status_code == 200, url


@pytest.mark.asyncio
async def test_tasks_require_this_deals_authoritative_assignment_not_shared_owner(session, scoped_api):
    client, _, people, private, _, sibling, versions, _ = scoped_api
    tasks = {}
    for name, deal in [("private", private), ("sibling", sibling)]:
        version = versions[name]
        model = GmModel(opportunity_id=deal.id, sow_version_id=version.id, engagement_type="fixed_bid")
        task = Task(owner_id=people[0].id, subject=f"{name} task", status="assigned")
        session.add_all([model, task])
        await session.flush()
        package = ApprovalPackage(opportunity_id=deal.id, sow_version_id=version.id,
            gm_model_id=model.id, package_hash=name, status="pending_delivery_hr", submitted_by=people[0].id)
        session.add(package)
        await session.flush()
        session.add(ApprovalAssignment(package_id=package.id, function="delivery", approver_id=people[0].id,
            due_date=date(2026, 1, 1), task_id=task.id))
        tasks[name] = task
    session.add(Task(owner_id=people[0].id, subject="No provable deal lineage", status="assigned"))
    await session.commit()
    response = await client.get(f"/deals/{private.id}")
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["tasks"]] == [str(tasks["private"].id)]


@pytest.mark.asyncio
async def test_foreign_version_uploader_is_not_an_authorized_fixture_document(session, scoped_api):
    client, _, people, private, _, _, versions, storage = scoped_api
    versions["private"].uploaded_by = people[1].id
    await session.commit()
    for url in read_urls(private, versions["private"])[1:3]:
        assert (await client.get(url)).status_code == 404
    history = await client.get(f"/sows/{private.id}/versions")
    assert history.status_code == 200
    assert history.json()["versions"] == []
    assert storage.download_calls == []


@pytest.mark.asyncio
async def test_denied_confirmation_and_mutations_have_no_provider_or_business_effects(session, scoped_api):
    client, active, _, private, _, _, versions, storage = scoped_api
    active["index"] = 1
    version = versions["private"]
    requests = [("GET", f"/sow/{private.id}/confirmation", None),
        ("GET", f"/sow/versions/{version.id}/extraction-conflicts", None),
        ("PATCH", f"/deals/{private.id}", {"next_client_action": "unauthorized"}),
        ("POST", f"/sow/{private.id}/upload-url", {"filename": "blocked.pdf", "content_type": "application/pdf"}),
        ("POST", f"/sow/{private.id}/versions", {"file_s3_key": "blocked.pdf", "file_hash": "blocked"}),
        ("PATCH", f"/sow/versions/{version.id}/fields/client_name", {"value": "unauthorized"}),
        ("POST", f"/sow/{private.id}/confirmation/submit", None),
        ("POST", f"/sow/versions/{version.id}/reextract", None),
        ("POST", f"/sow/versions/{version.id}/submit", None)]
    for method, url, body in requests:
        result = await client.request(method, url, json=body)
        assert result.status_code == 404, (url, result.text)
    await session.refresh(private)
    await session.refresh(version)
    assert private.next_client_action is None
    assert version.extracted_fields == {}
    assert version.confirmed_at is None
    assert storage.upload_calls == []
    assert storage.download_calls == []


@pytest.fixture(params=[("Legal", False), ("HR", False), ("Legal", True), ("HR", True)],
    ids=["legal-business", "hr-business", "legal-fixture", "hr-fixture"])
async def history_reader(session, scoped_api, request):
    client, active, people, _, real, _, versions, storage = scoped_api
    role, test_identity = request.param
    person = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name=f"{role} reader",
        groups=[role] + (["officeapp-e2e"] if test_identity else []))
    session.add(person)
    await session.flush()
    deal, version = real, versions["real"]
    if test_identity:
        issued = await create_fixture(session, actor_id=people[0].id,
            label=f"{role} history", reviewer_ids=[person.id])
        deal = await session.get(Opportunity, issued["opportunity_id"])
        sow = Sow(opportunity_id=deal.id, version_counter=1)
        session.add(sow)
        await session.flush()
        version = SowVersion(sow_id=sow.id, uploaded_by=people[0].id,
            file_s3_key=f"synthetic/{role}-history.pdf", file_hash=f"{role}-history",
            version_no=1, extract_status="complete", extracted_fields={})
        session.add(version)
    await session.commit()
    people.append(person)
    active["index"] = len(people) - 1
    active["alias"] = uuid.uuid4()
    return client, deal, version, storage, test_identity


@pytest.mark.asyncio
async def test_legal_hr_documents_history_matches_existing_sow_read_scope(session, scoped_api, history_reader):
    client, deal, version, _, test_identity = history_reader
    _, _, _, private, real, sibling, versions, _ = scoped_api
    for url in read_urls(deal, version)[1:]:
        response = await client.get(url)
        assert response.status_code == 200, (url, response.text)
    history = response.json()
    assert history["sow_id"] == str(version.sow_id)
    assert [row["id"] for row in history["versions"]] == [str(version.id)]
    assert history["versions"][0]["version_no"] == 1
    assert history["versions"][0]["is_current"] is True
    forbidden = [(private, versions["private"]), (sibling, versions["sibling"])]
    if test_identity:
        forbidden.append((real, versions["real"]))
    for forbidden_deal, forbidden_version in forbidden:
        for url in read_urls(forbidden_deal, forbidden_version)[1:]:
            response = await client.get(url)
            assert response.status_code == 404, (url, response.text)
            assert str(forbidden_deal.id) not in response.text
    if test_identity:
        grant = await session.scalar(select(AuditEvent).where(AuditEvent.action == "test.fixture_created",
            AuditEvent.entity_id == str(deal.client_id)))
        grant.after = {**grant.after, "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
        await session.commit()
        for url in read_urls(deal, version)[1:]:
            response = await client.get(url)
            assert response.status_code == 404, (url, response.text)


@pytest.mark.asyncio
async def test_legal_hr_history_access_does_not_grant_staffing_writes(session, history_reader):
    client, deal, version, storage, _ = history_reader
    before_audits = set((await session.scalars(select(AuditEvent.id))).all())
    before_versions = set((await session.scalars(select(SowVersion.id))).all())
    for path in ("staffing/import", "versions"):
        response = await client.post(f"/sows/{deal.id}/{path}",
            files={"file": ("synthetic.pdf", b"synthetic bytes", "application/pdf")})
        assert response.status_code == 403, (path, response.text)
    for path in ("staffing", "resources"):
        response = await client.put(f"/sows/{deal.id}/{path}",
            json={"engagement_type": "fixed_bid", "resource_lines": []})
        assert response.status_code == 403, (path, response.text)
    assert set((await session.scalars(select(AuditEvent.id))).all()) == before_audits
    assert set((await session.scalars(select(SowVersion.id))).all()) == before_versions
    assert list((await session.scalars(select(GmModel.id))).all()) == []
    await session.refresh(version)
    assert version.extracted_fields == {}
    assert storage.upload_calls == []
