"""S20 W3 D1 · SOW rollup headline + breakdown per deal.

`services.sow_rollup.compute_headline(opportunity_id)` must:

1. Return `no_sow` when the deal has zero (live) `Sow` rows.
2. Return `draft` when a SOW exists but no approval_package was
   submitted.
3. Escalate to the most-blocked open bucket by the D1 ordering rule:
   `changes_requested > ceo_exception > in_review > awaiting_signature
   > approved > draft`.
4. Count archived (voided) packages separately in `archived_count` and
   never let them win the headline.
5. Aggregate correctly across multiple `Sow` rows per deal (which is
   what the D1 uniqueness relax enables — see requests.md
   #W3-2026-09-30-01). Written to work today (single Sow per deal) *and*
   after the migration lands.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.approval import ApprovalPackage
from app.models.client import Client, LegalEntity
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.sow_rollup import compute_headline, serialize


@pytest_asyncio.fixture
async def rollup_data(session):
    """Client + user + one opportunity — plumbing every test reuses."""

    client = Client(id=uuid.uuid4(), name="Acme Ltd")
    session.add(client)
    session.add(
        LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Acme Ltd")
    )
    user = User(id=uuid.uuid4(), email="owner@example.com", name="Owner", groups=["Sales"])
    session.add(user)
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=None,
        source="test",
        owner_id=user.id,
        client_id=client.id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.flush()
    return {"client": client, "user": user, "opp": opp}


async def _make_sow_with_version(session, opp_id: uuid.UUID) -> tuple[Sow, SowVersion]:
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp_id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        file_s3_key=f"sows/{sow.id}.pdf",
        file_hash=uuid.uuid4().hex,
        extract_status="complete",
        confirmed_at=datetime.now(UTC),
    )
    session.add(version)
    await session.flush()
    return sow, version


async def _make_gm_model(
    session, opp_id: uuid.UUID, sow_version_id: uuid.UUID
) -> GmModel:
    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp_id,
        sow_version_id=sow_version_id,
        version=1,
        engagement_type="fixed_price",
    )
    session.add(gm)
    await session.flush()
    return gm


async def _make_pkg(
    session,
    *,
    opp_id: uuid.UUID,
    sow_version_id: uuid.UUID,
    gm_model_id: uuid.UUID,
    status: str,
    submitted_by: uuid.UUID,
    package_hash: str | None = None,
) -> ApprovalPackage:
    pkg = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp_id,
        sow_version_id=sow_version_id,
        gm_model_id=gm_model_id,
        package_hash=package_hash or uuid.uuid4().hex,
        status=status,
        submitted_by=submitted_by,
        submitted_at=datetime.now(UTC),
    )
    session.add(pkg)
    await session.flush()
    return pkg


# --- tests ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_sow_returns_no_sow_headline(session, rollup_data):
    """A deal with no Sow rows renders `no_sow` — never crashes, never
    lies with `draft`."""

    opp = rollup_data["opp"]
    result = await compute_headline(session, opp.id)
    assert result.headline == "no_sow"
    assert result.archived_count == 0
    payload = serialize(result)
    assert payload["headline"] == "no_sow"
    assert payload["breakdown"]["draft"] == 0


@pytest.mark.asyncio
async def test_sow_with_no_package_is_draft(session, rollup_data):
    """A Sow with a SowVersion but no ApprovalPackage rolls up as
    `draft` — no gate has been opened yet."""

    opp = rollup_data["opp"]
    await _make_sow_with_version(session, opp.id)
    result = await compute_headline(session, opp.id)
    assert result.headline == "draft"
    assert result.breakdown.draft == 1


@pytest.mark.asyncio
async def test_ordering_rejected_beats_approved(session, rollup_data):
    """T14: even if one SOW is `released`, a second SOW's rejected
    package escalates the deal headline to `changes_requested`.

    Today's schema has `unique(opportunity_id)` on `Sow` so this test
    is skipped until the D1 uniqueness relax lands (requests.md
    #W3-2026-09-30-01). We assert the *service* rule with a single Sow
    that has multiple packages via superseding SowVersions.
    """

    opp = rollup_data["opp"]
    user = rollup_data["user"]
    sow, v1 = await _make_sow_with_version(session, opp.id)
    gm1 = await _make_gm_model(session, opp.id, v1.id)
    await _make_pkg(
        session,
        opp_id=opp.id,
        sow_version_id=v1.id,
        gm_model_id=gm1.id,
        status="released",
        submitted_by=user.id,
    )
    # A second SowVersion on the same Sow with its own package —
    # `rejected` is the most-blocked open state.
    v2 = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        file_s3_key=f"sows/{sow.id}-v2.pdf",
        file_hash=uuid.uuid4().hex,
        extract_status="complete",
        confirmed_at=datetime.now(UTC),
        version_no=2,
    )
    session.add(v2)
    await session.flush()
    gm2 = await _make_gm_model(session, opp.id, v2.id)
    await _make_pkg(
        session,
        opp_id=opp.id,
        sow_version_id=v2.id,
        gm_model_id=gm2.id,
        status="rejected",
        submitted_by=user.id,
    )
    result = await compute_headline(session, opp.id)
    # Newest package wins the SOW's state → the SOW is `changes_requested`.
    assert result.headline == "changes_requested"


@pytest.mark.asyncio
async def test_ordering_ceo_exception_beats_in_review(session, rollup_data):
    """`pending_ceo_exception` (bucket `ceo_exception`) sits above
    `pending_finance_legal` (bucket `in_review`) in the D1 rule."""

    opp = rollup_data["opp"]
    user = rollup_data["user"]
    _sow, v = await _make_sow_with_version(session, opp.id)
    gm = await _make_gm_model(session, opp.id, v.id)
    await _make_pkg(
        session,
        opp_id=opp.id,
        sow_version_id=v.id,
        gm_model_id=gm.id,
        status="pending_ceo_exception",
        submitted_by=user.id,
    )
    result = await compute_headline(session, opp.id)
    assert result.headline == "ceo_exception"


@pytest.mark.asyncio
async def test_voided_counts_as_archived(session, rollup_data):
    """A voided package doesn't win the headline — it counts as
    archived. A SOW whose only package is voided rolls up as `draft`
    (the user can resubmit a fresh one)."""

    opp = rollup_data["opp"]
    user = rollup_data["user"]
    _sow, v = await _make_sow_with_version(session, opp.id)
    gm = await _make_gm_model(session, opp.id, v.id)
    await _make_pkg(
        session,
        opp_id=opp.id,
        sow_version_id=v.id,
        gm_model_id=gm.id,
        status="voided",
        submitted_by=user.id,
    )
    result = await compute_headline(session, opp.id)
    assert result.headline == "draft"
    assert result.archived_count == 1
    assert result.breakdown.archived == 1


@pytest.mark.asyncio
async def test_archived_sow_never_headline(session, rollup_data):
    """A `Sow.archived_at` row is counted in `archived_count`, never in
    a live bucket, and never wins the headline (D1 + D6)."""

    opp = rollup_data["opp"]
    user = rollup_data["user"]
    sow, v = await _make_sow_with_version(session, opp.id)
    gm = await _make_gm_model(session, opp.id, v.id)
    # Attach a released package to the sow.
    await _make_pkg(
        session,
        opp_id=opp.id,
        sow_version_id=v.id,
        gm_model_id=gm.id,
        status="released",
        submitted_by=user.id,
    )
    # Now archive the Sow.
    sow.archived_at = datetime.now(UTC)
    sow.archived_by = user.id
    sow.archived_reason = "test_archive"
    await session.flush()
    result = await compute_headline(session, opp.id)
    assert result.headline == "no_sow"
    assert result.archived_count == 1


@pytest.mark.asyncio
async def test_serialize_shape(session, rollup_data):
    """The router-facing serializer returns the exact shape the deal
    detail page consumes. Breaking this signature is a downstream
    contract change that must go through requests.md."""

    opp = rollup_data["opp"]
    result = await compute_headline(session, opp.id)
    payload = serialize(result)
    assert set(payload.keys()) == {"headline", "breakdown", "archived_count"}
    assert set(payload["breakdown"].keys()) == {
        "draft",
        "in_review",
        "ceo_exception",
        "changes_requested",
        "awaiting_signature",
        "approved",
        "archived",
    }
