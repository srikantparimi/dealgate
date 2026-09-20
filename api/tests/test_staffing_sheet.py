"""Staffing sheet: template out, rows in (S10-05).

Context: `auto_staffing` used to invent a roster when the SOW carried no
resource table — three default roles, a default hours figure, a zero bill
rate — and a gross margin was computed from it silently. That is refused now,
which means there has to be a real way for a person to supply the plan. This
is it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from io import BytesIO

import httpx
import pytest
import pytest_asyncio
from openpyxl import Workbook

from app.db import get_session
from app.main import app as main_app
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.staffing_sheet import (
    COLUMNS,
    StaffingSheetError,
    build_template_xlsx,
    parse_staffing_xlsx,
)

OWNER_EMAIL = "delivery@smartek21.com"


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest_asyncio.fixture
async def app_with_deps(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery,SystemAdmin")


def _sheet(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Staffing"
    ws.append([label for _key, label in COLUMNS])
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- the sheet itself -----------------------------------------------------


def test_template_round_trips_through_the_parser():
    """The sheet we hand out must be one the parser accepts."""

    rows = parse_staffing_xlsx(build_template_xlsx())
    assert len(rows) == 1
    line = rows[0].to_resource_line()
    assert line["role"] == "Consultant"
    assert line["location"] == "US"
    assert Decimal(line["hours_billable"]) > 0
    assert Decimal(line["hourly_bill_rate"]) > 0


def test_parses_a_filled_sheet():
    data = _sheet(
        [
            ["Architect", "Principal", "US", 1, 120, 260, "2026-08-25", "2026-09-30"],
            ["Engineer", "Senior", "India", 0.5, 300, 85, "2026-08-25", "2026-09-30"],
        ]
    )
    rows = parse_staffing_xlsx(data)
    assert [r.role for r in rows] == ["Architect", "Engineer"]
    assert rows[1].location == "India"
    assert rows[1].allocation_pct == Decimal("0.5")


def test_currency_formatting_is_tolerated():
    """People paste rates as "$1,250.00". Rejecting that is not useful."""

    rows = parse_staffing_xlsx(
        _sheet([["Engineer", "Senior", "US", 1, "1,200", "$1,250.00", None, None]])
    )
    assert rows[0].hourly_bill_rate == Decimal("1250.00")
    assert rows[0].hours_billable == Decimal("1200")


def test_all_errors_are_reported_at_once():
    """Fixing one row per upload would be the worst version of this."""

    data = _sheet(
        [
            ["Engineer", "Senior", "Mars", 1, 100, 200, None, None],
            ["Engineer", "Senior", "US", 1, 0, 200, None, None],
            ["Engineer", "", "US", 1, 100, 200, None, None],
        ]
    )
    with pytest.raises(StaffingSheetError) as excinfo:
        parse_staffing_xlsx(data)
    fields = {e.get("field") for e in excinfo.value.errors}
    assert fields == {"location", "hours_billable", "seniority"}


def test_zero_hours_is_rejected():
    """A line with no hours contributes nothing but looks like a plan."""

    with pytest.raises(StaffingSheetError):
        parse_staffing_xlsx(_sheet([["Engineer", "Senior", "US", 1, 0, 200, None, None]]))


def test_missing_required_column_is_named():
    wb = Workbook()
    ws = wb.active
    ws.title = "Staffing"
    ws.append(["Role", "Seniority", "Location"])  # no hours column
    ws.append(["Engineer", "Senior", "US"])
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(StaffingSheetError) as excinfo:
        parse_staffing_xlsx(buf.getvalue())
    assert "Billable hours" in excinfo.value.message


def test_non_xlsx_payload_is_rejected_clearly():
    with pytest.raises(StaffingSheetError) as excinfo:
        parse_staffing_xlsx(b"%PDF-1.4 this is a pdf")
    assert "xlsx" in excinfo.value.message


# --- endpoints ------------------------------------------------------------


async def _seed_opportunity(session) -> Opportunity:
    user = User(id=uuid.uuid4(), email=OWNER_EMAIL, name="Delivery", groups=["Delivery"])
    client = Client(id=uuid.uuid4(), name="Contoso Data Services, LLC")
    session.add_all([user, client])
    await session.flush()
    opp = Opportunity(
        id=uuid.uuid4(),
        client_id=client.id,
        owner_id=user.id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return opp


async def test_template_endpoint_serves_an_xlsx(app_with_deps):
    async with _client(app_with_deps) as c:
        r = await c.get(
            "/sows/staffing-template.xlsx", headers={"X-Test-User": OWNER_EMAIL}
        )
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"  # a real xlsx is a zip
    assert parse_staffing_xlsx(r.content)


async def test_import_returns_lines_without_saving(app_with_deps, session):
    """Upload parses and returns; it must not become a cost basis on its own."""

    opp = await _seed_opportunity(session)
    data = _sheet([["Architect", "Principal", "US", 1, 120, 260, None, None]])

    async with _client(app_with_deps) as c:
        r = await c.post(
            f"/sows/{opp.id}/staffing/import",
            headers={"X-Test-User": OWNER_EMAIL},
            files={
                "file": (
                    "staffing.xlsx",
                    data,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count"] == 1
    assert body["resource_lines"][0]["role"] == "Architect"

    # Nothing persisted — no GM model was created by the upload.
    from app.models.gm_model import GmModel
    from sqlalchemy import select

    assert not list((await session.execute(select(GmModel))).scalars())


async def test_import_reports_every_bad_row(app_with_deps, session):
    opp = await _seed_opportunity(session)
    data = _sheet(
        [
            ["Engineer", "Senior", "Mars", 1, 100, 200, None, None],
            ["Engineer", "Senior", "US", 1, 0, 200, None, None],
        ]
    )
    async with _client(app_with_deps) as c:
        r = await c.post(
            f"/sows/{opp.id}/staffing/import",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("staffing.xlsx", data, "application/octet-stream")},
        )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert len(detail["errors"]) == 2
    assert {e["row"] for e in detail["errors"]} == {2, 3}


async def test_import_unknown_opportunity_is_404(app_with_deps):
    async with _client(app_with_deps) as c:
        r = await c.post(
            f"/sows/{uuid.uuid4()}/staffing/import",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("s.xlsx", _sheet([]), "application/octet-stream")},
        )
    assert r.status_code == 404
