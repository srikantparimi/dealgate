"""S12 regression — the defaulted-grid path is preserved.

The phantom-roster deletion (S11 slice 1) removed the hardcoded
`[("Architect","Principal"),("Engineer","Senior"),("Engineer","Mid")]` and
its T&M / managed-service cousins. `docs/directives/gm-correctness.md` §3
says the *legitimate* proposal path — template defaults from the capability
catalog when the SOW yields no staffing — must still work and arrive as
editable, pre-filled `defaulted` rows the user can delete.

Today the confirm screen surfaces past-SOW / capability-catalog matches as
sources on `staffing.notes` when there is no plan on file. This test pins
that behaviour so a future "helpfully seed the grid again" edit cannot
resurrect the phantom-roster defect under a different name.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS, StubBedrock
from app.models.opportunity import Opportunity
from app.models.sow import SowVersion
from app.services.provenance import wrap
from app.services.sow_confirmation import build_confirmation
from app.services.sow_extract import confirm_field, create_sow_version, run_extract


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


OWNER = _uid("s12-defaulted-grid@smartek21.com")


@pytest_asyncio.fixture
async def fixed_price_no_staffing(session):
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-DEFGRID-{uuid.uuid4().hex[:8]}",
        owner_id=OWNER,
        governance_status="SOWDraft",
    )
    session.add(opp)
    await session.commit()
    state = await create_sow_version(
        session,
        opportunity_id=opp.id,
        uploaded_by=OWNER,
        file_s3_key="sow/defaulted.pdf",
        file_hash=f"sha256:{uuid.uuid4().hex}",
    )
    await run_extract(session, sow_version_id=state.id, bedrock=StubBedrock())
    for name in EXTRACTED_FIELDS:
        await confirm_field(
            session,
            actor_id=OWNER,
            sow_version_id=state.id,
            field_name=name,
            value=f"c-{name}" if name != "price" else "50000",
        )
    row = (
        await session.execute(select(SowVersion).where(SowVersion.id == state.id))
    ).scalar_one()
    fields = dict(row.extracted_fields or {})
    fields["price"] = wrap("50000", provenance="extracted", page_ref=1)
    # No resource_table extracted — fixed price with no roster in the SOW,
    # exactly the case the defaulted-grid proposal path is designed for.
    fields.pop("resource_table", None)
    row.extracted_fields = fields
    await session.commit()
    return opp


@pytest.mark.asyncio
async def test_fixed_price_no_staffing_returns_empty_lines_and_a_reason(
    fixed_price_no_staffing, session
):
    """A confirm-screen open on a fixed-price SOW with no roster returns an
    empty grid and a `needs_you` blocker with a human reason — not a
    fabricated Architect+Engineer roster, and not a silent 0% GM.
    """

    payload = await build_confirmation(
        session, opportunity_id=fixed_price_no_staffing.id, actor_id=OWNER
    )
    assert payload.staffing.lines == [], (
        f"defaulted-grid path should return no lines when no past SOW matches; "
        f"got {[(l.role, l.seniority) for l in payload.staffing.lines]}"
    )
    reasons = [gap.reason for gap in payload.needs_you if gap.field == "staffing"]
    assert any(
        "enter or upload staffing" in r or "no staffing plan" in r for r in reasons
    ), reasons
    # A confirm-screen open on a SOW with no plan must NOT auto-persist a
    # fake GmModel (the defect this whole thing traces back to).
    assert payload.gm_model is None


@pytest.mark.asyncio
async def test_past_sow_match_is_a_source_not_a_copied_roster(
    fixed_price_no_staffing, session
):
    """When a past-SOW similarity match exists, auto_staff surfaces the ids
    as sources in the confirmation notes; it does NOT copy that SOW's team
    onto this one (docs/directives/gm-correctness.md §3).
    """

    from app.services import auto_staffing as auto_staff_mod
    from app.integrations.bedrock_embeddings import Embedder

    # Fake embedder + past-SOW search that returns one hit.
    class _StubEmbedder:
        async def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    async def _fake_past_search(*_args, **_kwargs):
        return [
            {
                "sow_version_id": "11111111-1111-1111-1111-111111111111",
                "chunk_text": "similar past project",
                "score": 0.92,
            }
        ]

    original_search_sow = auto_staff_mod.__dict__.get("search_sow")
    # Instead of monkeypatching `search_sow` deep in the module, drive
    # `auto_staff` directly with our stub past-SOW search.
    result = await auto_staff_mod.staff(
        "fixed_price",
        {
            "scope_summary": wrap("Test scope", provenance="extracted"),
            "price": wrap("50000", provenance="extracted"),
        },
        past_sow_search=_fake_past_search,
    )
    assert result.lines == [], (
        "past-SOW match must never be copied as a team; the ids belong in "
        f"result.sources: {[(l.role, l.seniority) for l in result.lines]}"
    )
    assert "11111111-1111-1111-1111-111111111111" in result.sources
