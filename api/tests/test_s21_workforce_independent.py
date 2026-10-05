"""Independent managed-supply boundaries; private FK-enabled SQLite, no live proof."""

import uuid
from copy import deepcopy
from dataclasses import replace
from decimal import localcontext

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import AuthUser
from app.db.base import Base
from app.models.people_planning import PeopleImportBatch, PeopleSource, WorkforcePerson, WorkforceVersion
from app.models.user import User
from app.services.people_planning import WorkforceImportInput, availability, import_history, import_workforce


@pytest.fixture(autouse=True)
def private_scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "qa-workforce-independent")
    monkeypatch.setenv("DEALGATE_ENV", "local")


@pytest_asyncio.fixture
async def engine():
    database = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(database.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        await database.dispose()


async def hr(session):
    identity = uuid.uuid4()
    user = User(id=identity, email=f"{identity}@example.test", name="Independent HR", groups=["HR"])
    session.add(user)
    await session.commit()
    return AuthUser(id=identity, email=user.email, name=user.name, groups=("HR",))


def person(key="one", allocation="1"):
    return dict(person_key=key, display_name=f"Synthetic {key}", role="Engineer",
        skills=["python"], level="senior", location="US", timezone="America/Los_Angeles",
        evidence=[f"synthetic-roster:{key}"], intervals=[dict(kind="gross", allocation=allocation,
            start_date="2026-11-01", end_date="2026-11-30")])


def payload(**changes):
    return dict(source_system="independent-roster", request_key=str(uuid.uuid4()),
        expected_previous_batch_id=None, source_as_of="2026-10-01T00:00:00Z",
        reason="Independent gross roster with authoritative dated assignment evidence",
        basis="gross_with_commitments", people=[person()]) | changes


async def save(session, actor, data):
    return await import_workforce(session, actor=actor, body=WorkforceImportInput(**data))


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize("allocation", ["0.123456789012345678901", "0.000000000001"])
async def test_exact_fraction_survives_managed_import_and_named_source_projection(session, allocation):
    actor = await hr(session)
    await save(session, actor, payload(people=[person(allocation=allocation)]))
    view = await availability(session, actor=actor)
    assert view["people"][0]["intervals"][0]["allocation"] == allocation


async def test_serialization_is_not_rounded_by_the_callers_decimal_context(session):
    actor = await hr(session)
    await save(session, actor, payload(people=[person(allocation="0.125")]))
    with localcontext() as context:
        context.prec = 2
        view = await availability(session, actor=actor)
    assert view["people"][0]["intervals"][0]["allocation"] == "0.125"


async def test_omission_reintroduction_and_delayed_replay_preserve_one_current_snapshot(session):
    actor = await hr(session)
    original = payload(people=[person("one"), person("two")])
    first = await save(session, actor, original)
    first_view = await availability(session, actor=actor)
    stable = {row["display_name"]: row["person_id"] for row in first_view["people"]}
    second = await save(session, actor, payload(expected_previous_batch_id=first["id"],
        source_as_of="2026-10-01T01:00:00Z", people=[person("one", "0.5")]))
    assert await save(session, actor, original) == first
    current = await availability(session, actor=actor)
    assert current["sources"][0]["id"] == second["id"]
    assert [row["display_name"] for row in current["people"]] == ["Synthetic one"]
    assert current["people"][0]["intervals"][0]["allocation"] == "0.5"
    third = await save(session, actor, payload(expected_previous_batch_id=second["id"],
        source_as_of="2026-10-01T02:00:00Z", people=[person("two")]))
    current = await availability(session, actor=actor)
    assert current["people"][0]["person_id"] == stable["Synthetic two"]
    assert current["people"][0]["batch_id"] == third["id"]
    assert await count(session, WorkforcePerson) == 2
    assert await count(session, WorkforceVersion) == 4
    history = await import_history(session, actor=actor, page=2, size=1)
    assert history["total"] == 3 and len(history["items"]) == 1


async def test_empty_snapshot_does_not_clear_another_source_or_reintroduce_old_people(session):
    actor = await hr(session)
    first = await save(session, actor, payload())
    other = await save(session, actor, payload(source_system="other-roster", people=[person("other")]))
    await save(session, actor, payload(expected_previous_batch_id=first["id"], people=[]))
    current = await availability(session, actor=actor)
    assert [(row["display_name"], row["source_system"], row["batch_id"]) for row in current["people"]] == [
        ("Synthetic other", "other-roster", other["id"])]
    assert len(current["sources"]) == 2 and await count(session, WorkforceVersion) == 2


@pytest.mark.parametrize("fault", ["old_source_time", "old_predecessor", "conflicting_replay", "future"])
async def test_rejected_revision_leaves_latest_and_history_unchanged(session, fault):
    actor = await hr(session)
    data = payload()
    first = await save(session, actor, data)
    bad = payload(expected_previous_batch_id=first["id"], people=[])
    expected_status = 409
    if fault == "old_source_time":
        bad["source_as_of"] = "2026-09-30T00:00:00Z"
    elif fault == "old_predecessor":
        bad["expected_previous_batch_id"] = None
    elif fault == "conflicting_replay":
        bad["request_key"] = data["request_key"]
    else:
        bad["source_as_of"] = "2099-01-01T00:00:00Z"
        expected_status = 422
    with pytest.raises(HTTPException) as error:
        await save(session, actor, bad)
    assert error.value.status_code == expected_status
    await session.rollback()
    assert await count(session, PeopleImportBatch) == 1
    assert (await availability(session, actor=actor))["sources"][0]["id"] == first["id"]


@pytest.mark.parametrize("role", ["Sales", "Delivery", "Finance", "CEO", "Legal"])
async def test_denied_role_cannot_import_read_names_or_read_history(session, role):
    actor = await hr(session)
    data = payload()
    await save(session, actor, data)
    denied = replace(actor, groups=(role,))
    for operation in (lambda: save(session, denied, data),
        lambda: availability(session, actor=denied), lambda: import_history(session, actor=denied)):
        with pytest.raises(HTTPException) as error:
            await operation()
        assert error.value.status_code == 403
    assert await count(session, PeopleImportBatch) == 1


async def test_test_rosters_cannot_mix_with_real_named_supply_or_import_history(session):
    real = await hr(session)
    fixture = replace(real, groups=("HR", "officeapp-e2e"))
    data = payload(request_key="same-request")
    first = await save(session, real, data)
    assert (await availability(session, actor=fixture))["people"] == []
    assert (await import_history(session, actor=fixture))["total"] == 0
    second = await save(session, fixture, data)
    assert first["id"] != second["id"]
    for actor, expected in ((real, first), (fixture, second)):
        view = await availability(session, actor=actor)
        assert len(view["people"]) == 1 and view["people"][0]["batch_id"] == expected["id"]
        assert [row["id"] for row in (await import_history(session, actor=actor))["items"]] == [expected["id"]]


@pytest.mark.parametrize("key,value", [("DEALGATE_TENANT_ID", "foreign-tenant"), ("DEALGATE_ENV", "staging")])
async def test_same_source_and_request_key_remain_isolated_across_runtime_scope(session, monkeypatch, key, value):
    actor = await hr(session)
    data = payload(request_key="same-request")
    first = await save(session, actor, data)
    monkeypatch.setenv(key, value)
    assert (await availability(session, actor=actor))["people"] == []
    assert (await import_history(session, actor=actor))["total"] == 0
    second = await save(session, actor, data)
    assert second["id"] != first["id"]
    assert (await import_history(session, actor=actor))["total"] == 1
    assert await count(session, PeopleSource) == 2


async def test_invalid_second_person_rejects_whole_snapshot_without_partial_history(session):
    actor = await hr(session)
    first = await save(session, actor, payload())
    invalid = payload(expected_previous_batch_id=first["id"], people=[person("valid"), person("bad")])
    invalid["people"][1]["intervals"][0]["allocation"] = "1.01"
    with pytest.raises(ValidationError):
        await save(session, actor, invalid)
    assert await count(session, PeopleImportBatch) == 1
    assert await count(session, WorkforcePerson) == 1
    assert (await availability(session, actor=actor))["people"][0]["display_name"] == "Synthetic one"


@pytest.mark.parametrize("observation", [0, 1000000000.5])
def test_source_observation_requires_explicit_timezone_not_numeric_epoch_coercion(observation):
    with pytest.raises(ValidationError):
        WorkforceImportInput(**payload(source_as_of=observation))


@pytest.mark.parametrize("fault", ["float", "net_basis", "test_flag", "account_override", "cost", "overlap"])
def test_hostile_shapes_cannot_override_basis_provenance_or_financial_allowlist(fault):
    data = payload()
    row = data["people"][0]
    if fault == "float":
        row["intervals"][0]["allocation"] = 0.125
    elif fault == "net_basis":
        data["basis"] = "net_available"
    elif fault == "test_flag":
        data["test_fixture"] = False
    elif fault == "account_override":
        data["account_id"] = str(uuid.uuid4())
    elif fault == "cost":
        row["cost_rate"] = "123"
    else:
        row["intervals"].append(deepcopy(row["intervals"][0]))
    with pytest.raises(ValidationError):
        WorkforceImportInput(**data)
