"""GM computation from the sample_client_a.xlsx fixture.

The fixture ships three resource lines (see fixtures/legacy_projects/_build.py):

* US Senior Data Engineer — 100h @ $200 bill, $120 cost   → GM 40.00%
* India Backend           — 100h @ $80 bill,  $30 cost    → GM 62.50%
* India Junior QA         —  50h @ $50 bill,  $20 cost    → GM 60.00%

Component roll-ups (hand-computed):

* US    — revenue 20,000.00 / cost 12,000.00 → GM 40.00%
* India — revenue 10,500.00 / cost  4,000.00 → GM 61.90476190...%

The pilot reconciliation reports these numbers verbatim (rounded only for
display); the assertions below compare unrounded ``Decimal`` values.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio

from app.models.user import User
from app.services.legacy_import import (
    SowUpload,
    bulk_upload_sows,
    create_batch,
    import_excel,
    reconcile,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "legacy_projects"
    / "sample_client_a.xlsx"
)


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest_asyncio.fixture
async def finance_user(session):
    u = User(
        id=_uid("finance@smartek21.com"),
        email="finance@smartek21.com",
        name="Finance User",
        groups=["Finance"],
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_sample_client_a_gm_matches_hand_computation(session, finance_user):
    assert FIXTURE.exists(), (
        f"missing fixture {FIXTURE} — run fixtures/legacy_projects/_build.py"
    )

    batch = await create_batch(session, actor_id=finance_user.id)
    await bulk_upload_sows(
        session,
        actor_id=finance_user.id,
        batch=batch,
        uploads=[
            SowUpload(
                s3_key="sow/acme/2026-03.pdf",
                filename="acme-2026-03.pdf",
                sow_ref="SOW-Client-A-2026-03",
                client_name="Acme Widgets, Inc.",
            )
        ],
    )
    await import_excel(
        session,
        actor_id=finance_user.id,
        batch=batch,
        xlsx_bytes=FIXTURE.read_bytes(),
    )

    report = await reconcile(session, batch.id)
    assert len(report.project_gm) == 1
    snap = report.project_gm[0]

    # US component
    assert snap.revenue_us == Decimal("20000")
    assert snap.cost_us == Decimal("12000")
    assert snap.gm_us is not None
    assert snap.gm_us == (Decimal("20000") - Decimal("12000")) / Decimal("20000")
    assert snap.gm_us == Decimal("0.4")

    # India component
    assert snap.revenue_india == Decimal("10500")
    assert snap.cost_india == Decimal("4000")
    assert snap.gm_india is not None
    expected_india = (Decimal("10500") - Decimal("4000")) / Decimal("10500")
    assert snap.gm_india == expected_india

    # US at 40% is below the 35% floor? No — 0.40 >= 0.35, so US passes.
    # India at 61.9% is above the 50% floor. Neither component fails.
    assert snap.below_floor is False
    assert snap.failing == []
