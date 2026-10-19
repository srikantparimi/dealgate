"""T41 · signing is never held for an NDA or MSA (S20 · W5, replaced by S24-AG1 T10).

The S20 skeletons asked whether Signature lists NDA/MSA among its hold reasons. S17 removed the gate and
S24-AG1 confirms warn-only (directive "What Kanna decided" 3, B14 fixed blueprint.md:14): a missing NDA or MSA
is a flag, never a hold. These tests take the flagged net-new client of test_s20_nda_msa_rules.py through
approval to ``ready_to_sign`` and then through the real signing functions:

* ``approval_workflow.require_signature_eligibility`` (and the signed-SOW service's wrapper of it) passes;
* the signed SOW is uploaded through ``POST /signed-sow/{package_id}/file`` and registered by
  ``signed_sow.create_upload`` with no agreement on file;
* after the deal closes won, the client stays net new and flagged (a later win never makes it existing, so the
  warning is not lost at the moment it signs), signing is still eligible, and only the client's own copy or a
  mark clears the warning.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date

from sqlalchemy import select

from app.auth import AuthUser
from app.integrations.s3_evidence import StubS3 as AgreementStorage
from app.integrations.s3_evidence import get_evidence_s3
from app.integrations.s3_sow import StubS3 as SowStorage
from app.integrations.s3_sow import get_sow_s3
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.routers import signed_sow as signed_sow_routes
from app.services.approval_workflow import require_signature_eligibility
from app.services.signed_sow import _require_signature_eligibility, create_upload
from tests.test_s20_nda_msa_rules import (
    FLAGGED,
    STAGES,
    _local_env,  # noqa: F401  (an autouse fixture)
    api_for,
    nothing_on_file,
    ready_to_sign,
    warning_of,
)

SIGNED_PDF = b"%PDF-1.4\n% synthetic executed SOW for T10 (no real document)\n" + b"0" * 64


def _owner_token(seeded) -> AuthUser:
    owner = seeded.owner
    return AuthUser(owner.id, owner.email, owner.name, tuple(owner.groups))


async def test_signature_eligibility_passes_with_no_agreement_on_file(session):
    seeded, package = await ready_to_sign(session)
    assert await nothing_on_file(session, seeded.client_id)
    assert await warning_of(session, seeded) == FLAGGED  # flagged ...
    assert await require_signature_eligibility(session, package) is None  # ... and not held
    assert await _require_signature_eligibility(session, package) is None  # the signed-SOW service's own check
    assert await warning_of(session, seeded) == FLAGGED


async def test_the_signed_sow_is_uploaded_with_no_agreement_on_file(session):
    seeded, package = await ready_to_sign(session)
    storage = SowStorage()
    async with api_for(session, _owner_token(seeded), signed_sow_routes.router,
                       overrides={get_sow_s3: storage}) as api:
        response = await api.post(f"/signed-sow/{package.id}/file", data={"has_signature_evidence": "true"},
                                  files={"file": ("Halcyon SOW executed.pdf", SIGNED_PDF, "application/pdf")})
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["verify_status"], body["file_hash"]) == ("pending", hashlib.sha256(SIGNED_PDF).hexdigest())
    assert storage.put_calls == [(body["file_s3_key"], len(SIGNED_PDF), "application/pdf")]
    # The service path (a corrected scan registered by key) is not held either.
    again = await create_upload(session, actor_id=seeded.owner.id, package_id=package.id,
                                file_s3_key=f"sow/{uuid.uuid4()}/executed-v2.pdf", file_hash="ab" * 32)
    assert again.verify_status == "pending"
    uploads = (await session.scalars(select(SignedSowUpload).where(SignedSowUpload.package_id == package.id))).all()
    assert len(uploads) == 2
    assert await nothing_on_file(session, seeded.client_id)
    assert await warning_of(session, seeded) == FLAGGED


async def test_after_signing_and_winning_the_client_stays_net_new_and_flagged(session):
    seeded, package = await ready_to_sign(session)
    await create_upload(session, actor_id=seeded.owner.id, package_id=package.id,
                        file_s3_key=f"sow/{uuid.uuid4()}/executed.pdf", file_hash="cd" * 32)
    # The deal closes won (as the nightly HubSpot sync would record it after the signature).
    won_id, won_label, won_order, _closed = STAGES[6]
    await session.execute(Opportunity.__table__.update().where(Opportunity.id == seeded.opportunity_id).values(
        hubspot_stage_id=won_id, stage_label=won_label, sales_stage=won_label, stage_order=won_order,
        is_closed_won=True, close_date=date.today()))
    await session.commit()
    # A later win never turns a net-new client into an existing one: the warning is still there, and nothing
    # is held because of it.
    assert await warning_of(session, seeded) == FLAGGED
    assert await require_signature_eligibility(session, package) is None
    # Only the client's own copy or a mark clears it, one kind at a time.
    storage = AgreementStorage(bucket="stub-agreements-t10")
    async with api_for(session, seeded.legal, overrides={get_evidence_s3: storage}) as api:
        nda = await api.post(f"/clients/{seeded.client_id}/agreements/NDA/client-copy",
                             files={"file": ("Halcyon NDA.pdf", SIGNED_PDF, "application/pdf")})
        assert nda.status_code == 201, nda.text
        half = await warning_of(session, seeded)
        assert (half["nda"], half["msa"], half["needs_attention"], half["missing_kinds"], half["count"]) == (
            "client", "missing", True, ["MSA"], 1)
        msa = await api.put(f"/clients/{seeded.client_id}/agreements/MSA/mark",
                            json={"reason": "signed_outside_dealgate", "marked_on": date.today().isoformat()})
        assert msa.status_code == 200, msa.text
    cleared = await warning_of(session, seeded)
    assert (cleared["relationship"], cleared["nda"], cleared["msa"], cleared["needs_attention"], cleared["page"],
            cleared["count"]) == ("net_new", "client", "covered", False, [], 0)
