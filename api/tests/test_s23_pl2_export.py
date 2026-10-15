"""S23-PL2 B10 / T6 (CSV half) — the Pipeline export and CSV neutralisation.

A cell that a spreadsheet would read as a formula (it starts with = + - @, tab
or carriage return) gets a leading apostrophe in every CSV the product writes.
A plain number (``-123.45``) can never be a formula and stays as it is.
"""

from __future__ import annotations

import pytest

from app.services.csv_safety import neutralise, safe_row

FORMULA = '=HYPERLINK("http://x","y")'
MARKUP = "<img src=x onerror=alert(1)>"


@pytest.mark.parametrize(("raw", "expected"), [
    (FORMULA, "'" + FORMULA),
    ("+1-555", "'+1-555"),
    ("-2+3", "'-2+3"),
    ("@SUM(A1)", "'@SUM(A1)"),
    ("\tcmd", "'\tcmd"),
    ("\rcmd", "'\rcmd"),
    ("-", "'-"),
    ("-123.45", "-123.45"),
    ("123", "123"),
    ("0.50", "0.50"),
    ("12e3", "12e3"),
    ("123\n", "123\n"),  # not a plain number, but harmless: no trigger character first
    ("-123\n", "'-123\n"),  # a trailing newline makes it text, and text starting with - is neutralised
    (MARKUP, MARKUP),
    ("Acme = best", "Acme = best"),
    ("", ""),
])
def test_neutralise(raw, expected):
    assert neutralise(raw) == expected


def test_neutralise_non_text_values():
    from datetime import date
    from decimal import Decimal

    assert neutralise(None) == ""
    assert neutralise(Decimal("-5.00")) == "-5.00"
    assert neutralise(7) == "7"
    assert neutralise(date(2026, 10, 14)) == "2026-10-14"


def test_safe_row_neutralises_every_cell():
    assert safe_row([FORMULA, "ok", None, "-1"]) == ["'" + FORMULA, "ok", "", "-1"]


# --- GET /pipeline/export ---------------------------------------------------------------

import csv  # noqa: E402
import io  # noqa: E402
import uuid  # noqa: E402
from decimal import Decimal  # noqa: E402

from app.auth import AuthUser  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402
from tests import test_s23_pl2_workspace as shared  # noqa: E402
from tests.test_s23_pl2_workspace import PIPELINE_ID, STAGES, VIEWER, client_for  # noqa: E402

# Shared fixtures, bound as module globals so pytest finds them here.
api, engine, frozen_clock, seeded = shared.api, shared.engine, shared.frozen_clock, shared.seeded

DEAL_HEADER = ["Opportunity", "Client", "Deal owner", "Account owner", "Business unit", "HubSpot region",
               "Sales stage", "Amount", "Currency", "Close date", "Created", "Last activity", "SOW state",
               "NDA on file", "MSA on file", "Next action", "Next action due"]
CLIENT_HEADER = ["Client", "Account owner", "Matching deals", "Open deals", "Matching value USD", "NDA on file",
                 "MSA on file", "Last matching activity"]


async def export(api, **params) -> tuple[list[list[str]], str]:
    response = await api.get("/pipeline/export", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    raw = response.content.decode("utf-8")
    assert raw.startswith("\ufeff")
    body = raw[1:]
    assert "\r\n" in body and "\n" not in body.replace("\r\n", "")
    return list(csv.reader(io.StringIO(body))), response.headers["content-disposition"]


async def test_deals_export_has_every_filtered_row_in_order(api, seeded):
    rows, disposition = await export(api)
    assert disposition == 'attachment; filename="DealGate_Pipeline_deals.csv"'
    assert rows[0] == DEAL_HEADER
    workspace = (await api.get("/pipeline/workspace", params={"page_size": 100})).json()
    assert [row[0] for row in rows[1:]] == [row["title"] for row in workspace["rows"]]
    by_title = {row[0]: row for row in rows[1:]}
    assert by_title["Acme rollout"] == [
        "Acme rollout", "Acme Retail", "Ava Archer", "Ava Archer", "ST21 · US", "US",
        "1 · Initial Contact / Prospecting", "100000.00", "USD", "2026-10-19", "2026-09-04", "2026-10-12",
        "No SOW", "Yes", "Yes", "Send revised proposal", "2026-10-11"]
    assert by_title["Bolt warehouse scanners"] == [
        "Bolt warehouse scanners", "Bolt Logistics", "Unassigned", "Former HubSpot user", "IT Avalon · US",
        "US - IT Avalon (Staffing)", "4 · Proposal", "", "USD", "", "2026-10-09", "2026-10-13", "No SOW", "Yes",
        "No", "Confirm budget owner", ""]
    assert by_title["Cobalt clinic portal"][4:9] == ["Unmapped · Brazil", "Brazil", "5 · Negotiation", "75000.00",
                                                     "EUR"]
    assert by_title["Delta supply chain"][4:6] == ["", ""]  # no region at all
    assert by_title["Cobalt records audit"][6] == "Hold (open, paused)"
    assert by_title["Acme data platform"][12] == "In review · delivery/hr"


async def test_export_is_not_paged_and_follows_filters_and_sort(api, seeded):
    for params in ({"status": "all"}, {"status": "all", "sort": "name"}, {"bu": "unmapped"},
                   {"attention": "any", "sort": "activity"}, {"q": "acme"}):
        rows, _ = await export(api, **params)
        workspace = (await api.get("/pipeline/workspace", params={**params, "page_size": 25})).json()
        assert len(rows) - 1 == workspace["page"]["total_rows"], params
        if workspace["page"]["total_rows"] <= 25:
            assert [row[0] for row in rows[1:]] == [row["title"] for row in workspace["rows"]], params


async def test_clients_export(api, seeded):
    rows, disposition = await export(api, tab="clients", sort="name", include_unmatched_clients="true")
    assert disposition == 'attachment; filename="DealGate_Pipeline_clients.csv"'
    assert rows[0] == CLIENT_HEADER
    assert rows[1] == ["Acme Retail", "Ava Archer", "3", "3", "470000.00", "Yes", "Yes", "2026-10-12"]
    by_name = {row[0]: row for row in rows[1:]}
    assert by_name["Bolt Logistics"][1] == "Former HubSpot user"
    assert by_name["Cobalt Health"][1] == "Unassigned"
    assert by_name["Fjord Energy"] == ["Fjord Energy", "Ava Archer", "0", "0", "", "No", "Yes", ""]
    assert len(rows) - 1 == 7


async def test_export_roles(session, seeded):
    for role, code in (("Presales", 403), ("Marketing", 403), ("Sales", 200), ("Finance", 200),
                       ("SalesLeader", 200), ("SystemAdmin", 200)):
        user = AuthUser(uuid.uuid4(), f"{role.lower()}@example.test", role, (role,))
        async with client_for(session, user) as client:
            assert (await client.get("/pipeline/export")).status_code == code, role


async def test_export_rejects_what_the_workspace_rejects(api, seeded):
    for params in ({"status": "closed"}, {"bu": "Avalon"}, {"sow": "scope_gm"}, {"stage": 12}):
        assert (await api.get("/pipeline/export", params=params)).status_code == 422, params


# --- T6: hostile names stay text in JSON and never run as formulas in a CSV -----------------


async def _hostile(session) -> dict[str, uuid.UUID]:
    sid, label, order, _ = STAGES[0]
    markup_client = Client(name=MARKUP, hubspot_company_id="c-markup", hubspot_owner_id="101")
    formula_client = Client(name=FORMULA, hubspot_company_id="c-formula", hubspot_owner_id="101")
    session.add_all([markup_client, formula_client])
    await session.flush()
    ids = {}
    for title, client in ((FORMULA, markup_client), (MARKUP, formula_client)):
        deal = Opportunity(source="hubspot", hubspot_deal_id=f"hs-{uuid.uuid4()}", name=title, client_id=client.id,
                           hubspot_owner_id="101", hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid,
                           stage_label=label, stage_order=order, amount=Decimal("-250.50"), currency="USD",
                           governance_status="Intake")
        session.add(deal)
        await session.flush()
        ids[title] = deal.id
    await session.commit()
    return ids


async def test_hostile_names_are_verbatim_in_json_and_neutralised_in_csv(api, seeded, session):
    ids = await _hostile(session)
    body = (await api.get("/pipeline/workspace", params={"q": "x", "page_size": 100})).json()
    rows = {row["id"]: row for row in body["rows"]}
    assert rows[str(ids[FORMULA])]["title"] == FORMULA
    assert rows[str(ids[FORMULA])]["client"]["name"] == MARKUP
    assert rows[str(ids[MARKUP])]["title"] == MARKUP
    assert rows[str(ids[MARKUP])]["client"]["name"] == FORMULA
    assert rows[str(ids[MARKUP])]["amount"] == "-250.50"

    deal_rows, _ = await export(api, q="x")
    by_first = {row[0]: row for row in deal_rows[1:]}
    assert by_first["'" + FORMULA][1] == MARKUP
    assert by_first[MARKUP][1] == "'" + FORMULA
    assert by_first[MARKUP][7] == "-250.50"  # a plain negative number stays a number
    client_rows, _ = await export(api, tab="clients", q="x")
    assert {row[0] for row in client_rows[1:]} >= {"'" + FORMULA, MARKUP}
    clients = {row["name"] for row in (await api.get("/pipeline/workspace",
                                                     params={"tab": "clients", "q": "x"})).json()["rows"]}
    assert {FORMULA, MARKUP} <= clients


# --- every other CSV the product writes is neutralised too (no BOM on those) ------------------


async def test_reports_pipeline_export_is_neutralised(session, frozen_clock):
    from app.routers.reports import router as reports_router

    client = Client(name=MARKUP, hubspot_company_id="c-reports")
    session.add(client)
    await session.flush()
    for title, amount in ((FORMULA, Decimal("10.00")), ("@SUM(A1)", Decimal("-5.25"))):
        session.add(Opportunity(source="hubspot", hubspot_deal_id=f"hs-{uuid.uuid4()}", name=title,
                                client_id=client.id, amount=amount, currency="USD", governance_status="Intake"))
    await session.commit()
    async with client_for(session, VIEWER, reports_router) as api:
        response = await api.get("/reports/pipeline/export.csv")
    assert response.status_code == 200, response.text
    assert response.text.startswith("deal,client")  # no BOM: existing readers parse it as is
    rows = {row["deal"]: row for row in csv.DictReader(io.StringIO(response.text)) if row["client"]}
    assert set(rows) == {"'" + FORMULA, "'@SUM(A1)"}
    assert rows["'" + FORMULA]["client"] == MARKUP
    assert rows["'@SUM(A1)"]["amount"] == "-5.25"


def test_portfolio_forecast_csv_is_neutralised():
    from app.services.engagement_forecast import portfolio_csv

    row = {"business_unit": "ST21", "client_name": FORMULA, "name": "+cmd", "sales_owner": "@owner",
           "delivery_owner": "-lead", "type": "fixed", "start": "2026-10-01", "end": "2026-12-31", "people": 2,
           "revenue_month": "-1200.50", "cost_month": "300.00", "gm_pct_month": None, "gm_pct_term": "0.31",
           "status": "\tstatus"}
    text = portfolio_csv({"groups": [{"business_unit": "ST21", "people": 2, "revenue": "-1200.50", "cost": "300.00",
                                      "gm_pct": None}],
                          "rows": [row], "month": "2026-10",
                          "totals": {"people": 2, "revenue": "-1200.50", "cost": "300.00", "gm_pct": None}})
    assert not text.startswith("﻿")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[1] == ["ST21", "'" + FORMULA, "'+cmd", "'@owner", "'-lead", "fixed", "2026-10-01", "2026-12-31",
                         "2", "-1200.50", "300.00", "", "0.31", "'\tstatus"]


async def test_command_center_accounts_csv_is_neutralised(monkeypatch):
    from app.services import command_center
    from app.services.command_center import CommandAccountRow, CommandAccountsPage, command_accounts_csv
    from app.services.hubspot_pipeline import PipelineFilters

    row = CommandAccountRow(
        opportunity_id=uuid.uuid4(), hubspot_deal_id="123", account_id=None, account_name=FORMULA,
        engagement_id=None, engagement_name="=cmd", business_unit="@bu", pipeline_id="p", stage_id="s",
        stage_label="+stage", stage_order=5, is_closed_won=False, sow_stage="none", currency="USD",
        deal_value=Decimal("-10.00"), owner_id=None, owner_name="-owner", owner_email=None,
        next_action="=next", next_action_due="2026-10-20")

    async def one_page(session, *, scope, filters, actor=None):  # noqa: ANN001
        return CommandAccountsPage((row,), 1, 1, 100, "Stage 5+", ())

    monkeypatch.setattr(command_center, "list_command_accounts", one_page)
    text = await command_accounts_csv(None, scope=PipelineFilters())
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[1][:7] == ["'" + FORMULA, "'=cmd", "123", "p", "'+stage", "'@bu", "USD"]
    assert parsed[1][7] == "-10.00"
    assert parsed[1][13:] == ["'-owner", "'=next", "2026-10-20"]


async def test_bulk_import_log_csv_is_neutralised(session, monkeypatch):
    from app.routers import admin_bulk_imports

    async def overview(_session, _batch_id):  # noqa: ANN001
        return object()

    monkeypatch.setattr(admin_bulk_imports, "load_overview", overview)
    monkeypatch.setattr(admin_bulk_imports, "csv_rows", lambda _overview: [
        ["batch_id", "filename", "size", "errors"], ["b1", FORMULA, "-12", "@error"]])
    admin = AuthUser(uuid.uuid4(), "admin@example.test", "Admin", ("SystemAdmin",))
    async with client_for(session, admin, admin_bulk_imports.router) as api:
        response = await api.get(f"/admin/bulk-imports/{uuid.uuid4()}/log.csv")
    assert response.status_code == 200, response.text
    assert list(csv.reader(io.StringIO(response.text))) == [
        ["batch_id", "filename", "size", "errors"], ["b1", "'" + FORMULA, "-12", "'@error"]]
