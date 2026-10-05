"""Whole-source workforce imports, exact capacity, permissions and history."""
import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.auth import AuthUser
from app.models.people_planning import PeopleImportBatch, WorkforceVersion
from app.models.user import User
from app.services.people_planning import WorkforceImportInput, import_workforce, availability


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "people-import-test")
    monkeypatch.setenv("DEALGATE_ENV", "local")


async def principal(session):
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Synthetic HR", groups=["HR"])
    session.add(user)
    await session.commit()
    return AuthUser(id=user.id, email=user.email, name=user.name, groups=("HR",))


def payload(**changes):
    data = dict(source_system="synthetic-roster", request_key=str(uuid.uuid4()),
        expected_previous_batch_id=None, source_as_of="2026-10-01T12:00:00Z",
        reason="Managed workforce source confirms gross capacity and dated assignments",
        basis="gross_with_commitments", people=[dict(person_key="person-one", display_name="Synthetic engineer",
            role="Engineer", skills=["python"], level="senior", location="US", timezone="America/Los_Angeles",
            evidence=["Roster row 1"], intervals=[dict(kind="gross", allocation="1",
                start_date="2026-11-01", end_date="2026-11-30", assignment_key=None),
                dict(kind="committed", allocation="0.5", start_date="2026-11-01",
                    end_date="2026-11-15", assignment_key="signed-source")])])
    return data | changes


async def test_import_replay_and_immutable_correction_use_one_stable_person(session):
    actor = await principal(session)
    body = WorkforceImportInput(**payload())
    first = await import_workforce(session, actor=actor, body=body)
    assert await import_workforce(session, actor=actor, body=body) == first
    view = await availability(session, actor=actor)
    assert len(view["people"]) == 1 and view["sources"][0]["revision"] == 1
    stable = view["people"][0]["person_id"]
    assert view["people"][0]["intervals"][1]["allocation"] == "0.5"
    corrected = payload(expected_previous_batch_id=first["id"], source_as_of="2026-10-02T00:00:00Z")
    corrected["people"][0]["display_name"] = "Corrected display name"
    second = await import_workforce(session, actor=actor, body=WorkforceImportInput(**corrected))
    view = await availability(session, actor=actor)
    assert second["revision"] == 2 and second["id"] != first["id"]
    assert view["people"][0]["person_id"] == stable
    assert view["people"][0]["display_name"] == "Corrected display name"
    assert await session.scalar(select(func.count()).select_from(WorkforceVersion)) == 2


async def test_explicit_empty_full_snapshot_removes_current_supply_not_history(session):
    actor = await principal(session)
    first = await import_workforce(session, actor=actor, body=WorkforceImportInput(**payload()))
    await import_workforce(session, actor=actor, body=WorkforceImportInput(**payload(
        expected_previous_batch_id=first["id"], people=[])))
    view = await availability(session, actor=actor)
    assert view["people"] == [] and view["sources"][0]["revision"] == 2
    assert await session.scalar(select(func.count()).select_from(WorkforceVersion)) == 1


async def test_test_identities_cannot_publish_or_read_real_workforce_supply(session):
    actor = await principal(session)
    body = WorkforceImportInput(**payload())
    await import_workforce(session, actor=actor, body=body)
    test_actor = replace(actor, groups=("HR", "officeapp-e2e"))
    assert (await availability(session, actor=test_actor))["people"] == []
    await import_workforce(session, actor=test_actor, body=body)
    assert len((await availability(session, actor=actor))["people"]) == 1
    assert len((await availability(session, actor=test_actor))["people"]) == 1
    assert await session.scalar(select(func.count()).select_from(PeopleImportBatch)) == 2


@pytest.mark.parametrize("conflict", ["request", "version", "source_time"])
async def test_conflicting_import_cannot_change_supply_or_append_a_batch(session, conflict):
    actor = await principal(session)
    data = payload()
    first = await import_workforce(session, actor=actor, body=WorkforceImportInput(**data))
    changed = data | {"reason": "An explicit conflicting update"}
    if conflict != "request":
        changed["request_key"] = str(uuid.uuid4())
    if conflict == "source_time":
        changed.update(expected_previous_batch_id=first["id"], source_as_of="2026-09-30T12:00:00Z")
    with pytest.raises(HTTPException) as error:
        await import_workforce(session, actor=actor, body=WorkforceImportInput(**changed))
    assert error.value.status_code == 409
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(PeopleImportBatch)) == 1


async def test_named_supply_requires_hr_and_is_tenant_and_environment_scoped(session, monkeypatch):
    actor = await principal(session)
    body = WorkforceImportInput(**payload())
    await import_workforce(session, actor=actor, body=body)
    for role in ("Sales", "Delivery", "Finance", "CEO", "Legal"):
        denied = replace(actor, groups=(role,))
        for operation in (lambda: import_workforce(session, actor=denied, body=body),
                          lambda: availability(session, actor=denied)):
            with pytest.raises(HTTPException) as error:
                await operation()
            assert error.value.status_code == 403
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert (await availability(session, actor=actor))["people"] == []
    monkeypatch.setenv("DEALGATE_TENANT_ID", "people-import-test")
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    assert (await availability(session, actor=actor))["people"] == []


@pytest.mark.parametrize("fault", ["float", "net_basis", "salary", "overlap", "duplicate_person", "timezone", "naive_time"])
def test_invalid_or_financial_import_payload_rejects_whole_document(fault):
    data = payload()
    person = data["people"][0]
    if fault == "float": person["intervals"][0]["allocation"] = 0.5
    elif fault == "net_basis": data["basis"] = "net_available"
    elif fault == "salary": person["salary"] = "100000"
    elif fault == "overlap": person["intervals"].append(person["intervals"][0].copy())
    elif fault == "duplicate_person": data["people"].append(person.copy())
    elif fault == "timezone": person["timezone"] = "unknown"
    elif fault == "naive_time": data["source_as_of"] = datetime(2026, 10, 1)
    with pytest.raises(ValidationError):
        WorkforceImportInput(**data)
