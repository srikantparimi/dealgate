"""Canonical commercial sources must survive release and source deletion."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.gm_model import GmModel
from app.services.project_lifecycle import _baseline_snapshot


def test_release_freezes_canonical_inputs_and_calculation_by_value():
    inputs = {"profile": "fixed", "staffing": [{"assignment_id": "us-team", "quantity": 2}],
              "evidence": ["Synthetic approved source"]}
    calculation = {"complete": True, "revenue_total": "420000.00",
                   "cost_total": "115584.00", "policy_version": "gm-1"}
    expected_inputs, expected_calculation = deepcopy(inputs), deepcopy(calculation)
    gm = GmModel(id=uuid4(), version=2, engagement_type="fixed", resource_lines=[],
                 commercial_inputs=inputs, commercial_snapshot=calculation)
    result = _baseline_snapshot(package=SimpleNamespace(id=uuid4()),
        opportunity=SimpleNamespace(id=uuid4()),
        sow_version=SimpleNamespace(id=uuid4(), version_no=1, extracted_fields={}), gm_model=gm)
    assert result["commercial_inputs"] == expected_inputs
    assert result["commercial_snapshot"] == expected_calculation
    inputs["staffing"][0]["quantity"] = 99
    calculation["cost_total"] = "0"
    assert result["commercial_inputs"] == expected_inputs
    assert result["commercial_snapshot"] == expected_calculation


def test_legacy_baseline_does_not_invent_canonical_economics():
    gm = GmModel(id=uuid4(), version=1, engagement_type="fixed", resource_lines=[])
    result = _baseline_snapshot(package=SimpleNamespace(id=uuid4()),
        opportunity=SimpleNamespace(id=uuid4()),
        sow_version=SimpleNamespace(id=uuid4(), version_no=1, extracted_fields={}), gm_model=gm)
    assert result["commercial_inputs"] is None
    assert result["commercial_snapshot"] is None


@pytest.mark.parametrize("role,visible", [("HR", False), ("Sales", False), ("Legal", False),
                                         ("Delivery", True), ("Finance", True), ("CEO", True)])
async def test_live_project_baseline_uses_same_cost_boundary_as_retained(session, role, visible):
    from datetime import UTC, datetime
    from app.auth import AuthUser
    from app.models.approval import ApprovalPackage
    from app.models.project import Project
    from app.services.projects import list_projects
    from tests.test_deletion_by_state import _seed

    owner, deal, _ = await _seed(session, with_package=True)
    package = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.opportunity_id == deal.id))
    package.released_at = datetime.now(UTC)
    baseline = {"commercial_inputs": {"staffing": [{"cost_rate": "60"}]},
                "commercial_snapshot": {"cost_total": "115584"},
                "resource_lines": [{"hourly_cost": "60"}]}
    project = Project(id=uuid4(), opportunity_id=deal.id, client_id=deal.client_id,
        sow_version_id=package.sow_version_id, gm_model_id=package.gm_model_id,
        package_id=package.id, title="Synthetic approved project", baseline_snapshot_json=baseline)
    session.add(project)
    await session.commit()
    rows = await list_projects(session, actor=AuthUser(owner.id, owner.email, owner.name, (role,)))
    row = next(item for item in rows if item["project_id"] == str(project.id))
    assert row["baseline"] == (baseline if visible else None)
    assert project.baseline_snapshot_json == baseline
