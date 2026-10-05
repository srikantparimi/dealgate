"""Missing document currency is a review gap, not a reporting-currency default."""
# Imported pytest fixtures intentionally share argument names.
# ruff: noqa: F811
import copy

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sow import SowVersion
from app.services.provenance import read
from app.services.sow_confirmation import build_confirmation, scope_blockers, submit_confirmation
from app.services.sow_extract import confirm_field
from tests.test_sow_confirmation import OWNER, seeded_sow  # noqa: F401


@pytest.mark.parametrize("entry", [None, {"value": None, "provenance": "extracted", "status": "disputed", "page_ref": 2},
    {"value": "USD", "provenance": "extracted", "status": "disputed", "page_ref": 2},
    {"value": "USD", "provenance": "defaulted", "source_id": "policy.house_currency", "status": "unconfirmed"}])
async def test_unresolved_currency_never_silently_becomes_confirmable_usd(session, seeded_sow, entry):
    version = await session.scalar(select(SowVersion))
    fields = copy.deepcopy(version.extracted_fields)
    fields["currency"] = entry
    version.extracted_fields = fields
    await session.commit()
    payload = await build_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
    assert read(version.extracted_fields["currency"])["value"] == read(entry)["value"]
    assert "currency" in {row.field for row in scope_blockers(payload)}
    with pytest.raises(HTTPException, match="currency") as error:
        await submit_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
    assert error.value.status_code == 422 and version.confirmed_at is None
    await confirm_field(session, actor_id=OWNER, sow_version_id=version.id, field_name="currency", value="CAD")
    payload = await build_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
    assert "currency" not in {row.field for row in scope_blockers(payload)}
    assert read(version.extracted_fields["currency"])["value"] == "CAD"


async def test_human_confirmed_prior_house_currency_is_not_rewritten(session, seeded_sow):
    version = await session.scalar(select(SowVersion))
    fields = copy.deepcopy(version.extracted_fields)
    confirmed = {"value": "USD", "provenance": "defaulted", "source_id": "policy.house_currency", "status": "confirmed"}
    fields["currency"] = confirmed
    version.extracted_fields = fields
    await session.commit()
    payload = await build_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
    assert version.extracted_fields["currency"] == confirmed
    assert "currency" not in {row.field for row in scope_blockers(payload)}
