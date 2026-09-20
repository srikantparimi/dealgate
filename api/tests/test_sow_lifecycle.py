"""SOW version lifecycle: revise, supersede, delete, discard (S10-06).

The gap these close: the versioning table existed but nothing in the
SOW-first flow reached it for a revision. Uploading a corrected SOW created a
*second opportunity* for the same engagement, or was refused as a duplicate.
And there was no delete route for a SOW, a version, an upload job or an
opportunity anywhere in the API.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.integrations.bedrock_sow_extract import StubBedrock, get_bedrock_sow
from app.integrations.s3_sow import StubS3, get_sow_s3
from app.main import app as main_app
from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.sow_lifecycle import (
    SowLifecycleError,
    delete_version,
    discard_version,
    reserve_version_no,
    was_ever_submitted,
)

OWNER_EMAIL = "delivery@smartek21.com"
FIXTURES = __import__("pathlib").Path(__file__).resolve().parents[2] / "fixtures" / "sample_sows"


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery,SystemAdmin")


@pytest_asyncio.fixture
async def app_with_deps(session):
    async def _override():
        yield session

    stub_s3 = StubS3()
    main_app.dependency_overrides[get_session] = _override
    main_app.dependency_overrides[get_sow_s3] = lambda: stub_s3
    main_app.dependency_overrides[get_bedrock_sow] = lambda: StubBedrock()
    main_app.state.stub_s3 = stub_s3
    try:
        yield main_app
    finally:
        for dep in (get_session, get_sow_s3, get_bedrock_sow):
            main_app.dependency_overrides.pop(dep, None)


async def _seed(session) -> tuple[Opportunity, Sow, SowVersion]:
    user = User(id=uuid.uuid4(), email=OWNER_EMAIL, name="Delivery", groups=["Delivery"])
    client = Client(id=uuid.uuid4(), name="Contoso Data Services, LLC")
    session.add_all([user, client])
    await session.flush()
    opp = Opportunity(
        id=uuid.uuid4(), client_id=client.id, owner_id=user.id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    v1 = SowVersion(
        id=uuid.uuid4(), sow_id=sow.id, uploaded_by=user.id,
        file_s3_key="sow/abc/v1.pdf", file_hash="hash-v1",
        extract_status="complete", version_no=1,
    )
    session.add(v1)
    await session.commit()
    return opp, sow, v1


# --- numbering ------------------------------------------------------------


async def test_version_numbers_are_never_reused_after_a_delete(session):
    """Delete the highest version and the next upload must not reuse its
    number.

    MAX(version_no) alone does not give this — MAX drops when the top row
    goes, so the next upload becomes "version 2" again and the audit trail
    holds two different documents under the same label. Hence the monotonic
    counter on `sow`.

    Note `reserve_version_no` is not a pure read: each call takes the next
    number. It is called once per version actually created.
    """

    _opp, sow, v1 = await _seed(session)

    n2 = await reserve_version_no(session, sow.id)
    assert n2 == 2
    v2 = SowVersion(
        id=uuid.uuid4(), sow_id=sow.id, file_s3_key="k2", file_hash="h2",
        extract_status="complete", version_no=n2,
    )
    session.add(v2)
    await session.commit()

    await delete_version(session, sow_version_id=v2.id, actor_id=v1.uploaded_by)
    await session.commit()

    # MAX(version_no) is back to 1 here — the counter is what stops the reuse.
    assert await reserve_version_no(session, sow.id) == 3


# --- delete vs discard ----------------------------------------------------


async def test_delete_is_refused_once_submitted(session):
    """A submitted version is part of a decision record."""

    _opp, _sow, v1 = await _seed(session)
    session.add(
        ApprovalPackage(
            id=uuid.uuid4(),
            opportunity_id=_opp.id,
            sow_version_id=v1.id,
            gm_model_id=uuid.uuid4(),
            policy_version_id=uuid.uuid4(),
            package_hash="x" * 64,
            status="pending_delivery_hr",
            submitted_by=v1.uploaded_by,
        )
    )
    await session.commit()

    assert await was_ever_submitted(session, v1.id) is True
    with pytest.raises(SowLifecycleError) as excinfo:
        await delete_version(session, sow_version_id=v1.id, actor_id=None)
    assert "discard it instead" in excinfo.value.message
    assert excinfo.value.status_code == 409


async def test_delete_writes_an_audit_row_that_outlives_the_record(session):
    """`audit_event.entity_id` is a plain string with no FK, so the trail
    survives the row it describes."""

    from app.models.audit import AuditEvent

    _opp, _sow, v1 = await _seed(session)
    await delete_version(
        session, sow_version_id=v1.id, actor_id=v1.uploaded_by, reason="wrong file"
    )
    await session.commit()

    assert (
        await session.execute(select(SowVersion).where(SowVersion.id == v1.id))
    ).scalar_one_or_none() is None

    audit = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity == "sow_version")
            .where(AuditEvent.entity_id == str(v1.id))
        )
    ).scalars().all()
    actions = {a.action for a in audit}
    assert "sow_version.deleted" in actions
    deleted = next(a for a in audit if a.action == "sow_version.deleted")
    assert deleted.before["file_hash"] == "hash-v1"
    assert deleted.after["reason"] == "wrong file"


async def test_discard_requires_a_reason_and_is_idempotent(session):
    _opp, _sow, v1 = await _seed(session)

    with pytest.raises(SowLifecycleError) as excinfo:
        await discard_version(session, sow_version_id=v1.id, actor_id=None, reason="  ")
    assert excinfo.value.status_code == 422

    first = await discard_version(
        session, sow_version_id=v1.id, actor_id=None, reason="superseded by hand"
    )
    stamp = first.discarded_at
    again = await discard_version(
        session, sow_version_id=v1.id, actor_id=None, reason="different reason"
    )
    # Idempotent — a second discard does not move the timestamp or the reason.
    assert again.discarded_at == stamp
    assert again.discard_reason == "superseded by hand"


async def test_deleting_a_version_clears_pointers_to_it(session):
    """Otherwise the delete fails on the FK and the caller gets a 500 for
    what is really an ordering problem."""

    _opp, sow, v1 = await _seed(session)
    v2 = SowVersion(
        id=uuid.uuid4(), sow_id=sow.id, file_s3_key="k2", file_hash="h2",
        extract_status="complete", version_no=2,
    )
    session.add(v2)
    await session.flush()
    v1.superseded_by = v2.id
    v1.execution_state = "superseded"
    await session.commit()

    await delete_version(session, sow_version_id=v2.id, actor_id=None)
    await session.commit()
    await session.refresh(v1)
    assert v1.superseded_by is None
    # v1 becomes current again rather than being stranded as superseded.
    assert v1.execution_state == "draft"


# --- endpoints ------------------------------------------------------------


async def test_revision_attaches_to_the_same_sow_and_supersedes(
    app_with_deps, session
):
    """The bug this closes: a corrected SOW used to create a whole new
    opportunity for the same engagement."""

    opp, sow, v1 = await _seed(session)
    docx = (FIXTURES / "08_assessment_fixed_fee.docx").read_bytes()

    async with _client(app_with_deps) as c:
        r = await c.post(
            f"/sows/{opp.id}/versions",
            headers={"X-Test-User": OWNER_EMAIL},
            files={
                "file": (
                    "revised.docx",
                    docx,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version_no"] == 2
    assert body["supersedes"] == str(v1.id)

    # Exactly one opportunity and one SOW — no duplicate engagement.
    assert len(list((await session.execute(select(Opportunity))).scalars())) == 1
    assert len(list((await session.execute(select(Sow))).scalars())) == 1

    versions = list(
        (await session.execute(select(SowVersion).where(SowVersion.sow_id == sow.id))).scalars()
    )
    assert len(versions) == 2
    old = next(v for v in versions if v.version_no == 1)
    assert old.superseded_by is not None
    assert old.execution_state == "superseded"


async def test_revision_rejects_identical_bytes(app_with_deps, session):
    """Re-uploading the same file is not a revision."""

    opp, sow, v1 = await _seed(session)
    docx = (FIXTURES / "08_assessment_fixed_fee.docx").read_bytes()
    from app.services.sow_upload_job_service import sha256_hex

    v1.file_hash = sha256_hex(docx)
    await session.commit()

    async with _client(app_with_deps) as c:
        r = await c.post(
            f"/sows/{opp.id}/versions",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("same.docx", docx, "application/octet-stream")},
        )
    assert r.status_code == 409
    assert "already version 1" in r.json()["detail"]


async def test_version_list_says_what_each_version_allows(app_with_deps, session):
    opp, _sow, v1 = await _seed(session)
    async with _client(app_with_deps) as c:
        r = await c.get(
            f"/sows/{opp.id}/versions", headers={"X-Test-User": OWNER_EMAIL}
        )
    assert r.status_code == 200, r.text
    rows = r.json()["versions"]
    assert len(rows) == 1
    assert rows[0]["version_no"] == 1
    assert rows[0]["is_current"] is True
    # Never submitted → deletable, not discardable.
    assert rows[0]["can_delete"] is True
    assert rows[0]["can_discard"] is False


async def test_delete_endpoint_removes_the_stored_object(app_with_deps, session):
    opp, _sow, v1 = await _seed(session)
    async with _client(app_with_deps) as c:
        r = await c.delete(
            f"/sows/versions/{v1.id}?reason=test+upload",
            headers={"X-Test-User": OWNER_EMAIL},
        )
    assert r.status_code == 200, r.text
    assert main_app.state.stub_s3.deleted_keys == ["sow/abc/v1.pdf"]


async def test_revision_rejects_a_non_sow(app_with_deps, session):
    opp, _sow, _v1 = await _seed(session)
    resume = (FIXTURES / "99_resume.pdf").read_bytes()
    async with _client(app_with_deps) as c:
        r = await c.post(
            f"/sows/{opp.id}/versions",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("cv.pdf", resume, "application/pdf")},
        )
    assert r.status_code == 422
    assert r.json()["detail"]["detected_type"] == "resume"


# --- parallel contracts vs accidental re-uploads (S10-09) ----------------


async def test_open_sows_for_client_lists_the_others(session):
    """A client legitimately runs several contracts at once, so a second SOW
    is never blocked. But someone re-uploading a corrected file from the
    wrong screen lands in the same place, and silently creating a second
    opportunity gives them two of the same engagement with separate approval
    trails. This surfaces what already exists so the screen can ask."""

    from app.services.sow_lifecycle import open_sows_for_client

    opp_a, sow_a, v1 = await _seed(session)
    client_id = opp_a.client_id

    # A second, genuinely parallel contract for the same client.
    opp_b = Opportunity(
        id=uuid.uuid4(), client_id=client_id, owner_id=v1.uploaded_by,
        governance_status="Intake",
    )
    session.add(opp_b)
    await session.flush()
    sow_b = Sow(id=uuid.uuid4(), opportunity_id=opp_b.id)
    session.add(sow_b)
    await session.flush()
    session.add(
        SowVersion(
            id=uuid.uuid4(), sow_id=sow_b.id, file_s3_key="k", file_hash="h-b",
            extract_status="complete", version_no=1,
        )
    )
    await session.commit()

    # Asked from B's perspective, A shows up — and vice versa.
    from_b = await open_sows_for_client(
        session, client_id, exclude_opportunity_id=opp_b.id
    )
    assert [o.opportunity_id for o in from_b] == [opp_a.id]

    both = await open_sows_for_client(session, client_id)
    assert len(both) == 2


async def test_superseded_and_discarded_versions_are_not_offered(session):
    """Only what is actually in progress. A superseded version is history and
    a discarded one was a mistake; offering either as "did you mean this?"
    would send someone back to a dead record."""

    from app.services.sow_lifecycle import discard_version, open_sows_for_client

    opp, _sow, v1 = await _seed(session)
    assert len(await open_sows_for_client(session, opp.client_id)) == 1

    await discard_version(
        session, sow_version_id=v1.id, actor_id=None, reason="wrong client"
    )
    await session.commit()

    assert await open_sows_for_client(session, opp.client_id) == []
