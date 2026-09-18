"""S6 E9 actuals CSV import — end-to-end vertical slice.

Acceptance tests mirrored from ``docs/backlog/s6-actuals-import.md``:

- Happy path: 5 rows imported, ``actual_period`` rows exist.
- Unknown ``resource_line_id`` -> whole-file reject with row #.
- Missing ``actual_cost`` -> whole-file reject (blueprint §2 hard rule).
- Re-import same (line, period) -> upsert.
- Non-Finance -> 403 on every endpoint.
- ``actual_gm_for`` returns correct aggregation for a 2-line 2-period test
  (sum-of-cost / sum-of-revenue, not mean of percentages).
"""

from __future__ import annotations

import io
import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.main import app as main_app
from app.models.actual import ActualImportBatch, ActualPeriod
from app.models.gm_model import GmModel, ResourceLine
from app.models.user import User
from app.services.actuals_import import (
    ActualsImportError,
    actual_gm_for,
    import_csv,
)


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def finance_user(session) -> User:
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


# ---- helpers ------------------------------------------------------------


async def _seed_gm(session) -> tuple[GmModel, list[ResourceLine]]:
    """Seed one GmModel with two resource lines (US + India)."""

    gm = GmModel(
        id=uuid.uuid4(), engagement_type="staff_aug", currency="USD"
    )
    session.add(gm)
    await session.flush()

    us_line = ResourceLine(
        id=uuid.uuid4(),
        gm_model_id=gm.id,
        role="Sr Engineer",
        seniority="senior",
        location="US",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        allocation_pct=Decimal("100"),
        billable_hours=Decimal("160"),
        hourly_bill_rate=Decimal("200"),
        hourly_loaded_cost=Decimal("120"),
    )
    india_line = ResourceLine(
        id=uuid.uuid4(),
        gm_model_id=gm.id,
        role="QA",
        seniority="mid",
        location="India",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        allocation_pct=Decimal("100"),
        billable_hours=Decimal("160"),
        hourly_bill_rate=Decimal("80"),
        hourly_loaded_cost=Decimal("30"),
    )
    session.add_all([us_line, india_line])
    await session.commit()
    await session.refresh(gm)
    await session.refresh(us_line)
    await session.refresh(india_line)
    return gm, [us_line, india_line]


def _csv(rows: list[dict]) -> bytes:
    header = "sow_ref,resource_line_id,period_month,actual_hours,actual_cost,actual_revenue"
    lines = [header]
    for r in rows:
        lines.append(
            ",".join(
                str(r.get(c, ""))
                for c in (
                    "sow_ref",
                    "resource_line_id",
                    "period_month",
                    "actual_hours",
                    "actual_cost",
                    "actual_revenue",
                )
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


# ---- role gating -------------------------------------------------------


async def test_non_finance_forbidden_on_all_endpoints(
    app_with_session, session, monkeypatch, finance_user
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    gm_id = uuid.uuid4()
    async with _client(app_with_session) as c:
        # POST /actuals/import
        r = await c.post(
            "/actuals/import",
            headers={"X-Test-User": "sales@x.com"},
            files={"file": ("x.csv", b"header\n", "text/csv")},
        )
        assert r.status_code == 403, r.text
        # GET /actuals/batches
        r = await c.get(
            "/actuals/batches", headers={"X-Test-User": "sales@x.com"}
        )
        assert r.status_code == 403, r.text
        # GET /actuals/batches/{id}
        r = await c.get(
            f"/actuals/batches/{uuid.uuid4()}",
            headers={"X-Test-User": "sales@x.com"},
        )
        assert r.status_code == 403, r.text
        # GET /actuals/gm-model/{id}
        r = await c.get(
            f"/actuals/gm-model/{gm_id}?period_month=2026-01",
            headers={"X-Test-User": "sales@x.com"},
        )
        assert r.status_code == 403, r.text


# ---- happy path --------------------------------------------------------


async def test_import_csv_happy_path_upserts_rows(session, finance_user):
    gm, lines = await _seed_gm(session)
    us, india = lines
    csv_bytes = _csv(
        [
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(us.id),
                "period_month": "2026-01",
                "actual_hours": "160",
                "actual_cost": "19200.00",
                "actual_revenue": "32000.00",
            },
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(india.id),
                "period_month": "2026-01",
                "actual_hours": "160",
                "actual_cost": "4800.00",
                "actual_revenue": "12800.00",
            },
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(us.id),
                "period_month": "2026-02",
                "actual_hours": "150",
                "actual_cost": "18000.00",
                "actual_revenue": "30000.00",
            },
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(india.id),
                "period_month": "2026-02",
                "actual_hours": "150",
                "actual_cost": "4500.00",
                "actual_revenue": "12000.00",
            },
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(us.id),
                "period_month": "2026-03",
                "actual_hours": "100",
                "actual_cost": "12000.00",
                "actual_revenue": "20000.00",
            },
        ]
    )
    batch = await import_csv(session, actor_id=finance_user.id, csv_bytes=csv_bytes)
    assert batch.status == "committed"
    assert batch.row_count == 5
    rows = (await session.execute(select(ActualPeriod))).scalars().all()
    assert len(list(rows)) == 5


# ---- unknown resource_line_id → whole-file reject ----------------------


async def test_unknown_resource_line_id_rejects_whole_file(
    session, finance_user
):
    gm, lines = await _seed_gm(session)
    good = lines[0]
    csv_bytes = _csv(
        [
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(good.id),
                "period_month": "2026-01",
                "actual_hours": "10",
                "actual_cost": "100.00",
                "actual_revenue": "200.00",
            },
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(uuid.uuid4()),
                "period_month": "2026-01",
                "actual_hours": "10",
                "actual_cost": "100.00",
                "actual_revenue": "200.00",
            },
        ]
    )
    with pytest.raises(ActualsImportError) as ei:
        await import_csv(session, actor_id=finance_user.id, csv_bytes=csv_bytes)
    rows_with_err = {e.get("row") for e in ei.value.errors}
    assert 3 in rows_with_err  # header=1, good=2, unknown=3
    cols = {e.get("column") for e in ei.value.errors}
    assert "resource_line_id" in cols
    # All-or-nothing: no ActualPeriod rows persisted.
    persisted = (await session.execute(select(ActualPeriod))).scalars().all()
    assert list(persisted) == []
    # Batch was recorded as failed with the report.
    batches = list(
        (await session.execute(select(ActualImportBatch))).scalars().all()
    )
    assert len(batches) == 1
    assert batches[0].status == "failed"
    assert batches[0].errors is not None


# ---- missing actual_cost → whole-file reject (§2) ----------------------


async def test_missing_actual_cost_rejects_whole_file(session, finance_user):
    gm, lines = await _seed_gm(session)
    line = lines[0]
    csv_bytes = _csv(
        [
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(line.id),
                "period_month": "2026-01",
                "actual_hours": "160",
                "actual_cost": "",  # missing → hard reject per §2
                "actual_revenue": "32000.00",
            }
        ]
    )
    with pytest.raises(ActualsImportError) as ei:
        await import_csv(session, actor_id=finance_user.id, csv_bytes=csv_bytes)
    cols = {e.get("column") for e in ei.value.errors}
    assert "actual_cost" in cols
    persisted = (await session.execute(select(ActualPeriod))).scalars().all()
    assert list(persisted) == []


# ---- re-import upserts -------------------------------------------------


async def test_reimport_same_period_line_upserts(session, finance_user):
    gm, lines = await _seed_gm(session)
    line = lines[0]
    row = {
        "sow_ref": "SOW-A",
        "resource_line_id": str(line.id),
        "period_month": "2026-01",
        "actual_hours": "160",
        "actual_cost": "19200.00",
        "actual_revenue": "32000.00",
    }
    await import_csv(
        session, actor_id=finance_user.id, csv_bytes=_csv([row])
    )
    # Re-import with corrected numbers for the same (line, month).
    row2 = dict(row)
    row2["actual_hours"] = "170"
    row2["actual_cost"] = "20400.00"
    row2["actual_revenue"] = "34000.00"
    await import_csv(
        session, actor_id=finance_user.id, csv_bytes=_csv([row2])
    )
    rows = list(
        (await session.execute(select(ActualPeriod))).scalars().all()
    )
    # Same (line, month) → still one row, upserted values.
    assert len(rows) == 1
    assert Decimal(rows[0].actual_cost) == Decimal("20400.00")
    assert Decimal(rows[0].actual_revenue) == Decimal("34000.00")
    assert Decimal(rows[0].actual_hours) == Decimal("170")


# ---- actual_gm_for aggregation ----------------------------------------


async def test_actual_gm_for_aggregates_two_lines_two_periods(
    session, finance_user
):
    """2 lines (US + India) × 2 periods; assert Jan aggregation.

    Jan totals: US $32k rev / $19.2k cost -> 40% GM.
                India $12.8k rev / $4.8k cost -> 62.5% GM.
    We assert on Jan only so the period_month filter is exercised.
    """

    gm, lines = await _seed_gm(session)
    us, india = lines
    rows = [
        {
            "sow_ref": "SOW-A",
            "resource_line_id": str(us.id),
            "period_month": "2026-01",
            "actual_hours": "160",
            "actual_cost": "19200.00",
            "actual_revenue": "32000.00",
        },
        {
            "sow_ref": "SOW-A",
            "resource_line_id": str(india.id),
            "period_month": "2026-01",
            "actual_hours": "160",
            "actual_cost": "4800.00",
            "actual_revenue": "12800.00",
        },
        # Feb rows — should NOT be counted in Jan aggregation.
        {
            "sow_ref": "SOW-A",
            "resource_line_id": str(us.id),
            "period_month": "2026-02",
            "actual_hours": "150",
            "actual_cost": "18000.00",
            "actual_revenue": "30000.00",
        },
        {
            "sow_ref": "SOW-A",
            "resource_line_id": str(india.id),
            "period_month": "2026-02",
            "actual_hours": "150",
            "actual_cost": "4500.00",
            "actual_revenue": "12000.00",
        },
    ]
    await import_csv(
        session, actor_id=finance_user.id, csv_bytes=_csv(rows)
    )

    snap = await actual_gm_for(
        session, gm_model_id=gm.id, period_month=date(2026, 1, 1)
    )
    # Sum-of-cost / sum-of-revenue, not mean of percentages.
    assert snap.revenue == Decimal("44800.00")
    assert snap.cost_us == Decimal("19200.00")
    assert snap.cost_india == Decimal("4800.00")
    # US: (32000 - 19200) / 32000 = 0.4
    assert snap.gm_us == Decimal("0.4")
    # India: (12800 - 4800) / 12800 = 0.625
    assert snap.gm_india == Decimal("0.625")


# ---- POST /actuals/import via HTTP -------------------------------------


async def test_import_endpoint_returns_batch(
    app_with_session, session, monkeypatch, finance_user
):
    gm, lines = await _seed_gm(session)
    line = lines[0]
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    csv_bytes = _csv(
        [
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(line.id),
                "period_month": "2026-01",
                "actual_hours": "160",
                "actual_cost": "19200.00",
                "actual_revenue": "32000.00",
            }
        ]
    )
    async with _client(app_with_session) as c:
        r = await c.post(
            "/actuals/import",
            headers={"X-Test-User": "finance@smartek21.com"},
            files={"file": ("actuals.csv", csv_bytes, "text/csv")},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "committed"
        assert body["row_count"] == 1


async def test_import_endpoint_422_on_validation_failure(
    app_with_session, session, monkeypatch, finance_user
):
    gm, lines = await _seed_gm(session)
    line = lines[0]
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    csv_bytes = _csv(
        [
            {
                "sow_ref": "SOW-A",
                "resource_line_id": str(line.id),
                "period_month": "2026-01",
                "actual_hours": "10",
                "actual_cost": "",  # missing → 422
                "actual_revenue": "200",
            }
        ]
    )
    async with _client(app_with_session) as c:
        r = await c.post(
            "/actuals/import",
            headers={"X-Test-User": "finance@smartek21.com"},
            files={"file": ("actuals.csv", csv_bytes, "text/csv")},
        )
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        cols = {e.get("column") for e in detail["errors"]}
        assert "actual_cost" in cols
