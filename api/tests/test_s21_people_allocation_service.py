"""T22: global capacity is allocated before portfolio display filters."""
import uuid
from dataclasses import replace
from decimal import Decimal

from app.gm.demand_source import line_key
from app.models.client import Client
from app.models.user import User
from app.services.forecast_plans import save_plan
from app.services.people_allocation import demand_allocation
from app.services.people_demand import publish_plan_demand
from app.services.people_planning import WorkforceImportInput, import_workforce
from tests.test_s21_demand_publication import source, publication
from tests.test_s21_forecast_plans import scope  # noqa: F401
from tests.test_s21_people_imports import payload


async def prepared(session):
    user, request, first = await source(session, quantity=1, allocation=Decimal("1"))
    enrichments = {line_key("build", "team-1"): {"skills": ["python"], "level": "senior", "evidence": ["HR review"]}}
    await publish_plan_demand(session, actor=user, body=publication(first, enrichments=enrichments))
    roster = payload()
    roster["people"][0]["timezone"] = "America/New_York"
    roster["people"][0]["intervals"] = [roster["people"][0]["intervals"][0]]
    await import_workforce(session, actor=replace(user, groups=("HR",)), body=WorkforceImportInput(**roster))
    other = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Other synthetic owner", groups=["Delivery"])
    account = Client(id=uuid.uuid4(), name="Other synthetic account")
    session.add_all([other, account])
    await session.commit()
    second = await save_plan(session, actor=replace(user, id=other.id), body=request.model_copy(update={
        "account_id": account.id, "idempotency_key": uuid.uuid4()}))
    await publish_plan_demand(session, actor=replace(user, id=other.id), body=publication(second, enrichments=enrichments))
    return user, first, second


async def test_global_allocation_has_one_person_not_one_per_account(session):
    user, first, second = await prepared(session)
    result = await demand_allocation(session, actor=replace(user, groups=("HR",)))
    november = next(item for item in result["intervals"] if item["start"] == "2026-11-01")
    assert len(november["demands"]) == 2
    assert sum(Decimal(row["matched_fte"]) for row in november["demands"]) == 1
    assert sum(Decimal(row["gap_fte"]) for row in november["demands"]) == 1
    assert sum(row["quantity"] for row in november["demands"]) == 2
    assert len({row["id"] for row in november["demands"]}) == 2
    assert result["is_reservation"] is False
    assert result["sources"][0]["source_as_of"]
    assert result["source_watermark"]
    assert {row["plan_id"] for row in november["demands"]} == {str(first.plan_id), str(second.plan_id)}


async def test_sales_and_account_filters_do_not_reallocate_hidden_capacity(session):
    user, first, _ = await prepared(session)
    full = await demand_allocation(session, actor=replace(user, groups=("HR",)))
    own = await demand_allocation(session, actor=replace(user, groups=("Sales",)))
    assert own["scope_label"] == "My portfolio"
    assert str(first.plan_id) in str(own)
    for interval in own["intervals"]:
        original = next(item for item in full["intervals"] if item["start"] == interval["start"])
        for row in interval["demands"]:
            assert row["plan_id"] == str(first.plan_id)
            expected = next(item for item in original["demands"] if item["id"] == row["id"])
            assert row["matched_fte"] == expected["matched_fte"] and row["gap_fte"] == expected["gap_fte"]
            assert "matches" not in row and "retained_person_ids" not in row
        assert "overcommitted_person_ids" not in interval
    assert own["sources"] == []
    assert "Other synthetic" not in str(own)
    assert all(item["peak_headcount"] == 1 for item in own["months"])


async def test_pending_source_is_visible_as_incomplete_not_zero_demand(session):
    user, _, version = await source(session)
    result = await demand_allocation(session, actor=user)
    assert result["complete"] is False
    assert result["pending_sources"] == [str(version.plan_id)]
    assert result["months"] == []
    assert "supply_source" in result["missing"]
