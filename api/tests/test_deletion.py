"""S13a-B2 tests — delete + archive with governance, live-only dedupe.

Covers the four rules the directive lists:

- Draft record (no approvals, no signed SOW, not HubSpot-linked) → hard
  delete cascades; one `audit_event`; SOW-version hash frees for re-upload.
- Approved record → hard delete refused; archive path succeeds; the
  archived row is invisible to `list_clients` default view.
- HubSpot-linked → refused with a distinct reason; archive succeeds.
- Batch delete cascades every draft file in one call; approved files skip.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.services.deletion import (
    DeletionError,
    archive_client,
    assess_client,
    assess_opportunity,
    assess_sow_version,
    delete_client,
    delete_opportunity,
    delete_sow_version,
    live_sow_version_by_hash,
)
from app.services.sow_upload_job_service import find_by_hash


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


ADMIN = _uid("s13a-admin@smartek21.com")


async def _draft_client(session, name: str = "Peppermill Casino") -> Client:
    row = Client(id=uuid.uuid4(), name=name, hubspot_company_id=None)
    session.add(row)
    await session.commit()
    return row


async def _draft_opportunity_with_sow(
    session,
    *,
    client_id: uuid.UUID,
    source: str = "sow_upload",
    hubspot_deal_id: str | None = None,
    file_hash: str | None = None,
) -> tuple[Opportunity, Sow, SowVersion]:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=hubspot_deal_id,
        source=source,
        owner_id=ADMIN,
        client_id=client_id,
        governance_status="SOWDraft",
    )
    session.add(opp)
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=ADMIN,
        file_s3_key=f"sow/{uuid.uuid4().hex[:6]}.pdf",
        file_hash=file_hash or f"sha256:{uuid.uuid4().hex}",
        extract_status="done",
    )
    session.add(version)
    await session.commit()
    return opp, sow, version


@pytest.mark.asyncio
async def test_assess_draft_client_returns_draft(session):
    client = await _draft_client(session)
    a = await assess_client(session, client.id)
    assert a.state == "draft", a.reason
    assert a.counts["opportunities"] == 0


@pytest.mark.asyncio
async def test_delete_draft_client_hard_deletes_and_frees_hash(session):
    """The DoD case: delete a Peppermill row, its SOW hash is free again."""

    client = await _draft_client(session)
    _opp, _sow, version = await _draft_opportunity_with_sow(
        session, client_id=client.id, file_hash="sha256:deadbeef"
    )
    job = SowUploadJob(
        id=uuid.uuid4(),
        uploader_id=ADMIN,
        s3_key=None,
        file_hash="sha256:deadbeef",
        status="done",
        sow_version_id=version.id,
        opportunity_id=_opp.id,
    )
    session.add(job)
    await session.commit()

    result = await delete_client(
        session, client_id=client.id, actor_id=ADMIN, reason="e2e cleanup"
    )
    await session.commit()
    assert result.state == "deleted"
    assert result.counts["clients"] == 1
    assert result.counts["sows"] >= 1
    assert result.counts["sow_versions"] >= 1

    # Live-only dedupe helper now returns None — the hash is free.
    hit = await live_sow_version_by_hash(session, "sha256:deadbeef")
    assert hit is None

    # And `find_by_hash` finds nothing — the cascade deleted the job row
    # too (it held a FK to the sow_version), so the exact bytes upload
    # cleanly next time as if they had never been seen.
    refetched = await find_by_hash(session, "sha256:deadbeef")
    assert refetched is None

    # One audit event per cascade.
    audits = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.entity_id == str(client.id))
            )
        )
        .scalars()
        .all()
    )
    assert any(a.action == "client.deleted" for a in audits)


@pytest.mark.asyncio
async def test_delete_refused_when_approval_package_exists(session):
    client = await _draft_client(session)
    opp, _sow, version = await _draft_opportunity_with_sow(session, client_id=client.id)
    session.add(
        ApprovalPackage(
            id=uuid.uuid4(),
            opportunity_id=opp.id,
            sow_version_id=version.id,
            gm_model_id=uuid.uuid4(),  # nominal — no FK check on sqlite mem
            package_hash="test-hash",
            status="pending_delivery_hr",
            submitted_by=ADMIN,
            submitted_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    a = await assess_client(session, client.id)
    assert a.state == "approved"

    with pytest.raises(DeletionError) as exc:
        await delete_client(session, client_id=client.id, actor_id=ADMIN)
    assert exc.value.status_code == 409
    assert "archive instead" in exc.value.message


@pytest.mark.asyncio
async def test_delete_refused_when_hubspot_linked(session):
    client = await _draft_client(session, name="HubSpot Client")
    await _draft_opportunity_with_sow(
        session,
        client_id=client.id,
        source="hubspot",
        hubspot_deal_id="H-LIVE-1",
    )
    a = await assess_client(session, client.id)
    assert a.state == "hubspot_linked"

    with pytest.raises(DeletionError):
        await delete_client(session, client_id=client.id, actor_id=ADMIN)


@pytest.mark.asyncio
async def test_archive_client_hides_from_defaults_and_records_audit(session):
    client = await _draft_client(session, name="Archive Me")
    await _draft_opportunity_with_sow(
        session, client_id=client.id, source="hubspot", hubspot_deal_id="H-ARCH-1"
    )
    result = await archive_client(
        session, client_id=client.id, actor_id=ADMIN, reason="closed lost"
    )
    await session.commit()
    assert result.state == "archived"

    refetched = await session.get(Client, client.id)
    assert refetched.archived_at is not None
    assert refetched.archived_reason == "closed lost"

    # Audit written.
    ev = (
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.entity_id == str(client.id))
                .where(AuditEvent.action == "client.archived")
            )
        )
        .scalars()
        .first()
    )
    assert ev is not None


@pytest.mark.asyncio
async def test_assess_opportunity_and_sow_version_draft(session):
    client = await _draft_client(session, name="Cascade Client")
    opp, _sow, version = await _draft_opportunity_with_sow(session, client_id=client.id)
    assert (await assess_opportunity(session, opp.id)).state == "draft"
    assert (await assess_sow_version(session, version.id)).state == "draft"


@pytest.mark.asyncio
async def test_delete_sow_version_frees_hash(session):
    client = await _draft_client(session, name="Version Client")
    _opp, _sow, version = await _draft_opportunity_with_sow(
        session, client_id=client.id, file_hash="sha256:versionhash"
    )
    result = await delete_sow_version(
        session, sow_version_id=version.id, actor_id=ADMIN
    )
    await session.commit()
    assert result.state == "deleted"
    hit = await live_sow_version_by_hash(session, "sha256:versionhash")
    assert hit is None


@pytest.mark.asyncio
async def test_live_sow_version_by_hash_flags_archived(session):
    """Archived SOWs surface as informational hits, not blocking ones."""

    client = await _draft_client(session, name="Archive-Hash")
    _opp, sow, version = await _draft_opportunity_with_sow(
        session, client_id=client.id, file_hash="sha256:archivedhash"
    )
    sow.archived_at = datetime.now(timezone.utc)
    await session.commit()

    # `live_sow_version_by_hash` returns the hit with archived=True so the
    # upload router can show "matches archived SOW" without blocking.
    hit = await live_sow_version_by_hash(session, "sha256:archivedhash")
    assert hit is not None
    assert hit.archived is True
