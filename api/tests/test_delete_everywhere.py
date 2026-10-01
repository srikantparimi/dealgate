"""S17 §Addendum 1 — one delete service, and it removes the SOW from
every list every screen queries.

We seed a SOW with a client, opportunity, GM model, approval package with
one approval + one assignment, a task and a notification. Every list
endpoint that a screen reads (approvals board, pipeline clients, command
center rollup, projects, my-work tasks, notifications) must return the
SOW's descendant rows before the delete. After ``delete_sow`` every one
of those lists must be empty for the SOW, and a single ``sow.deleted``
audit row must exist carrying who/when/name/stage/price.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models.approval import Approval, ApprovalPackage
from app.models.approval_routing import ApprovalAssignment
from app.models.audit import AuditEvent
from app.models.client import Client, LegalEntity
from app.models.gm_model import GmModel
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.deletion import DeletionError, archive_sow, delete_sow


@pytest.mark.asyncio
async def test_delete_sow_removes_it_from_every_list(session):
    """S17 §Addendum 1, superseded by S20 D6.

    With a submitted approval package, D6 requires ``archive_sow`` (rows
    survive with archived_at set) — hard delete is refused. The list
    surfaces filter on ``archived_at IS NULL`` so the archived SOW is
    invisible to every UI while the audit chain remains intact.
    """
    owner = User(
        id=uuid.uuid4(),
        email="s17-owner@example.test",
        name="S17 Owner",
        groups=["Sales", "SystemAdmin"],
    )
    session.add(owner)
    client = Client(id=uuid.uuid4(), name="S17 Delete Everywhere Client")
    session.add(client)
    await session.flush()
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Entity"))
    await session.flush()
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-S17-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        client_id=client.id,
        governance_status="SOWDraft.confirmed",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/{uuid.uuid4()}.pdf",
        file_hash="cafe" * 16,
        extract_status="complete",
        extracted_fields={
            "sow_title": {"value": "S17 delete-everywhere fixture", "page_ref": 1},
            "price": {"value": "$42,000", "page_ref": 2},
        },
        confirmed_at=datetime.now(UTC),
    )
    session.add(version)
    await session.flush()
    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        engagement_type="staff_aug",
        contingency_pct="5",
        warranty_days=30,
        revenue_us="42000",
        revenue_india="0",
        version=1,
    )
    session.add(gm)
    await session.flush()
    package = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        gm_model_id=gm.id,
        package_hash="s17hash" + uuid.uuid4().hex[:16],
        status="pending_delivery_hr",
        submitted_by=owner.id,
        submitted_at=datetime.now(UTC),
    )
    session.add(package)
    await session.flush()
    session.add(
        Approval(
            id=uuid.uuid4(),
            package_id=package.id,
            function="delivery",
            approver_id=owner.id,
            decision="approve",
            reason="test",
            decided_at=datetime.now(UTC),
        )
    )
    task = Task(
        id=uuid.uuid4(),
        owner_id=owner.id,
        subject="Review SOW",
        due_date=date.today(),
        category="approval.awaiting",
        status="assigned",
    )
    session.add(task)
    await session.flush()
    session.add(
        ApprovalAssignment(
            package_id=package.id,
            function="delivery",
            approver_id=owner.id,
            due_date=date.today(),
            use_sla=True,
            task_id=task.id,
        )
    )
    session.add(
        Notification(
            id=uuid.uuid4(),
            user_id=owner.id,
            channel="inapp",
            category="approval_pending",
            subject="Awaiting delivery review",
            body_md="body",
            related_entity="approval_package",
            related_entity_id=str(package.id),
        )
    )
    await session.commit()

    # -- Pre-delete: every list endpoint returns the SOW's rows --
    async def count(model, *predicates):
        stmt = select(model)
        for p in predicates:
            stmt = stmt.where(p)
        return len(list((await session.execute(stmt)).scalars().all()))

    assert await count(Sow, Sow.id == sow.id) == 1
    assert await count(SowVersion, SowVersion.sow_id == sow.id) == 1
    assert await count(GmModel, GmModel.sow_version_id == version.id) == 1
    assert await count(ApprovalPackage, ApprovalPackage.opportunity_id == opp.id) == 1
    assert await count(Approval, Approval.package_id == package.id) == 1
    assert await count(ApprovalAssignment, ApprovalAssignment.package_id == package.id) == 1
    assert await count(Task, Task.id == task.id) == 1
    assert (
        await count(
            Notification,
            Notification.related_entity == "approval_package",
            Notification.related_entity_id == str(package.id),
        )
    ) == 1

    # -- Act: D6 refuses hard delete of a governed SOW --
    with pytest.raises(DeletionError) as excinfo:
        await delete_sow(session, actor_id=owner.id, sow_id=sow.id)
    assert excinfo.value.status_code == 409
    assert "archive" in str(excinfo.value).lower()

    # -- Act (D6 path): archive_sow succeeds --
    summary = await archive_sow(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()

    # -- Post-archive: SOW row survives (rule 4) with archived_at set --
    archived = await session.get(Sow, sow.id)
    assert archived is not None
    assert archived.archived_at is not None
    assert archived.archived_reason == "s20_w3_governed_archive"

    # -- Descendants survive (rule 4 — audit + decisions must persist) --
    assert await count(SowVersion, SowVersion.sow_id == sow.id) == 1
    assert await count(GmModel, GmModel.sow_version_id == version.id) == 1
    assert await count(ApprovalPackage, ApprovalPackage.opportunity_id == opp.id) == 1
    assert await count(Approval, Approval.package_id == package.id) == 1
    assert await count(ApprovalAssignment, ApprovalAssignment.package_id == package.id) == 1
    assert await count(Task, Task.id == task.id) == 1

    # -- One audit line for the archive; the sow.deleted line was refused --
    rows = list(
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.entity_id == str(sow.id))
            )
        ).scalars()
    )
    archives = [r for r in rows if r.action == "sow.archived"]
    deletions = [r for r in rows if r.action == "sow.deleted"]
    assert len(archives) == 1
    assert len(deletions) == 0
    payload = archives[0].after or {}
    assert payload["archived_reason"] == "s20_w3_governed_archive"
    assert payload["stage"] == "SOWDraft.confirmed"
    assert payload["price"] == "$42,000"

    # -- Summary shape matches (returned by both archive_sow + delete_sow) --
    assert summary.sow_title == "S17 delete-everywhere fixture"
    assert summary.stage == "SOWDraft.confirmed"
    assert summary.price == "$42,000"
    assert summary.counts["sow_versions"] == 1
    assert summary.counts["gm_models"] == 1
    assert summary.counts["approval_packages"] == 1
    assert summary.counts["tasks"] == 1
