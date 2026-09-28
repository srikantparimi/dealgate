import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.client import Agreement, Client, LegalEntity
from app.models.task import Task
from app.models.user import User
from tests.test_agreements import app_with_session, seeded, _client  # noqa: F401


@pytest.mark.asyncio
async def test_signed_upload_confirmation_roles_sources_and_idempotency(
    app_with_session, seeded, session, monkeypatch  # noqa: F811
):
    from io import BytesIO
    from zipfile import ZipFile
    from app.integrations.bedrock_sow_extract import get_bedrock_sow, StubBedrock
    from app.models.agreement_tracking import AgreementDocument

    row = Agreement(
        id=uuid.uuid4(), legal_entity_id=seeded["entity"].id, kind="NDA", state="missing"
    )
    session.add(row)
    await session.commit()
    data = BytesIO()
    with ZipFile(data, "w") as doc:
        doc.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Signed non-disclosure agreement for S16 Test Company. Effective 2026-01-01 through 2027-01-01.</w:t></w:r></w:p></w:body></w:document>',
        )
    app_with_session.dependency_overrides[get_bedrock_sow] = lambda: StubBedrock()
    headers = {"X-Test-User": "legal@example.test"}
    ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try:
        async with _client(app_with_session) as c:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
            denied = await c.post(
                f"/agreements/{row.id}/extract",
                headers=headers,
                files={"file": ("signed.docx", data.getvalue(), ct)},
            )
            assert denied.status_code == 403
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
            response = await c.post(
                f"/agreements/{row.id}/extract",
                headers=headers,
                files={"file": ("signed.docx", data.getvalue(), ct)},
            )
            assert response.status_code == 200, response.text
            draft = response.json()
            assert draft["fields"]["effective_from"]["page_ref"] >= 1
            assert row.state == "missing"
            body = {
                "document_id": draft["id"],
                "effective_from": "2026-01-01",
                "expiry": "2027-01-01",
                "signed_confirmed": False,
                "correction_reason": "Dates verified against signed source",
            }
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
            response = await c.post(f"/agreements/{row.id}/execute", headers=headers, json=body)
            assert response.status_code == 403
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
            response = await c.post(f"/agreements/{row.id}/execute", headers=headers, json=body)
            assert response.status_code == 422
            body["signed_confirmed"] = True
            response = await c.post(f"/agreements/{row.id}/execute", headers=headers, json=body)
            assert response.status_code == 200, response.text
            assert response.json()["state"] == "executed"
            assert response.json()["evidence_s3_key"] in app_with_session.state.stub_s3.objects
            response = await c.post(f"/agreements/{row.id}/execute", headers=headers, json=body)
            assert response.status_code == 200
            assert len(list((await session.scalars(select(AgreementDocument))).all())) == 1
    finally:
        app_with_session.dependency_overrides.pop(get_bedrock_sow, None)


@pytest.mark.asyncio
async def test_new_company_gap_tasks_are_owned_idempotent_and_complete(session):
    from app.services.agreement_tracking import ensure_agreement_tasks

    owner = User(
        id=uuid.uuid4(), email="account@example.test", name="Account Owner", groups=["Sales"]
    )
    client = Client(id=uuid.uuid4(), name="S16 Test Company")
    entity = LegalEntity(id=uuid.uuid4(), client_id=client.id, name=client.name)
    session.add_all([owner, client, entity])
    await session.flush()
    for _ in range(2):
        await ensure_agreement_tasks(
            session, client_id=client.id, owner_id=owner.id, actor_id=owner.id
        )
    tasks = list((await session.scalars(select(Task))).all())
    assert len(tasks) == 2
    assert all(t.owner_id == owner.id and t.category == "coverage" for t in tasks)
    assert {t.subject for t in tasks} == {
        "Obtain NDA - S16 Test Company",
        "Obtain MSA - S16 Test Company",
    }
    agreements = list((await session.scalars(select(Agreement))).all())
    assert {a.kind for a in agreements} == {"NDA", "MSA"}
    for a in agreements:
        a.state = "executed"
        a.effective_from = date.today()
        a.expiry = date.today() + timedelta(days=365)
        a.evidence_s3_key = f"agreements/{a.id}/signed.pdf"
    await ensure_agreement_tasks(session, client_id=client.id, owner_id=owner.id, actor_id=owner.id)
    assert all(t.status == "done" for t in tasks)


def test_tracking_skips_review_ceremony_but_requires_signed_evidence():
    from app.services.agreement_state import InvalidAgreementTransition, transition

    row = Agreement(kind="NDA", state="missing")
    transition(row, "requested", None)
    transition(row, "sent", None)
    with pytest.raises(InvalidAgreementTransition):
        transition(row, "under_review", None)
    with pytest.raises(InvalidAgreementTransition):
        transition(row, "executed", None)
    row.effective_from, row.expiry = date.today(), date.today() + timedelta(days=365)
    row.evidence_s3_key = "agreements/fixture/signed.pdf"
    transition(row, "executed", None)
    assert row.state == "executed"


@pytest.mark.asyncio
async def test_review_allowed_without_coverage_but_signature_blocked(session):
    from tests.test_coverage_gate import _seed_owner, _seed_opp_gm
    from app.services.approvals import submit_package
    from app.services.signed_sow import create_upload, SignedSowError

    owner = await _seed_owner(session, "review@example.test")
    opp, _ = await _seed_opp_gm(session, owner, None)
    package = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert package.status == "pending_delivery_hr"
    package.status = "ready_to_sign"
    await session.flush()
    with pytest.raises(SignedSowError, match="MSA.*NDA required"):
        await create_upload(
            session,
            actor_id=owner.id,
            package_id=package.id,
            file_s3_key="sow/fixture/signed.pdf",
            file_hash="s16-signature",
        )


@pytest.mark.asyncio
async def test_sow_intake_creates_gap_tasks_and_draft_client_remains_deletable(session):
    from app.models.agreement_tracking import AgreementGap
    from app.services.deletion import delete_client
    from app.services.sow_upload_job_service import _create_opportunity
    from tests.test_coverage_gate import _seed_owner

    owner = await _seed_owner(session, "intake@example.test")
    client = Client(id=uuid.uuid4(), name="Example Intake Company")
    session.add(client)
    await session.flush()
    await _create_opportunity(session, uploader_id=owner.id, client_id=client.id)
    tasks = list((await session.scalars(select(Task).where(Task.category == "coverage"))).all())
    assert len(tasks) == 2
    assert all(t.owner_id == owner.id for t in tasks)
    await delete_client(session, client_id=client.id, actor_id=owner.id)
    assert list((await session.scalars(select(AgreementGap))).all()) == []


@pytest.mark.asyncio
async def test_agreement_evidence_prevents_hard_delete(session):
    from app.models.agreement_tracking import AgreementDocument
    from app.services.deletion import assess_client, delete_client, DeletionError
    from tests.test_coverage_gate import _seed_owner, _seed_client_with_agreements

    owner = await _seed_owner(session, "evidence@example.test")
    client, entities = await _seed_client_with_agreements(session, kinds_executed=())
    agreement = Agreement(
        id=uuid.uuid4(), legal_entity_id=entities[0].id, kind="NDA", state="missing"
    )
    session.add(agreement)
    await session.flush()
    session.add(
        AgreementDocument(
            agreement_id=agreement.id,
            file_hash="s16-evidence",
            file_s3_key="agreements/fixture.pdf",
            extracted_fields={},
            uploaded_by=owner.id,
        )
    )
    await session.flush()
    assert (await assess_client(session, client.id)).state == "approved"
    with pytest.raises(DeletionError, match="archive"):
        await delete_client(session, client_id=client.id, actor_id=owner.id)
