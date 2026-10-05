"""Projection repair edges beyond the unchanged independent QA cases."""

import pytest

from app.gm.commercial import HybridPricing
from app.gm.demand_source import project_staffing
from tests.test_s21_demand_source_independent import enrichment, hybrid, source


@pytest.mark.parametrize("version", ["", "2", "unsupported"])
def test_unregistered_profile_version_is_not_projected(version):
    original = source(profile_version=version, staffing=())
    with pytest.raises(ValueError, match="unsupported"):
        project_staffing(original)


@pytest.mark.parametrize("pricing", [None, source().pricing])
def test_hybrid_without_typed_children_is_rejected(pricing):
    with pytest.raises(ValueError, match="hybrid"):
        project_staffing(source(profile="hybrid", pricing=pricing))


def test_empty_hybrid_children_are_explicitly_missing_even_with_parent_staffing():
    result = project_staffing(source(profile="hybrid", pricing=HybridPricing(())), enrichment())
    assert "component:delivery:components" in result["missing"]
    assert result["lines"][0]["quantity"] == 2


def test_unknown_parent_bounds_do_not_invent_confirmed_containment():
    result = project_staffing(hybrid([source("child")], service_start=None, service_end=None), enrichment("child"))
    assert "component:root:service_start" in result["missing"]
    assert "component:root:service_end" in result["missing"]
    assert result["lines"][0]["quantity"] == 2


def test_unknown_child_bounds_do_not_inherit_parent_dates():
    child = source("child", service_start=None, service_end=None)
    result = project_staffing(hybrid([child]), enrichment("child"))
    row, = result["lines"]
    assert row["start_date"] is None and row["end_date"] is None
    assert {"start_date", "end_date"} <= set(row["missing"])


def test_missing_source_evidence_remains_line_local_and_component_missing():
    result = project_staffing(source(source_evidence=()), enrichment())
    assert "source_evidence" in result["lines"][0]["missing"]
    assert "component:delivery:source_evidence" in result["missing"]


def test_nonhybrid_cannot_hide_empty_hybrid_shape():
    with pytest.raises(ValueError, match="hybrid"):
        project_staffing(source(pricing=HybridPricing(())))
