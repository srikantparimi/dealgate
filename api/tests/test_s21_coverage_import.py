"""Explicit financial service coverage is validated before ledger writes."""

import uuid
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models.actual import FinancialActual
from app.models.approval import ApprovalPackage
from app.services.actuals_import import FinancialImportInput, import_financial
from tests.test_s21_financial_actuals import actor, fixture, request, scope  # noqa: F401


def covered(account_id, **changes):
    raw = request(account_id).model_dump(mode="json")
    raw["rows"][0].update(source_date="2026-10-01", coverage={
        "sow_version_id": str(uuid.uuid4()), "schedule_row": 0,
        "fraction_start": "0", "fraction_end": "0.5", "through_date": "2026-10-01",
        "basis_evidence": "Finance confirms half the same service scope"}, **changes)
    return raw


def test_coverage_input_roundtrips_explicit_scope_without_deriving_dates():
    raw = covered(uuid.uuid4())
    assert FinancialImportInput.model_validate(raw).model_dump(mode="json") == raw


@pytest.mark.parametrize("changes", [
    {"fraction_start": "0.5", "fraction_end": "0.5"},
    {"fraction_start": "-0.1"}, {"fraction_end": "1.01"},
    {"fraction_end": 0.5}, {"fraction_end": "NaN"},
    {"schedule_row": True}, {"schedule_row": -1}, {"basis_evidence": " "},
])
def test_coverage_rejects_ambiguous_or_invalid_scope(changes):
    raw = covered(uuid.uuid4())
    raw["rows"][0]["coverage"].update(changes)
    with pytest.raises(ValidationError):
        FinancialImportInput.model_validate(raw)


@pytest.mark.asyncio
async def test_coverage_requires_signed_source_and_rejects_whole_batch(session):
    user, deal, sow, gm, _ = await fixture(session)
    raw = covered(deal.client_id, gm_model_id=str(gm.id))
    raw["rows"][0]["coverage"]["sow_version_id"] = str(sow.id)
    raw["rows"].append(request(deal.client_id).model_dump(mode="json")["rows"][0] | {"source_id": "separate"})
    with pytest.raises(HTTPException) as error:
        await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))
    assert error.value.status_code == 422
    assert "signed" in str(error.value.detail).lower()
    assert not (await session.scalars(select(FinancialActual))).all()


async def signed_coverage_fixture(session, monkeypatch):
    from app.gm.commercial import FeeAllocation, FixedFee, PeriodCost, calculate_component
    from app.services.commercial_models import SCHEDULE
    from tests.test_s21_commercial_profiles import component
    monkeypatch.setenv("DEALGATE_REPORTING_TIMEZONE", "UTC")
    monkeypatch.setenv("DEALGATE_REPORTING_CURRENCY", "USD")
    user, deal, sow, gm, _ = await fixture(session)
    today = datetime.now(UTC).date()
    month = today.replace(day=1)
    schedule = calculate_component(component(
        service_start=month, service_end=today,
        pricing=FixedFee(Decimal("24000"), (FeeAllocation(month, "India", Decimal(1)),),
                         "Confirmed service scope", Decimal("0.01")),
        costs=(PeriodCost("delivery", month, "India", Decimal("10000")),),
    ))
    gm.commercial_snapshot = {"tenant_id": "financial-ledger-tests", "environment": "local",
                              "schedule": SCHEDULE.dump_python(schedule, mode="json")}
    session.add(ApprovalPackage(opportunity_id=deal.id, sow_version_id=sow.id,
        gm_model_id=gm.id, package_hash="coverage-fixture", status="released", submitted_by=user.id))
    await session.commit()
    raw = covered(deal.client_id, gm_model_id=str(gm.id))
    raw["rows"][0].update(period_month=month.isoformat(), source_date=today.isoformat())
    raw["rows"][0]["coverage"].update(sow_version_id=str(sow.id), through_date=today.isoformat())
    return user, gm, raw


@pytest.mark.asyncio
async def test_signed_coverage_replay_correction_and_cross_source_overlap(session, monkeypatch):
    from copy import deepcopy
    from app.services.actuals_import import financial_records
    user, gm, raw = await signed_coverage_fixture(session, monkeypatch)
    frozen = deepcopy(gm.commercial_snapshot)
    first = await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))
    assert (await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))).id == first.id
    overlapping = deepcopy(raw)
    overlapping.update(source_system="Another Finance system", idempotency_key=str(uuid.uuid4()))
    with pytest.raises(HTTPException) as error:
        await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(overlapping))
    assert error.value.status_code == 422 and "overlap" in str(error.value.detail)
    raw["idempotency_key"] = str(uuid.uuid4())
    raw["rows"][0].update(revision=2, expected_previous_revision=1, amount="11000.99")
    await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))
    history = await financial_records(session, actor=actor(user), history=True)
    assert [item["revision"] for item in history] == [2, 1]
    assert all(item["coverage"] == raw["rows"][0]["coverage"] for item in history)
    assert gm.commercial_snapshot == frozen


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["invoice", "version", "index", "month", "future", "fx"])
async def test_invalid_coverage_never_writes_a_financial_fact(session, monkeypatch, change):
    from datetime import timedelta
    user, _, raw = await signed_coverage_fixture(session, monkeypatch)
    row, coverage = raw["rows"][0], raw["rows"][0]["coverage"]
    if change == "invoice":
        row["measure"] = "billed"
    elif change == "version":
        coverage["sow_version_id"] = str(uuid.uuid4())
    elif change == "index":
        coverage["schedule_row"] = 99
    elif change == "month":
        row["period_month"] = "2000-01-01"
    elif change == "future":
        coverage["through_date"] = (date.fromisoformat(row["source_date"]) + timedelta(days=1)).isoformat()
    else:
        row["currency"] = "EUR"
    with pytest.raises(HTTPException) as error:
        await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))
    assert error.value.status_code == 422
    assert not (await session.scalars(select(FinancialActual))).all()


@pytest.mark.asyncio
async def test_legacy_replay_hash_is_unchanged_when_coverage_is_absent(session):
    user, deal, _, _, _ = await fixture(session)
    body = request(deal.client_id)
    legacy = body.model_dump(mode="json")
    legacy["rows"][0].pop("coverage", None)
    batch = await import_financial(session, actor=actor(user), body=body)
    assert batch.request_hash == hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()


@pytest.mark.asyncio
async def test_replaced_signature_cannot_qualify_historical_verified_upload(session, monkeypatch):
    from datetime import timedelta
    from app.models.signed_sow import SignedSowUpload
    user, gm, raw = await signed_coverage_fixture(session, monkeypatch)
    package = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.gm_model_id == gm.id))
    now = datetime.now(UTC)
    for state, when in (("verified", now - timedelta(minutes=1)), ("pending", now)):
        session.add(SignedSowUpload(package_id=package.id, file_s3_key=f"synthetic/{state}",
            file_hash=state, uploaded_by=user.id, uploaded_at=when, verify_status=state))
    await session.commit()
    with pytest.raises(HTTPException) as error:
        await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))
    assert error.value.status_code == 422
    assert not (await session.scalars(select(FinancialActual))).all()


@pytest.mark.asyncio
async def test_current_estimate_replaces_only_covered_scope_and_correction_reconciles(session, monkeypatch):
    from copy import deepcopy
    from app.services.forecast_plans import outlook
    user, gm, raw = await signed_coverage_fixture(session, monkeypatch)
    now = datetime.now(UTC)
    before = await outlook(session, actor=actor(user), as_of=now)
    raw["rows"][0]["amount"] = "11000.99"
    revenue = deepcopy(raw["rows"][0])
    for measure, amount in (("delivery_cost", "6000"), ("billed", "15000"), ("cash_collected", "8000")):
        row = deepcopy(revenue)
        row.update(source_id=measure, measure=measure, amount=amount)
        if measure != "delivery_cost":
            row["coverage"] = None
        raw["rows"].append(row)
    await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))
    view = await outlook(session, actor=actor(user), as_of=now)
    estimate = view["current_period_estimate"]
    assert estimate["totals"]["revenue"] == Decimal("23000.99")
    assert estimate["totals"]["cost"] == Decimal("11000")
    assert estimate["totals"]["profit"] == Decimal("12000.99")
    assert estimate["rows"][0]["revenue"]["uncovered_forecast"] == Decimal("12000")
    assert view["current_month"] == before["current_month"]
    assert {x["measure"]: x["amount"] for x in view["financial_actuals"]["totals"]} == {
        "recognized_revenue": Decimal("11000.99"), "delivery_cost": Decimal("6000"),
        "billed": Decimal("15000"), "cash_collected": Decimal("8000")}
    raw["idempotency_key"] = str(uuid.uuid4())
    revenue.update(revision=2, expected_previous_revision=1, amount="10500")
    raw["rows"] = [revenue]
    await import_financial(session, actor=actor(user), body=FinancialImportInput.model_validate(raw))
    corrected = await outlook(session, actor=actor(user), as_of=now)
    assert corrected["current_period_estimate"]["totals"]["revenue"] == Decimal("22500")
    assert corrected["current_period_estimate"]["totals"]["cost"] == Decimal("11000")
    hidden = await outlook(session, actor=actor(user, ("Sales",)), as_of=now)
    assert "current_period_estimate" not in hidden
