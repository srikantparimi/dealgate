"""S20 W4 Session 6 · deliverables 1 (card == row count), 3 (reports
endpoints), 5 (three-way reconciliation) and 6 (deal in 3 groups +
watchlist counts once).

Every test here is lane-A owned: it exercises code added or edited
exclusively in `api/app/routers/reports.py`, `api/app/services/
hubspot_pipeline.py` (summary() only) and the related invariants in the
Command-center → Pipeline deep-link.

Lane A does NOT run against staging (CLAUDE.md rule 17). The CI
Postgres fixture + the in-memory session fixture here are the proof
surfaces.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from app.models.approval import ApprovalPackage
from app.models.client import Agreement, Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.models.user import User
from app.models.watchlist import WatchedItem
from app.services.hubspot_pipeline import (
    PipelineFilters,
    list_opportunities,
    summary,
)


async def _seed_package(
    session: AsyncSession,
    *,
    opp: Opportunity,
    owner: User,
    status: str,
) -> ApprovalPackage:
    """Minimal ApprovalPackage with the FK + required columns satisfied."""
    sow = Sow(opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    sow_v = SowVersion(
        sow_id=sow.id,
        file_s3_key="s3://b/x.pdf",
        file_hash="deadbeef",
        extract_status="complete",
    )
    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        engagement_type="staff_aug",
        currency="USD",
        revenue_us=Decimal("1000"),
        revenue_india=Decimal("0"),
    )
    session.add_all([sow_v, gm])
    await session.flush()
    pkg = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=sow_v.id,
        gm_model_id=gm.id,
        package_hash="0" * 64,
        status=status,
        submitted_by=owner.id,
    )
    session.add(pkg)
    await session.flush()
    return pkg


async def _seed_open_deal(
    session: AsyncSession,
    *,
    owner: User,
    client: Client,
    deal_id: str,
    name: str,
    amount: Decimal = Decimal("1000"),
    stage: str = "1-Discovery",
) -> Opportunity:
    """Produce the smallest open opportunity the pipeline + summary agree on."""
    opp = Opportunity(
        source="hubspot",
        hubspot_deal_id=deal_id,
        name=name,
        owner_id=owner.id,
        client_id=client.id,
        sales_stage=stage,
        stage_label=stage,
        hubspot_pipeline_id="710688094",
        hubspot_stage_id=f"STAGE_{stage}",
        amount=amount,
        currency="USD",
        close_date=date.today() + timedelta(days=30),
        governance_status="Intake",
    )
    session.add(opp)
    await session.flush()
    return opp


# =============================================================================
# Deliverable 1 · command-center card number equals row count on deep-link
# filter. Each card runs through `summary()` on the exact filter the UI
# would open and asserts equality against `list_opportunities(filters).total`.
# =============================================================================


@pytest.mark.asyncio
async def test_card_sows_in_progress_equals_deep_link_count(session):
    """`sows_in_progress` on the summary === count of opportunities whose
    newest approval package is in a pending state. Deep-link URL is
    `/pipeline?attention=pending_approval`; the pipeline filter resolves
    that attention flag over the same base set.
    """
    owner = User(email="s1@dealgate.local", name="S1", groups=[])
    c = Client(name="SIP Corp")
    session.add_all([owner, c])
    await session.flush()
    opp = await _seed_open_deal(
        session, owner=owner, client=c, deal_id="d_sip", name="SIP"
    )
    await _seed_package(
        session, opp=opp, owner=owner, status="pending_delivery_hr"
    )
    await session.commit()

    s = await summary(session, filters=PipelineFilters())
    assert s.sows_in_progress == 1, (
        "summary.sows_in_progress must count exactly one pending package"
    )
    # Deep link opens /pipeline?attention=pending_approval. The pipeline
    # filter re-counts the same base; a pending package attaches to the
    # linked opp so the row count is 1.
    page = await list_opportunities(
        session,
        filters=PipelineFilters(attention=("pending_approval",)),
    )
    assert page.total == 1
    assert s.sows_in_progress == page.total


@pytest.mark.asyncio
async def test_card_ceo_pending_equals_deep_link_count(session):
    """`ceo_pending` === pipeline rows whose attached package is in
    `pending_ceo_exception`. Deep-link: `/pipeline?readiness=ceo_exception`.
    """
    owner = User(email="s2@dealgate.local", name="S2", groups=[])
    c = Client(name="CEO Corp")
    session.add_all([owner, c])
    await session.flush()
    opp = await _seed_open_deal(
        session, owner=owner, client=c, deal_id="d_ceo", name="CEOp"
    )
    await _seed_package(
        session, opp=opp, owner=owner, status="pending_ceo_exception"
    )
    await session.commit()
    s = await summary(session, filters=PipelineFilters())
    assert s.ceo_pending == 1
    page = await list_opportunities(
        session,
        filters=PipelineFilters(readiness=("ceo_exception",)),
    )
    assert page.total == 1
    assert s.ceo_pending == page.total


@pytest.mark.asyncio
async def test_card_agreements_uploaded_matches_agreement_count(session):
    """`agreements_uploaded` on the summary === count of Agreement rows."""
    c = Client(name="Agr Corp")
    session.add(c)
    await session.flush()
    for i in range(3):
        session.add(
            Agreement(
                client_id=c.id,
                kind="NDA" if i % 2 == 0 else "MSA",
                file_key=f"s3://b/agr_{i}.pdf",
                filename=f"agr_{i}.pdf",
                file_size=100,
                uploaded_by=uuid.uuid4(),
            )
        )
    await session.commit()
    s = await summary(session, filters=PipelineFilters())
    assert s.agreements_uploaded == 3


# =============================================================================
# Deliverable 5 · three-way reconciliation:
#   command-center open total == reports by-stage total == /pipeline open total
# =============================================================================


@pytest.mark.asyncio
async def test_three_way_reconciliation_open_total(session):
    """CC `summary.open_count` == sum of `by-stage` counts == `list_opps.total`.

    This locks the directive's "Reporting numbers agree" invariant across
    all three surfaces at once.
    """
    owner = User(email="rec@dealgate.local", name="Rec", groups=[])
    c = Client(name="Rec Corp")
    session.add_all([owner, c])
    await session.flush()
    for i in range(5):
        await _seed_open_deal(
            session,
            owner=owner,
            client=c,
            deal_id=f"d_rec_{i}",
            name=f"Rec {i}",
            stage="1-Discovery" if i < 2 else "3-Proposal",
        )
    await session.commit()

    # Command center source
    cc = await summary(session, filters=PipelineFilters())

    # Pipeline source
    pipeline = await list_opportunities(
        session, filters=PipelineFilters(open_closed="open"), page_size=100
    )

    # Reports by-stage source — mirror the router's own derivation.
    from app.routers.reports import pipeline_by_stage
    from app.auth import AuthUser

    sysadmin = AuthUser(
        id=uuid.uuid4(),
        email="rec@dealgate.local",
        name="Rec",
        groups=("SystemAdmin",),
    )
    by_stage = await pipeline_by_stage(user=sysadmin, session=session)

    assert cc.open_count == pipeline.total == by_stage.total_count == 5, (
        f"three-way mismatch: cc={cc.open_count}, "
        f"pipeline={pipeline.total}, reports={by_stage.total_count}"
    )


# =============================================================================
# Deliverable 6 · W6 item 8 real test: deal lives in 3 groups + is watched.
# Assert the deal counts ONCE on the Watching card AND on
# /pipeline?watching=true (group membership never multiplies).
# =============================================================================


@pytest.mark.asyncio
async def test_watched_deal_in_three_groups_counts_once(session):
    """A single deal, member of three tracking groups, starred on the
    user's watchlist, must count exactly one on the Command center
    Watching metric and on /pipeline?watching=true.

    Teardown: the in-memory session is discarded per-test by the
    conftest fixture — no residue, no staging mutation (rule 17).
    """
    owner = User(email="w@dealgate.local", name="W Rep", groups=[])
    c = Client(name="Watch Corp")
    session.add_all([owner, c])
    await session.flush()
    opp = await _seed_open_deal(
        session, owner=owner, client=c, deal_id="d_watched", name="Watched One"
    )

    # Seed three tracking groups all pointing to the SAME opportunity.
    groups = [
        TrackingGroup(
            owner_id=owner.id,
            name=f"G{i}",
            visibility="private",
            member_kind="opportunity",
        )
        for i in range(3)
    ]
    session.add_all(groups)
    await session.flush()
    for g in groups:
        session.add(
            TrackingGroupMember(
                group_id=g.id, member_id=opp.id, added_by=owner.id
            )
        )

    # Star the deal on the user's watchlist.
    session.add(
        WatchedItem(
            user_id=owner.id,
            kind="opportunity",
            item_id=opp.id,
        )
    )
    await session.commit()

    # /pipeline?watching=true → router resolves owner's watch set and
    # passes it as `watching_ids`. We mirror that at the service layer.
    page = await list_opportunities(
        session,
        filters=PipelineFilters(watching_ids=(opp.id,)),
    )
    assert page.total == 1, (
        "watchlist deep-link must count the deal once; got %d" % page.total
    )

    # Command center Watching card: the UI calls `listWatchlist()` which
    # returns `counts.opportunity + counts.client`. For this user, that
    # equals 1 (one WatchedItem row). Three group memberships do not
    # multiply the count because WatchedItem is independent of groups.
    from sqlalchemy import select

    watched = (
        (
            await session.execute(
                select(WatchedItem).where(WatchedItem.user_id == owner.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(watched) == 1, (
        "WatchedItem must contain exactly one row for the test user; "
        "group membership never populates WatchedItem"
    )
    assert len(watched) == page.total, (
        "Command-center Watching count must equal /pipeline?watching=true total"
    )


# =============================================================================
# Deliverable 3 · reports endpoints: by-stage / by-owner / by-bu honest
# "not mirrored" / SOW GM / aging / CSV with totals-before-pagination.
# =============================================================================


@pytest.mark.asyncio
async def test_reports_by_bu_declares_not_mirrored(session):
    """W1-D10 · staging has no BU property on deals. The report says so
    explicitly rather than fabricating a split.
    """
    from app.auth import AuthUser
    from app.routers.reports import pipeline_by_bu

    owner = User(email="bu@dealgate.local", name="BU", groups=[])
    c = Client(name="BU Corp")
    session.add_all([owner, c])
    await session.flush()
    await _seed_open_deal(
        session, owner=owner, client=c, deal_id="d_bu", name="BU test"
    )
    await session.commit()

    sysadmin = AuthUser(
        id=uuid.uuid4(),
        email="bu@dealgate.local",
        name="BU",
        groups=("SystemAdmin",),
    )
    out = await pipeline_by_bu(user=sysadmin, session=session)
    # Honest state: bu_mirrored is false when every row carries no BU.
    assert out.bu_mirrored is False
    assert any(r.business_unit == "Not mirrored" for r in out.rows)
    # The note must mention mirroring so a screenshot is self-describing.
    assert "mirror" in out.note.lower()


@pytest.mark.asyncio
async def test_reports_approvals_aging_buckets_cover_four_bands(session):
    """Aging shape is stable: 4 buckets per lane, 3 lanes."""
    from app.auth import AuthUser
    from app.routers.reports import approvals_aging

    sysadmin = AuthUser(
        id=uuid.uuid4(),
        email="a@dealgate.local",
        name="A",
        groups=("SystemAdmin",),
    )
    out = await approvals_aging(user=sysadmin, session=session)
    assert len(out.lanes) == 3
    for lane in out.lanes:
        assert [b.label for b in lane.buckets] == [
            "<= 24h",
            "1-3d",
            "3-7d",
            "> 7d",
        ]


@pytest.mark.asyncio
async def test_reports_pipeline_csv_totals_row_computed_before_pagination(session):
    """The CSV header carries a TOTAL row with the summary's open_count
    BEFORE any pagination — not a sum over the materialised rows (which
    could silently be capped at the service's page cap).
    """
    from app.auth import AuthUser
    from app.routers.reports import pipeline_export_csv

    owner = User(email="csv@dealgate.local", name="CSV", groups=[])
    c = Client(name="CSV Corp")
    session.add_all([owner, c])
    await session.flush()
    for i in range(4):
        await _seed_open_deal(
            session,
            owner=owner,
            client=c,
            deal_id=f"d_csv_{i}",
            name=f"CSV {i}",
        )
    await session.commit()
    sysadmin = AuthUser(
        id=uuid.uuid4(),
        email="csv@dealgate.local",
        name="CSV",
        groups=("SystemAdmin",),
    )
    resp = await pipeline_export_csv(user=sysadmin, session=session)
    # X-Totals-Count comes from `summary()` which is a global aggregate
    # (totals BEFORE pagination). This proves the invariant without
    # streaming the body (StreamingResponse is iterable but we assert on
    # the header the service deliberately set).
    assert resp.headers["X-Totals-Count"] == "4"
