"""Connected regressions from independent global-allocation review."""
from dataclasses import replace
from decimal import Decimal

from app.gm.demand_source import line_key
from app.services.forecast_plans import save_plan
from app.services.people_allocation import demand_allocation
from app.services.people_demand import publish_plan_demand
from app.services.people_planning import WorkforceImportInput, import_workforce
from tests.test_s21_demand_publication import source, publication
from tests.test_s21_forecast_plans import scope  # noqa: F401
from tests.test_s21_people_imports import payload


async def test_empty_published_staffing_does_not_become_complete_zero_demand(session):
    user, request, initial = await source(session)
    revised = await save_plan(session, actor=user, plan_id=initial.plan_id,
        body=request.model_copy(update={"expected_version_id": initial.id,
            "inputs": request.inputs | {"staffing": []}}))
    await publish_plan_demand(session, actor=user, body=publication(revised))
    await import_workforce(session, actor=replace(user, groups=("HR",)), body=WorkforceImportInput(**payload()))
    result = await demand_allocation(session, actor=user)
    assert result["complete"] is False
    assert any("staffing" in item for item in result["missing"])


async def test_unresolved_competing_population_is_not_hidden_by_owner_filter(session):
    import uuid
    from app.models.user import User
    user, _, _ = await source(session)
    outsider = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Other salesperson", groups=["Sales"])
    session.add(outsider)
    await session.commit()
    await import_workforce(session, actor=replace(user, groups=("HR",)), body=WorkforceImportInput(**payload()))
    result = await demand_allocation(session, actor=replace(user, id=outsider.id, groups=("Sales",)))
    assert result["complete"] is False and "global_demand_incomplete" in result["missing"]
    assert result["pending_sources"] == [] and result["intervals"] == []


async def test_exact_precision_overflow_is_explicit_not_server_error_or_rounded_total(session):
    user, _, version = await source(session, allocation=Decimal("0." + "9" * 28))
    await publish_plan_demand(session, actor=user, body=publication(version,
        enrichments={line_key("build", "team-1"): {"skills": ["python"], "level": "senior", "evidence": ["HR review"]}}))
    result = await demand_allocation(session, actor=user)
    assert result["complete"] is False and "allocation_precision" in result["missing"]
    assert result["months"] == [] and result["intervals"] == []


async def test_inactive_unpublished_plans_are_not_pending_recruiting_demand(session):
    user, request, initial = await source(session)
    await save_plan(session, actor=user, plan_id=initial.plan_id,
        body=request.model_copy(update={"expected_version_id": initial.id, "lifecycle": "closed_lost"}))
    await import_workforce(session, actor=replace(user, groups=("HR",)), body=WorkforceImportInput(**payload()))
    result = await demand_allocation(session, actor=user)
    assert result["pending_sources"] == [] and "global_demand_incomplete" not in result["missing"]
    scoped = await demand_allocation(session, actor=user, account_id=request.account_id)
    assert scoped["scope_label"] == "Selected account demand"
