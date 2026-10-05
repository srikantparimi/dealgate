"""Cached source/owner state must not defeat transaction-bound review guards."""
# Imported pytest fixtures intentionally share parameter names.
# ruff: noqa: F811
import copy

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select, update

from app.models.opportunity import Opportunity
from app.models.sow import SowVersion
from app.services.sow_confirmation import build_confirmation, submit_confirmation
from app.services.sow_extract import SowSubmissionIncomplete, submit_sow
from tests.test_s21_extraction_conflicts import client_for, conflicting
from tests.test_s21_extraction_overrides import source  # noqa: F401
from tests.test_sow_confirmation import OWNER, seeded_sow  # noqa: F401


async def test_scope_builder_does_not_commit_callers_transaction(session, seeded_sow):
    commits = []

    def committed(_):
        commits.append(True)

    event.listen(session.sync_session, "after_commit", committed)
    try:
        payload = await build_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
        assert payload.gm_model is not None
        assert commits == [], "Auto-GM must not release the source lock before confirmation"
    finally:
        event.remove(session.sync_session, "after_commit", committed)


@pytest.mark.parametrize("legacy", [False, True])
async def test_submit_refreshes_cached_source_before_checking_conflicts(session, seeded_sow, legacy):
    version = await session.scalar(select(SowVersion))
    fields = copy.deepcopy(version.extracted_fields)
    fields["metadata"] = {"reextract_conflicts": {"price": {
        "value": "999.00", "status": "unconfirmed", "provenance": "extracted", "page_ref": 2}}}
    await session.execute(update(SowVersion).where(SowVersion.id == version.id)
        .values(extracted_fields=fields).execution_options(synchronize_session=False))
    assert not (version.extracted_fields.get("metadata") or {}).get("reextract_conflicts")
    if legacy:
        with pytest.raises(SowSubmissionIncomplete) as error:
            await submit_sow(session, actor_id=OWNER, sow_version_id=version.id)
        assert "extraction_conflict:price" in error.value.missing
    else:
        with pytest.raises(HTTPException, match="extraction_conflict:price"):
            await submit_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
    assert version.confirmed_at is None


async def test_review_authorization_refreshes_owner_before_mutating(session, source):
    owner, deal, version = source
    path = await conflicting(session, version)
    async with client_for(session, owner) as client:
        listing = await client.get(path)
        assert listing.status_code == 200
        token = listing.json()["items"][0]["review_token"]
        await session.execute(update(Opportunity).where(Opportunity.id == deal.id)
            .values(owner_id=None).execution_options(synchronize_session=False))
        assert deal.owner_id == owner.id
        response = await client.post(f"{path}/price", json={"review_token": token,
            "decision": "accept_candidate", "reason": "Old owner must no longer edit"})
        assert response.status_code == 403, response.text
    await session.refresh(version)
    assert version.extracted_fields["price"]["value"] == "250.00"


async def test_legacy_upload_reserves_monotonic_version_numbers(session, source):
    from app.services.sow_extract import create_sow_version

    owner, deal, _ = source
    second = await create_sow_version(session, opportunity_id=deal.id, uploaded_by=owner.id,
        file_s3_key="synthetic/second.docx", file_hash="second-source")
    version = await session.get(SowVersion, second.id)
    assert version.version_no == 2
    await session.delete(version)
    await session.flush()
    third = await create_sow_version(session, opportunity_id=deal.id, uploaded_by=owner.id,
        file_s3_key="synthetic/third.docx", file_hash="third-source")
    assert (await session.get(SowVersion, third.id)).version_no == 3
