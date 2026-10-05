"""Release-created delivery and later capability edits feed the same sourcing outbox."""
import uuid

from sqlalchemy import func, select

from app.auth import AuthUser
from app.gm.demand_source import line_key
from app.models.automation import AutomationJob
from app.models.people_demand import DemandPublication, DemandPublicationVersion
from app.models.people_sourcing import SourcingDraftVersion
from app.models.user import User
from app.services.automation import RuleInput, save_rule
from app.services.automation_jobs import process_jobs
from app.services.people_project_demand import publish_project_demand
from app.services.people_sourcing import RulesInput, save_rules
from app.services.project_lifecycle import create_or_link
from tests.test_s21_project_demand import canonical, request  # noqa: F401
from tests.test_s21_project_scope_independent import engine  # noqa: F401
from tests.test_s21_people_company_x import import_roster


async def test_release_uses_fixture_source_classification_not_ordinary_reviewer_groups(session, monkeypatch):
    from tests.test_s21_project_scope_independent import prepared

    owner, _, _, _, _, _, package, _ = await prepared(session, monkeypatch, test_fixture=True, capture=False)
    actor = AuthUser(id=owner.id, email=owner.email, name=owner.name, groups=tuple(owner.groups))
    await save_rule(session, actor=actor, body=RuleInput(expected_version_id=None, request_key="fixture-rule",
        enabled=True, reason="Refresh only authorized fixture sources"))
    reviewer = User(id=uuid.uuid4(), email="ordinary-reviewer@example.test", name="Ordinary reviewer", groups=["Legal"])
    session.add(reviewer)
    await session.flush()
    project, created = await create_or_link(session, actor_id=reviewer.id, package=package)
    await session.commit()
    jobs = (await session.scalars(select(AutomationJob))).all()
    assert created is True and len(jobs) == 1
    assert jobs[0].project_id == project.id
    assert jobs[0].event_key == f"project:{project.id}"


async def test_release_and_reviewed_capability_emit_source_events_without_invented_staffing(session, canonical):  # noqa: F811
    owner, _, _, _, package = canonical
    owner.groups = ["SystemAdmin"]
    legal = User(id=uuid.uuid4(), email="release-reviewer@example.test", name="Synthetic legal", groups=["Legal"])
    session.add(legal)
    await session.commit()
    actor = AuthUser(id=owner.id, email=owner.email, name=owner.name, groups=("SystemAdmin",))
    await import_roster(session, actor, [])
    await save_rules(session, actor=actor, body=RulesInput(expected_version_id=None, request_key="rules",
        reason="Reviewed lead times", rules=[{"skill": "python", "location": "US", "lead_days": 45}]))
    await save_rule(session, actor=actor, body=RuleInput(expected_version_id=None, request_key="enable",
        enabled=True, reason="Enable released staffing refresh"))
    assert await session.scalar(select(func.count()).select_from(AutomationJob)) == 0
    project, created = await create_or_link(session, actor_id=legal.id, package=package)
    assert created is True
    await session.commit()
    job = await session.scalar(select(AutomationJob))
    assert job is not None and job.project_id == project.id and job.status == "pending"
    assert await process_jobs(session) == 1
    await session.refresh(job)
    assert job.status == "review"
    draft = await session.scalar(select(SourcingDraftVersion))
    assert draft.snapshot["complete"] is False
    assert all(row["quantity"] == 2 and row["skills"] == [] for row in draft.snapshot["rows"])
    publication = await session.scalar(select(DemandPublication).where(DemandPublication.project_id == project.id))
    version = await session.scalar(select(DemandPublicationVersion).where(DemandPublicationVersion.publication_id == publication.id))
    await publish_project_demand(session, actor=actor, body=request(project,
        expected_publication_version_id=version.id, enrichments={line_key("build", "team-1"): {
            "skills": ["python"], "level": "senior", "evidence": ["Reviewed signed staffing capability"]}}))
    assert await process_jobs(session) == 1
    drafts = (await session.scalars(select(SourcingDraftVersion).order_by(SourcingDraftVersion.revision))).all()
    assert [row.revision for row in drafts] == [1, 2]
    assert drafts[1].snapshot["complete"] is True
    assert all(row["quantity"] == 2 and row["skills"] == ["python"] and row["sourcing_by"] == "2026-09-17"
        for row in drafts[1].snapshot["rows"])
    await create_or_link(session, actor_id=legal.id, package=package)
    await session.commit()
    assert await process_jobs(session) == 0
