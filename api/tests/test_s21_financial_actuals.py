"""FC-06 managed financial facts, distinct bases and immutable corrections."""

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.auth import AuthUser
from app.models.actual import FinancialActual, FinancialImportBatch
from app.services.actuals_import import FinancialImportInput, import_financial, financial_records
from tests.test_approval_routing import fixture
from tests.test_approvals import app_with_session, _client  # noqa: F401


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "financial-ledger-tests")
    monkeypatch.setenv("DEALGATE_ENV", "local")


def actor(user, groups=("Finance",)):
    return AuthUser(user.id, user.email, user.name, groups)


def request(account_id, **changes):
    return FinancialImportInput.model_validate({
        "source_system": "Managed Finance ledger", "idempotency_key": str(uuid.uuid4()),
        "rows": [{"account_id": str(account_id), "source_id": "recognized-100", "revision": 1,
                  "period_month": "2026-10-01", "measure": "recognized_revenue", "amount": "12000.01",
                  "currency": "USD", "source_date": "2026-10-15", "reason": "Confirmed Finance source"}],
        **changes})


@pytest.mark.asyncio
async def test_finance_replay_preserves_one_batch_and_exact_source_fact(session):
    user, deal, _, _, _ = await fixture(session)
    body = request(deal.client_id)
    first = await import_financial(session, actor=actor(user), body=body)
    assert (await import_financial(session, actor=actor(user), body=body)).id == first.id
    assert len((await session.scalars(select(FinancialActual))).all()) == 1
    rows = await financial_records(session, actor=actor(user))
    assert rows[0]["amount"] == "12000.01"
    assert rows[0]["measure"] == "recognized_revenue"
    assert rows[0]["source_system"] == body.source_system


@pytest.mark.asyncio
async def test_correction_keeps_old_revision_and_replaces_current_without_double_count(session):
    user, deal, _, _, _ = await fixture(session)
    original = request(deal.client_id)
    await import_financial(session, actor=actor(user), body=original)
    corrected = original.model_dump(mode="json")
    corrected["idempotency_key"] = str(uuid.uuid4())
    corrected["rows"][0].update(revision=2, expected_previous_revision=1, amount="11000.99", reason="Finance correction")
    await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(corrected))
    records = list((await session.scalars(select(FinancialActual).order_by(FinancialActual.revision))).all())
    assert [record.amount for record in records] == [Decimal("12000.01"), Decimal("11000.99")]
    current = await financial_records(session, actor=actor(user))
    assert len(current) == 1 and current[0]["revision"] == 2
    corrected["idempotency_key"] = str(uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(corrected))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_failed_whole_batch_keeps_error_history_but_no_partial_actuals(session):
    user, deal, _, _, _ = await fixture(session)
    body = request(deal.client_id).model_dump(mode="json")
    body["rows"].append({**body["rows"][0], "source_id": "unknown-account", "account_id": str(uuid.uuid4())})
    with pytest.raises(HTTPException) as error:
        await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(body))
    assert error.value.status_code == 422
    assert not (await session.scalars(select(FinancialActual))).all()
    failed = await session.scalar(select(FinancialImportBatch))
    assert failed.status == "failed" and failed.errors


@pytest.mark.asyncio
async def test_roles_and_tenant_scope_do_not_share_financial_records(session, monkeypatch):
    user, deal, _, _, _ = await fixture(session)
    body = request(deal.client_id)
    with pytest.raises(HTTPException) as denied:
        await import_financial(session, actor=actor(user, ("Sales",)), body=body)
    assert denied.value.status_code == 403
    await import_financial(session, actor=actor(user), body=body)
    with pytest.raises(HTTPException):
        await financial_records(session, actor=actor(user, ("HR",)))
    monkeypatch.setenv("DEALGATE_TENANT_ID", "other")
    assert await financial_records(session, actor=actor(user)) == []


@pytest.mark.parametrize("amount", [1.2, "NaN", "Infinity", "invalid"])
def test_financial_amount_never_accepts_floats_or_nonfinite_values(amount):
    from pydantic import ValidationError
    body = request(uuid.uuid4()).model_dump(mode="json")
    body["rows"][0]["amount"] = amount
    with pytest.raises(ValidationError):
        FinancialImportInput.model_validate(body)


@pytest.mark.asyncio
async def test_financial_http_permissions_import_and_source_history(app_with_session, session, monkeypatch):  # noqa: F811
    user, deal, _, _, _ = await fixture(session)
    body = request(deal.client_id).model_dump(mode="json")
    async with _client(app_with_session) as client:
        headers = {"X-Test-User": user.email}
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
        assert (await client.post("/actuals/financial-import", json=body, headers=headers)).status_code == 403
        assert (await client.get("/actuals/financial-records", headers=headers)).status_code == 403
        assert (await client.get("/actuals/financial-imports", headers=headers)).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
        response = await client.post("/actuals/financial-import", json=body, headers=headers)
        assert response.status_code == 201, response.text
        records = await client.get("/actuals/financial-records", headers=headers)
        assert records.status_code == 200 and records.json()["total"] == 1
        assert records.json()["items"][0]["amount"] == "12000.01"
        batches = await client.get("/actuals/financial-imports", headers=headers)
        assert batches.json()["total"] == 1
        assert batches.json()["items"][0]["id"] == response.json()["id"]


@pytest.mark.asyncio
async def test_outlook_separates_actuals_and_does_not_leak_to_other_roles(session, monkeypatch):
    from datetime import datetime
    from app.services.forecast_plans import outlook
    monkeypatch.setenv("DEALGATE_REPORTING_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("DEALGATE_REPORTING_CURRENCY", "USD")
    user, deal, _, _, _ = await fixture(session)
    now = datetime.fromisoformat("2026-10-20T12:00:00Z")
    before = await outlook(session, actor=actor(user), as_of=now)
    await import_financial(session, actor=actor(user), body=request(deal.client_id))
    view = await outlook(session, actor=actor(user), as_of=now)
    assert view["future"] == before["future"]
    assert view["actuals_available"] is True
    assert view["financial_actuals"]["totals"][0]["amount"] == Decimal("12000.01")
    assert view["financial_actuals"]["blended_with_forecast"] is False
    assert view["source_watermark"] != before["source_watermark"]
    hidden = await outlook(session, actor=actor(user, ("Sales",)), as_of=now)
    assert "financial_actuals" not in hidden
    assert hidden["actuals_available"] is False
