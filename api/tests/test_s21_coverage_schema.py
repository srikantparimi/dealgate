"""Coverage schema pins two source versions and never becomes a financial fraction."""
from sqlalchemy import CheckConstraint, UniqueConstraint


def test_coverage_root_has_scoped_unique_source_pair():
    from app.models.people_coverage import DemandCoverageRoot
    table = DemandCoverageRoot.__table__
    assert {"tenant_id", "environment", "test_fixture", "plan_publication_id", "project_publication_id"} <= set(table.c.keys())
    assert any(isinstance(item, UniqueConstraint) and set(item.columns.keys()) == {
        "tenant_id", "environment", "plan_publication_id", "project_publication_id"} for item in table.constraints)


def test_coverage_history_binds_both_exact_publication_versions():
    from app.models.people_coverage import DemandCoverageVersion
    table = DemandCoverageVersion.__table__
    for field in ("plan_version_id", "project_version_id"):
        key = next(iter(table.c[field].foreign_keys))
        assert key.target_fullname == "demand_publication_version.id" and key.ondelete == "CASCADE"
    assert "scope_fraction" not in table.c
    assert {"mappings", "reason", "created_by", "created_at", "request_hash"} <= set(table.c.keys())


def test_coverage_revision_and_request_replay_are_independently_unique():
    from app.models.people_coverage import DemandCoverageVersion
    constraints = DemandCoverageVersion.__table__.constraints
    for fields in ({"root_id", "revision"}, {"root_id", "request_key"}):
        assert any(isinstance(item, UniqueConstraint) and set(item.columns.keys()) == fields for item in constraints)
    assert any(isinstance(item, CheckConstraint) and str(item.sqltext) == "revision > 0" for item in constraints)


def test_deleting_owned_publication_cascades_mapping_not_project():
    from app.models.people_coverage import DemandCoverageRoot
    for field in ("plan_publication_id", "project_publication_id"):
        key = next(iter(DemandCoverageRoot.__table__.c[field].foreign_keys))
        assert key.target_fullname == "demand_publication.id" and key.ondelete == "CASCADE"
