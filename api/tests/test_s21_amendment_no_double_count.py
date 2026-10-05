"""S21F:T20.08 — an activated amendment stops the original being counted.

When an amendment supersedes the original signed SOW version, the
signed outlook must carry only the amendment's schedule. Counting both
would book the full original contract again as extension revenue
(S21-16: "never count the full original contract again"). The same
exclusion applies to a package that was itself superseded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.sow import SowVersion
from app.services.commercial_models import COMPONENT, save_commercial_model
from app.services.forecast_plans import outlook
from tests.test_s21_forecast_plans_independent import (  # noqa: F401
    AS_OF,
    actor,
    component,
    isolated_scope,
    seed,
    signed_source,
)


async def _amendment(session, user, gm1, *, revenue="600", cost="300"):
    """Second confirmed version on the same Sow with its own released GM."""

    original = await session.get(SowVersion, gm1.sow_version_id)
    v2 = SowVersion(
        id=uuid.uuid4(),
        sow_id=gm1.sow_id,
        uploaded_by=user.id,
        file_s3_key=f"sow/amendment-{uuid.uuid4().hex[:8]}.pdf",
        file_hash=uuid.uuid4().hex * 2,
        extract_status="complete",
        extracted_fields={},
        confirmed_by=user.id,
        confirmed_at=datetime.now(UTC),
        version_no=original.version_no + 1,
    )
    session.add(v2)
    await session.flush()
    inputs = component(
        revenue, cost, source_id=str(gm1.sow_id), source_version=str(v2.id)
    )
    gm2 = await save_commercial_model(
        session,
        opportunity_id=gm1.opportunity_id,
        actor_id=user.id,
        sow_version_id=v2.id,
        expected_gm_model_id=gm1.id,
        inputs=COMPONENT.dump_python(inputs, mode="json"),
        change_reason="Signed extension recalculates the changed period",
    )
    session.add(
        ApprovalPackage(
            id=uuid.uuid4(),
            opportunity_id=gm1.opportunity_id,
            sow_version_id=v2.id,
            gm_model_id=gm2.id,
            package_hash="b" * 64,
            status="released",
            submitted_by=user.id,
        )
    )
    await session.commit()
    return original, v2, gm2


@pytest.mark.asyncio
async def test_superseded_original_version_is_not_counted(session):
    user, deal = await seed(session)
    gm1, _ = await signed_source(session, user, deal.client_id, revenue="400", cost="200")

    before = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert before["future"]["revenue"] == Decimal("400")

    original, _, gm2 = await _amendment(session, user, gm1)

    # Activation supersedes the original version; only the amendment counts.
    original.superseded_by = (await session.get(SowVersion, gm2.sow_version_id)).id
    await session.commit()

    after = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert after["future"]["revenue"] == Decimal("600")
    source_ids = {row["source_id"] for row in after["rows"]}
    assert str(gm2.id) in source_ids
    assert str(gm1.id) not in source_ids


@pytest.mark.asyncio
async def test_superseded_package_is_not_counted(session):
    user, deal = await seed(session)
    gm1, package1 = await signed_source(
        session, user, deal.client_id, revenue="400", cost="200"
    )
    _, _, gm2 = await _amendment(session, user, gm1)

    package2 = await session.scalar(
        select(ApprovalPackage).where(ApprovalPackage.gm_model_id == gm2.id)
    )
    package1.superseded_by = package2.id
    await session.commit()

    after = await outlook(session, actor=actor(user), as_of=AS_OF)
    assert after["future"]["revenue"] == Decimal("600")
    source_ids = {row["source_id"] for row in after["rows"]}
    assert source_ids == {str(gm2.id)}
