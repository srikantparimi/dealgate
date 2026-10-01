"""S20 W7 (T23) — release-gate pytest.

**The one contract this file exists to defend:**

> Release requires internal signoff + client execution + delivery
> acceptance. CRM Closed Won alone can never authorise release.

Test list — each mirrors a failure mode from the review (L15, T22, T23):

- ``test_release_ignores_closed_won`` — the whole point. Closed Won +
  verified upload but no delivery acceptance = 409. The regression
  fixture flips ``opportunity.is_closed_won=True`` to make sure the
  gate ignores it entirely.
- ``test_gate_lists_every_missing_event`` — the failure reasons must
  name each missing event.
- ``test_gate_requires_internal_signoff`` — Delivery approval missing
  → gate refuses.
- ``test_gate_requires_client_execution`` — upload with
  verify_status='blocked' (or unsigned) → gate refuses.
- ``test_gate_requires_delivery_acceptance`` — no acceptance row →
  gate refuses.
- ``test_gate_passes_when_all_three_land`` — happy path; release
  succeeds and audits ``handoff.gate_passed`` + ``project.created``.
- ``test_project_link_is_idempotent`` — running release a second time
  (via helper) finds the same project row and audits
  ``project.linked``.
- ``test_release_refuses_superseded_package`` — `superseded_by` set →
  409 even with the three events.
- ``test_unsigned_upload_rejected_400`` — T22: upload alone is not
  execution.
- ``test_declined_and_expired_transitions_audit`` — T22: declined /
  expired write dedicated audit lines and set the reason.
- ``test_ceo_closed_won_alone_is_still_refused`` — combined
  smoke check.

Uses SQLite via the shared ``session`` fixture (see ``conftest.py``).
Every audit line is asserted to keep W7's audit chain intact
(rule 5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.audit import verify_chain
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    EXTRACTED_FIELDS,
    ExtractedFields,
    ManualRequired,
)
from app.integrations.ses import StubSES
from app.models.approval import Approval, ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Client, LegalEntity
from app.models.delivery_acceptance import DeliveryAcceptance
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.delivery_acceptance import (
    DeliveryAcceptanceError,
    record as record_acceptance,
)
from app.services.handoff import check_release_gate
from app.services.project_lifecycle import create_or_link as create_or_link_project
from app.services.signed_sow import (
    SignedSowError,
    create_upload,
    latest_upload_for,
    mark_declined,
    mark_expired,
    release,
    verify,
)


# ---- fixtures ------------------------------------------------------------


APPROVED_PRICE = "500000.00"
APPROVED_TERM_START = "2027-01-01"
APPROVED_TERM_END = "2027-12-31"
APPROVED_SCOPE = "Deliver a cloud migration for the origination platform."


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _approved_fields() -> dict:
    fields: dict = {}
    for name in EXTRACTED_FIELDS:
        fields[name] = {"value": None, "page_ref": 1, "status": "confirmed"}
    fields["price"]["value"] = APPROVED_PRICE
    fields["term_start"]["value"] = APPROVED_TERM_START
    fields["term_end"]["value"] = APPROVED_TERM_END
    fields["scope_summary"]["value"] = APPROVED_SCOPE
    return fields


class _MatchBedrock(BedrockSowExtract):
    """Bedrock stub that always returns the approved terms verbatim."""

    def extract(self, file_bytes: bytes) -> ExtractedFields | ManualRequired:
        fields: dict[str, dict] = {}
        for name in EXTRACTED_FIELDS:
            fields[name] = {"value": None, "page_ref": 1, "status": "unconfirmed"}
        fields["price"]["value"] = APPROVED_PRICE
        fields["term_start"]["value"] = APPROVED_TERM_START
        fields["term_end"]["value"] = APPROVED_TERM_END
        fields["scope_summary"]["value"] = APPROVED_SCOPE
        return ExtractedFields(fields=fields)


async def _seed_user(session, email: str, groups: list[str]) -> User:
    u = User(id=_uid(email), email=email, name=email.split("@")[0], groups=groups)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _seed_package(session, owner: User) -> tuple[ApprovalPackage, Opportunity]:
    """Minimal ready-to-sign package with pinned approved fields."""

    client = Client(
        id=uuid.uuid4(),
        name=f"Release-gate client {uuid.uuid4().hex[:6]}",
        hubspot_company_id=f"HS-RG-{uuid.uuid4().hex[:6]}",
    )
    session.add(client)
    await session.flush()
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Entity"))
    await session.flush()

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-RG-{uuid.uuid4().hex[:6]}",
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
        file_hash="deadbeef" * 8,
        extract_status="complete",
        extracted_fields=_approved_fields(),
        confirmed_by=owner.id,
        confirmed_at=datetime.now(UTC),
    )
    session.add(version)
    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        engagement_type="fixed_price",
        delivery_pattern="us_only",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        revenue_us=Decimal(APPROVED_PRICE),
        revenue_india=Decimal("0"),
        created_by=owner.id,
    )
    session.add(gm)
    await session.flush()

    package = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        gm_model_id=gm.id,
        package_hash="a" * 64,
        status="ready_to_sign",
        submitted_by=owner.id,
    )
    session.add(package)
    await session.commit()
    await session.refresh(package)
    await session.refresh(opp)
    return package, opp


async def _seed_internal_signoff(
    session, package: ApprovalPackage, delivery_user: User
) -> None:
    session.add(
        Approval(
            id=uuid.uuid4(),
            package_id=package.id,
            function="delivery",
            approver_id=delivery_user.id,
            decision="approve",
            reason="internal signoff",
        )
    )
    await session.commit()


async def _seed_verified_upload(
    session, package: ApprovalPackage, owner: User
) -> SignedSowUpload:
    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key=f"sow/signed/{uuid.uuid4()}.pdf",
        file_hash=f"sha256:{uuid.uuid4().hex}",
    )
    return await verify(
        session, actor_id=owner.id, upload_id=upload.id, bedrock=_MatchBedrock()
    )


async def _seed_delivery_acceptance(
    session, package: ApprovalPackage, delivery_user: User
) -> DeliveryAcceptance:
    return await record_acceptance(
        session,
        actor_id=delivery_user.id,
        package_id=package.id,
        notes="ready for delivery",
        staffing_confirmed=True,
        billing_setup_confirmed=True,
        po_confirmed=True,
    )


async def _count_audits(session, action: str) -> int:
    rows = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalars().all()
    return len(list(rows))


# ---- T23: CRM Closed Won is not a release signal -----------------------


async def test_release_ignores_closed_won(session):
    """The single non-negotiable check: Closed Won alone cannot release.

    Given a Closed Won opportunity with a verified executed pdf, but
    NO internal signoff and NO delivery acceptance — the release must
    still refuse with 409. This test would fail if any code path in
    `services.release` (or its dependencies) reads
    `Opportunity.is_closed_won` as a release authority.
    """

    owner = await _seed_user(session, "cw-owner@smartek21.com", ["Sales"])
    package, opp = await _seed_package(session, owner)

    # Flip the CRM flag — the gate must not care.
    opp.is_closed_won = True
    await session.commit()

    # Verified upload lands.
    upload = await _seed_verified_upload(session, package, owner)
    assert upload.verify_status == "verified"

    # NO internal signoff, NO delivery acceptance.
    ses = StubSES()
    with pytest.raises(SignedSowError) as exc:
        await release(session, actor_id=owner.id, upload_id=upload.id, ses=ses)
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["error"] == "release_gate_not_met"
    assert detail["gate"]["checks"]["internal_signoff"] is False
    assert detail["gate"]["checks"]["delivery_acceptance"] is False
    assert detail["gate"]["checks"]["client_execution"] is True
    # Nothing was sent.
    assert ses.sent == []
    # Refusal is audited.
    assert await _count_audits(session, "handoff.gate_refused") == 1
    assert await _count_audits(session, "signed_sow.released") == 0
    # No project row was created.
    projects = (await session.execute(select(Project))).scalars().all()
    assert list(projects) == []


async def test_gate_lists_every_missing_event(session):
    """The gate result names each missing event by role."""

    owner = await _seed_user(session, "gate-empty@smartek21.com", ["Sales"])
    package, _ = await _seed_package(session, owner)
    gate = await check_release_gate(session, package)
    assert gate.ok is False
    assert gate.internal_signoff_ok is False
    assert gate.client_execution_ok is False
    assert gate.delivery_acceptance_ok is False
    # Reasons name each specifically.
    joined = " || ".join(gate.reasons)
    assert "internal_signoff" in joined
    assert "client_execution" in joined
    assert "delivery_acceptance" in joined


async def test_gate_requires_internal_signoff(session):
    owner = await _seed_user(session, "sig-only@smartek21.com", ["Sales"])
    delivery = await _seed_user(session, "delivery-a@smartek21.com", ["Delivery"])
    package, _ = await _seed_package(session, owner)

    # Verified upload + delivery acceptance, but no signoff.
    await _seed_verified_upload(session, package, owner)
    await _seed_delivery_acceptance(session, package, delivery)
    gate = await check_release_gate(session, package)
    assert gate.internal_signoff_ok is False
    assert gate.client_execution_ok is True
    assert gate.delivery_acceptance_ok is True
    assert gate.ok is False


async def test_gate_requires_client_execution(session):
    owner = await _seed_user(session, "exec-only@smartek21.com", ["Sales"])
    delivery = await _seed_user(session, "delivery-b@smartek21.com", ["Delivery"])
    package, _ = await _seed_package(session, owner)

    # Signoff + acceptance, but no verified upload.
    await _seed_internal_signoff(session, package, delivery)
    await _seed_delivery_acceptance(session, package, delivery)
    gate = await check_release_gate(session, package)
    assert gate.internal_signoff_ok is True
    assert gate.client_execution_ok is False
    assert gate.delivery_acceptance_ok is True
    assert gate.ok is False


async def test_gate_requires_delivery_acceptance(session):
    owner = await _seed_user(session, "accept-only@smartek21.com", ["Sales"])
    delivery = await _seed_user(session, "delivery-c@smartek21.com", ["Delivery"])
    package, _ = await _seed_package(session, owner)

    await _seed_internal_signoff(session, package, delivery)
    await _seed_verified_upload(session, package, owner)
    gate = await check_release_gate(session, package)
    assert gate.internal_signoff_ok is True
    assert gate.client_execution_ok is True
    assert gate.delivery_acceptance_ok is False
    assert gate.ok is False


async def test_gate_passes_when_all_three_land(session):
    owner = await _seed_user(session, "happy-owner@smartek21.com", ["Sales"])
    delivery = await _seed_user(session, "delivery-h@smartek21.com", ["Delivery"])
    package, _ = await _seed_package(session, owner)

    await _seed_internal_signoff(session, package, delivery)
    upload = await _seed_verified_upload(session, package, owner)
    await _seed_delivery_acceptance(session, package, delivery)

    gate = await check_release_gate(session, package)
    assert gate.ok is True

    ses = StubSES()
    result = await release(session, actor_id=owner.id, upload_id=upload.id, ses=ses)
    assert result.released_at is not None
    # Project row now exists and its baseline is frozen.
    projects = list((await session.execute(select(Project))).scalars().all())
    assert len(projects) == 1
    assert projects[0].baseline_snapshot_json["price"] == APPROVED_PRICE
    # Named audit lines are present.
    assert await _count_audits(session, "handoff.gate_passed") == 1
    assert await _count_audits(session, "project.created") == 1
    assert await _count_audits(session, "signed_sow.released") == 1
    assert await verify_chain(session) is True


async def test_project_link_is_idempotent(session):
    owner = await _seed_user(session, "idempotent@smartek21.com", ["Sales"])
    delivery = await _seed_user(session, "delivery-i@smartek21.com", ["Delivery"])
    package, _ = await _seed_package(session, owner)

    await _seed_internal_signoff(session, package, delivery)
    upload = await _seed_verified_upload(session, package, owner)
    await _seed_delivery_acceptance(session, package, delivery)

    # First call — creates.
    project_a, created_a = await create_or_link_project(
        session, actor_id=owner.id, package=package
    )
    await session.commit()
    assert created_a is True
    # Second call — links, does not create.
    project_b, created_b = await create_or_link_project(
        session, actor_id=owner.id, package=package
    )
    await session.commit()
    assert created_b is False
    assert project_b.id == project_a.id
    # Only one project row exists for this package.
    rows = list((await session.execute(select(Project))).scalars().all())
    assert len(rows) == 1
    assert await _count_audits(session, "project.created") == 1
    assert await _count_audits(session, "project.linked") == 1


async def test_release_refuses_superseded_package(session):
    owner = await _seed_user(session, "supers-owner@smartek21.com", ["Sales"])
    delivery = await _seed_user(session, "delivery-s@smartek21.com", ["Delivery"])
    package, _ = await _seed_package(session, owner)

    await _seed_internal_signoff(session, package, delivery)
    upload = await _seed_verified_upload(session, package, owner)
    await _seed_delivery_acceptance(session, package, delivery)

    # Mark the package as superseded — a stale UI must not be able to
    # release it.
    package.superseded_by = uuid.uuid4()
    await session.commit()

    ses = StubSES()
    with pytest.raises(SignedSowError) as exc:
        await release(session, actor_id=owner.id, upload_id=upload.id, ses=ses)
    assert exc.value.status_code == 409
    assert exc.value.detail["gate"]["checks"]["not_superseded"] is False


# ---- T22: signature transitions ----------------------------------------


async def test_unsigned_upload_rejected_400(session):
    owner = await _seed_user(session, "unsigned@smartek21.com", ["Sales"])
    package, _ = await _seed_package(session, owner)

    with pytest.raises(SignedSowError) as exc:
        await create_upload(
            session,
            actor_id=owner.id,
            package_id=package.id,
            file_s3_key="sow/nofile.pdf",
            file_hash="sha256:nosig",
            has_signature_evidence=False,
        )
    assert exc.value.status_code == 400
    # No row created.
    rows = list((await session.execute(select(SignedSowUpload))).scalars().all())
    assert rows == []


async def test_declined_and_expired_transitions_audit(session):
    owner = await _seed_user(session, "decex@smartek21.com", ["Sales"])
    package, _ = await _seed_package(session, owner)

    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/sent.pdf",
        file_hash="sha256:sent",
    )

    # Decline first — separate status + audit action.
    declined = await mark_declined(
        session, actor_id=owner.id, upload_id=upload.id, reason="signer refused"
    )
    assert declined.verify_status == "declined"
    assert declined.signer_state == "declined"
    assert "declined_by_signer" in (declined.verify_reason or "")
    assert declined.verified_at is None
    assert await _count_audits(session, "signed_sow.declined") == 1

    # Expire a fresh upload — separate status + audit action.
    upload2 = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/sent-2.pdf",
        file_hash="sha256:sent2",
    )
    expired = await mark_expired(
        session,
        actor_id=owner.id,
        upload_id=upload2.id,
        reason="timeout",
    )
    assert expired.verify_status == "expired"
    assert expired.signer_state == "expired"
    assert "signature_request_expired" in (expired.verify_reason or "")
    assert await _count_audits(session, "signed_sow.expired") == 1


# ---- T23: delivery_acceptance role gate --------------------------------


async def test_delivery_acceptance_requires_delivery_role(session):
    owner = await _seed_user(session, "not-delivery@smartek21.com", ["Sales"])
    package, _ = await _seed_package(session, owner)

    # Owner is Sales — cannot file the acceptance record.
    with pytest.raises(DeliveryAcceptanceError) as exc:
        await record_acceptance(
            session,
            actor_id=owner.id,
            package_id=package.id,
        )
    assert exc.value.status_code == 403


async def test_delivery_acceptance_is_set_once(session):
    owner = await _seed_user(session, "twice-owner@smartek21.com", ["Sales"])
    delivery = await _seed_user(session, "delivery-t@smartek21.com", ["Delivery"])
    package, _ = await _seed_package(session, owner)

    await _seed_delivery_acceptance(session, package, delivery)
    with pytest.raises(DeliveryAcceptanceError) as exc:
        await record_acceptance(
            session, actor_id=delivery.id, package_id=package.id
        )
    assert exc.value.status_code == 409


# ---- Combined: closed_won + verified upload is still refused -----------


async def test_ceo_closed_won_alone_is_still_refused(session):
    """The whole-arc regression: even 'CRM says won' + verified pdf is not
    enough. Missing internal signoff / acceptance = 409. This is the T23
    contract restated at the release entrypoint."""

    owner = await _seed_user(session, "combo@smartek21.com", ["Sales", "CEO"])
    package, opp = await _seed_package(session, owner)
    opp.is_closed_won = True
    opp.is_closed_lost = False
    await session.commit()

    upload = await _seed_verified_upload(session, package, owner)
    ses = StubSES()
    with pytest.raises(SignedSowError) as exc:
        await release(session, actor_id=owner.id, upload_id=upload.id, ses=ses)
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "release_gate_not_met"
    # No project, no distribution.
    assert (await session.execute(select(Project))).scalars().first() is None
    assert ses.sent == []
