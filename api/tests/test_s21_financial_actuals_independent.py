"""Independent 0051 ledger boundaries; SQLite units, not deployed acceptance."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text

from app.auth import AuthUser
from app.models.actual import FinancialActual, FinancialImportBatch
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import test_fixtures
from app.services.actuals_import import FinancialImportInput, financial_records, import_financial

TENANT = "independent-actuals-qa"


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", TENANT)
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")


@pytest_asyncio.fixture
async def ledger(session):
    # Exercise the actual SET NULL foreign keys, not a manually detached fact.
    await session.execute(text("PRAGMA foreign_keys=ON"))
    assert await session.scalar(text("PRAGMA foreign_keys")) == 1
    return session


async def user(session, *, fixture=False):
    roles = ["Finance", "SystemAdmin"] + (["officeapp-e2e"] if fixture else [])
    identity = uuid.uuid4()
    row = User(id=identity, email=f"{identity}@independent.test", name="QA Finance", groups=roles)
    session.add(row)
    await session.commit()
    return AuthUser(row.id, row.email, row.name, tuple(roles))


async def account(session):
    row = Client(id=uuid.uuid4(), name="Independent financial account")
    session.add(row)
    await session.commit()
    return row


async def gm_source(session, owner, client, *, tenant=TENANT, environment="local"):
    # Minimal stored source metadata fixture; no signature or commercial-engine proof.
    deal = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner.id, governance_status="Intake")
    session.add(deal)
    await session.flush()
    gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, engagement_type="fixed_assignment",
                 created_by=owner.id, currency="USD", version=1,
                 commercial_snapshot={"tenant_id": tenant, "environment": environment})
    session.add(gm)
    await session.commit()
    return gm


def body(account_id, **changes):
    row = dict(account_id=str(account_id), source_id="finance-row-1", revision=1,
               expected_previous_revision=0, period_month="2026-10-01", measure="recognized_revenue",
               amount="12345.67", currency="USD", source_date="2026-10-31", reason="Confirmed Finance source")
    return FinancialImportInput.model_validate(dict(source_system="QA managed ledger",
        idempotency_key=str(uuid.uuid4()), rows=[row | changes]))


def correction(request, **changes):
    raw = request.model_dump(mode="json")
    raw["idempotency_key"] = str(uuid.uuid4())
    raw["rows"][0].update(revision=2, expected_previous_revision=1, amount="12000.01", **changes)
    return FinancialImportInput.model_validate(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["account", "tenant", "environment"])
async def test_gm_link_must_match_account_tenant_and_environment(ledger, boundary):
    owner, client = await user(ledger), await account(ledger)
    gm_account = await account(ledger) if boundary == "account" else client
    gm = await gm_source(ledger, owner, gm_account,
        tenant="foreign-tenant" if boundary == "tenant" else TENANT,
        environment="staging" if boundary == "environment" else "local")
    with pytest.raises(HTTPException) as error:
        await import_financial(ledger, actor=owner, body=body(client.id, gm_model_id=str(gm.id)))
    assert error.value.status_code in {403, 404, 422}
    assert not (await ledger.scalars(select(FinancialActual))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_identity", ["account_id", "measure"])
async def test_correction_cannot_move_account_or_measure_and_preserves_original(ledger, changed_identity):
    owner, client = await user(ledger), await account(ledger)
    original = body(client.id)
    await import_financial(ledger, actor=owner, body=original)
    changes = {changed_identity: str((await account(ledger)).id) if changed_identity == "account_id" else "billed"}
    with pytest.raises(HTTPException) as error:
        await import_financial(ledger, actor=owner, body=correction(original, **changes))
    assert error.value.status_code == 422
    history = await financial_records(ledger, actor=owner, history=True)
    assert [(row["revision"], row["amount"], row["measure"]) for row in history] == [(1, "12345.67", "recognized_revenue")]


@pytest.mark.asyncio
async def test_competing_correction_replay_preserves_conflict_status_and_one_failed_batch(ledger):
    first_actor, second_actor, client = await user(ledger), await user(ledger), await account(ledger)
    original = body(client.id)
    await import_financial(ledger, actor=first_actor, body=original)
    winning, losing = correction(original), correction(original)
    await import_financial(ledger, actor=first_actor, body=winning)
    errors = []
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await import_financial(ledger, actor=second_actor, body=losing)
        errors.append(error.value)
    assert [error.status_code for error in errors] == [409, 409]
    assert errors[0].detail == errors[1].detail
    assert len((await ledger.scalars(select(FinancialActual))).all()) == 2
    assert len((await ledger.scalars(select(FinancialImportBatch))).all()) == 3


@pytest.mark.asyncio
async def test_failed_whole_batch_replay_preserves_errors_audit_and_no_partial_rows(ledger):
    owner, client = await user(ledger), await account(ledger)
    raw = body(client.id).model_dump(mode="json")
    raw["rows"].append({**raw["rows"][0], "source_id": "missing-account", "account_id": str(uuid.uuid4())})
    request = FinancialImportInput.model_validate(raw)
    errors = []
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await import_financial(ledger, actor=owner, body=request)
        errors.append(error.value)
    assert [error.status_code for error in errors] == [422, 422]
    assert errors[0].detail == errors[1].detail
    assert not (await ledger.scalars(select(FinancialActual))).all()
    assert len((await ledger.scalars(select(FinancialImportBatch))).all()) == 1
    audits = (await ledger.scalars(select(AuditEvent).where(AuditEvent.action == "actuals.financial_import_rejected"))).all()
    assert len(audits) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", ["12345.67", "-12345.67", "0.01"])
async def test_signed_decimal_cent_values_round_trip_without_float_expectations(ledger, amount):
    owner, client = await user(ledger), await account(ledger)
    await import_financial(ledger, actor=owner, body=body(client.id, amount=amount))
    ledger.expire_all()
    records = await financial_records(ledger, actor=owner)
    assert len(records) == 1 and records[0]["amount"] == amount
    assert (await ledger.scalar(select(FinancialActual))).amount == Decimal(amount)


def test_input_preserves_long_exact_amount_and_fx_strings():
    amount, fx = "12345678901234567890.01234567890123456789", "1.12345678901234567890123456789"
    request = body(uuid.uuid4(), amount=amount, fx_rate=fx, fx_version="qa-fx-1", fx_date="2026-10-31")
    encoded = request.model_dump(mode="json")["rows"][0]
    assert encoded["amount"] == amount and encoded["fx_rate"] == fx


async def fixture_import(session):
    owner = await user(session, fixture=True)
    issued = await test_fixtures.create_fixture(session, actor_id=owner.id, label="Ledger QA", reviewer_ids=[], hours=1)
    await session.commit()
    request = body(issued["client_id"])
    await import_financial(session, actor=owner, body=request)
    return owner, issued, request


def expire_fixture(monkeypatch):
    later = datetime.now(UTC) + timedelta(hours=2)

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return later.astimezone(tz) if tz else later.replace(tzinfo=None)

    monkeypatch.setattr(test_fixtures, "datetime", ExpiredClock)


@pytest.mark.asyncio
async def test_fixture_expiry_hides_records_and_rejects_new_corrections(ledger, monkeypatch):
    owner, _, request = await fixture_import(ledger)
    assert len(await financial_records(ledger, actor=owner)) == 1
    expire_fixture(monkeypatch)
    assert await financial_records(ledger, actor=owner, history=True) == []
    with pytest.raises(HTTPException) as error:
        await import_financial(ledger, actor=owner, body=correction(request))
    assert error.value.status_code == 422
    assert len((await ledger.scalars(select(FinancialActual))).all()) == 1


@pytest.mark.asyncio
async def test_fixture_expiry_is_rechecked_on_successful_import_replay(ledger, monkeypatch):
    owner, _, request = await fixture_import(ledger)
    expire_fixture(monkeypatch)
    with pytest.raises(HTTPException) as error:
        await import_financial(ledger, actor=owner, body=request)
    assert error.value.status_code in {403, 404, 422}


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", ["account", "gm"])
async def test_business_history_detaches_on_deletion_and_accepts_immutable_correction(ledger, deleted):
    owner, client = await user(ledger), await account(ledger)
    client_id = client.id
    gm = await gm_source(ledger, owner, client) if deleted == "gm" else None
    original = body(client_id, gm_model_id=str(gm.id) if gm else None)
    await import_financial(ledger, actor=owner, body=original)
    await ledger.delete(gm if gm else client)
    await ledger.commit()
    ledger.expire_all()
    records = await financial_records(ledger, actor=owner, account_id=client_id)
    assert len(records) == 1 and records[0]["source_detached"]
    assert records[0]["account_id"] == str(client_id) and records[0]["amount"] == "12345.67"
    await import_financial(ledger, actor=owner, body=correction(original))
    history = await financial_records(ledger, actor=owner, history=True)
    assert [(row["revision"], row["amount"]) for row in history] == [(2, "12000.01"), (1, "12345.67")]
    assert all(row["source_detached"] for row in history)


@pytest.mark.asyncio
async def test_deleted_fixture_facts_do_not_become_business_history(ledger):
    owner, issued, request = await fixture_import(ledger)
    await ledger.delete(await ledger.get(Opportunity, issued["opportunity_id"]))
    await ledger.flush()
    await ledger.delete(await ledger.get(Client, issued["client_id"]))
    await ledger.commit()
    ledger.expire_all()
    business_reader = await user(ledger)
    assert await financial_records(ledger, actor=business_reader, history=True) == []
    assert await financial_records(ledger, actor=owner, history=True) == []
    with pytest.raises(HTTPException) as error:
        await import_financial(ledger, actor=business_reader, body=correction(request))
    assert error.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("dimension,value", [("DEALGATE_TENANT_ID", "other"), ("DEALGATE_ENV", "staging")])
async def test_financial_read_scope_never_crosses_tenant_or_environment(ledger, monkeypatch, dimension, value):
    owner, client = await user(ledger), await account(ledger)
    await import_financial(ledger, actor=owner, body=body(client.id))
    monkeypatch.setenv(dimension, value)
    assert await financial_records(ledger, actor=owner, account_id=client.id, history=True) == []
