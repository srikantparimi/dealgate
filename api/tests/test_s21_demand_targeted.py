"""Target checks may narrow I/O; allocation must retain the global population."""
from dataclasses import replace

from app.services.forecast_plans import save_plan
from app.services.people_demand import _source_rows, demand_sources
from tests.test_s21_people_company_x import (
    engine, isolated_scope, owner_and_account, plan_request, publish,
)  # noqa: F401


async def test_targeted_plan_reader_returns_exact_source_without_unrelated_rows(session):
    owner, account = await owner_and_account(session)
    own = await save_plan(session, actor=owner, body=plan_request(account))
    await publish(session, owner, own)
    other, account2 = await owner_and_account(session, "Other account")
    other_version = await save_plan(session, actor=other, body=plan_request(account2))
    await publish(session, other, other_version)
    all_rows = (await demand_sources(session, actor=owner))["items"]
    selected = (await _source_rows(session, actor=owner, source_id=own.plan_id))["items"]
    assert len(all_rows) == 2
    assert selected == [row for row in all_rows if row["source_id"] == str(own.plan_id)]
    assert (await _source_rows(session, actor=replace(owner, groups=("Sales",)),
        source_id=other_version.plan_id))["items"] == []


async def test_targeted_source_cannot_cross_runtime(session, monkeypatch):
    owner, account = await owner_and_account(session)
    own = await save_plan(session, actor=owner, body=plan_request(account))
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert (await _source_rows(session, actor=owner, source_id=own.plan_id))["items"] == []
