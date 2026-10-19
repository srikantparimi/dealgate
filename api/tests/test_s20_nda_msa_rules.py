"""T15 + T41 · NDA/MSA rules are warn-only (S20 · W5, replaced by S24-AG1 T10).

The S20 skeletons here described an "on file" vs "verified" model that S17 removed and S24-AG1 replaced. The
rule now (directive "What Kanna decided" 3, docs/reference/openapi-agreements.yaml: "Nothing in this file
blocks any workflow: a missing agreement only produces a warning and a flag"):

* a net-new client past stage 1 with an NDA or MSA missing is FLAGGED (needs attention) in the client panel,
  the Agreements page, and the Pipeline / Command Center count (``agreement_status``, the one shared service);
* NOTHING is blocked: the client's SOW is submitted for approval (``approvals.submit_package``) and every
  reviewer, Legal included, decides (``approvals.decide``) through to ``ready_to_sign`` with no agreement on
  file, and the flag stays on the whole way (nothing clears it but a copy or a mark).

Signing (signature eligibility, the signed upload) is in test_s20_signature_nda_msa_rule.py, which reuses the
seed below. The client is net new the way staging will have it: the cutover is set, the client was stamped
net new, its HubSpot deal is at stage 3 and its SOW was created after the cutover. Synthetic names only.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.agreements import AgreementMark, AgreementsSettings
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client, LegalEntity
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.routers import pipeline as pipeline_routes  # registers every table the Pipeline route reads
from app.services import approval_routing
from app.services.agreement_status import needs_attention_count
from app.services.approvals import decide, submit_package
from app.services.delivery_model import GmModelPayload, ResourceLinePayload, create_gm_model_version
from app.services.hubspot_owners import HubspotOwner  # noqa: F401 — registers the table for create_all
from app.services.hubspot_properties import HubspotPropertyMapping  # noqa: F401 — same

PIPELINE_ID = "t10-pipeline"
STAGES = (  # HubSpot stage id, label, display order, closed (the staging shape)
    ("t10-s1", "1-Initial Contact/Prospecting", 0, False), ("t10-s2", "2-Qualification", 1, False),
    ("t10-s3", "3-Requirement/Fit Gap Analysis", 2, False), ("t10-s4", "4-Proposal", 3, False),
    ("t10-s5", "5-Negotiation", 4, False), ("t10-s6", "6-Contracting/Drive Commitment", 5, False),
    ("t10-s7", "7-Closed Won", 6, True), ("t10-s8", "8-Closed Lost", 7, True), ("t10-s9", "Hold", 8, False),
)
CLIENT_NAME = "Halcyon Robotics"
# The cutover (the first real batch run) was two weeks ago; everything about this deal happens after it.
CUTOVER = (datetime.now(UTC) - timedelta(days=14)).date()
REVIEWERS = (("delivery", "Delivery"), ("hr", "HR"), ("sales", "Sales"), ("finance", "Finance"),
             ("legal", "Legal"))


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)
    monkeypatch.delenv("DEALGATE_NOW", raising=False)
    monkeypatch.delenv("DEALGATE_TENANT_ID", raising=False)


@dataclass
class Flagged:
    """A net-new client past stage 1, with nothing on file, whose SOW is ready to submit."""

    client_id: uuid.UUID
    opportunity_id: uuid.UUID
    owner: User
    reviewers: dict[str, User]
    legal: AuthUser


async def _user(session, email: str, name: str, groups: list[str]) -> User:
    user = User(id=_uid(email), email=email, name=name, groups=groups)
    session.add(user)
    await session.flush()
    return user


def _passing_payload(sow_version_id: uuid.UUID) -> GmModelPayload:
    """US 50% + India 60% margin, above both floors, so no CEO exception is needed."""
    start, end = date(2026, 11, 1), date(2027, 4, 30)
    line = dict(role="Engineer", seniority="senior", allocation_pct=Decimal("1"), start_date=start, end_date=end,
                validated_by=uuid.uuid4())
    return GmModelPayload(
        engagement_type="tm", sow_version_id=sow_version_id, delivery_pattern="hybrid",
        contingency_pct=Decimal("5.00"), warranty_days=30, cost_lines=[],
        resource_lines=[
            ResourceLinePayload(**line, location="US", person_name="Avery", hours_billable=Decimal("1000"),
                                hourly_bill_rate=Decimal("200"), hourly_cost=Decimal("100")),
            ResourceLinePayload(**line, location="India", person_name="Bao", hours_billable=Decimal("800"),
                                hourly_bill_rate=Decimal("100"), hourly_cost=Decimal("40")),
        ],
    )


async def seed_flagged(session, *, stage: int = 3) -> Flagged:
    """The cutover, a client stamped net new at it, its HubSpot deal at ``stage``, a confirmed SOW created
    after the cutover and a passing GM model. No NDA, no MSA, no mark."""
    admin = await _user(session, "t10.admin@example.test", "Tao Admin", ["SystemAdmin"])
    owner = await _user(session, "t10.owner@example.test", "Olu Owner", ["Sales"])
    reviewers = {fn: await _user(session, f"t10.{fn}@example.test", f"{group} Reviewer", [group])
                 for fn, group in REVIEWERS}
    await _user(session, "t10.ceo@example.test", "Cara Ceo", ["CEO"])
    session.add(HubspotPipeline(id=PIPELINE_ID, label="T10 Pipeline", display_order=0, archived=False))
    await session.flush()
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order,
                                  is_closed=closed, probability=Decimal("0.10"), archived=False)
                     for sid, label, order, closed in STAGES])
    stamped_at = datetime.combine(CUTOVER, datetime.min.time(), tzinfo=UTC) + timedelta(hours=20)
    session.add(AgreementsSettings(id=1, cutover_date=CUTOVER, set_by=admin.id, set_at=stamped_at))
    client = Client(id=uuid.uuid4(), name=CLIENT_NAME, hubspot_company_id="t10-company-halcyon",
                    relationship="net_new", relationship_basis="none", relationship_set_by=admin.id,
                    relationship_set_at=stamped_at)
    session.add(client)
    await session.flush()
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Halcyon Robotics Inc."))
    sid, label, order, _closed = STAGES[stage - 1]
    opp = Opportunity(
        id=uuid.uuid4(), source="hubspot", hubspot_deal_id="t10-deal-halcyon", name="Halcyon platform build",
        owner_id=owner.id, client_id=client.id, governance_status="SOWDraft.confirmed",
        hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid, stage_label=label, sales_stage=label,
        stage_order=order, is_closed_won=False, is_closed_lost=False, amount=Decimal("145000"), currency="USD",
        close_date=date.today() + timedelta(days=30), hubspot_last_modified_at=datetime.now(UTC))
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner.id, file_s3_key=f"sow/{uuid.uuid4()}.pdf",
        file_hash="deadbeef" * 8, extract_status="complete",
        extracted_fields={"scope_summary": {"value": "Build a robot fleet console", "page_ref": 1,
                                            "status": "confirmed"},
                          "price": {"value": "145000", "page_ref": 1, "status": "confirmed"}},
        confirmed_by=owner.id, confirmed_at=datetime.now(UTC))
    session.add(version)
    await session.commit()
    await create_gm_model_version(session, opportunity_id=opp.id, actor_id=owner.id,
                                  payload=_passing_payload(version.id))
    legal = reviewers["legal"]
    return Flagged(client_id=client.id, opportunity_id=opp.id, owner=owner, reviewers=reviewers,
                   legal=AuthUser(legal.id, legal.email, legal.name, ("Legal",)))


def _provide(value):
    def provide():
        return value

    return provide


@asynccontextmanager
async def api_for(session, user: AuthUser, *routers, overrides: dict | None = None):
    """The given routers on this session, as ``user`` (no network, no auth stack); ``overrides`` replaces more
    dependencies (storage stubs)."""
    if not routers:
        from app.routers import agreements_workspace, client_agreements

        routers = (agreements_workspace.router, client_agreements.router)
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user
    for dependency, value in (overrides or {}).items():
        app.dependency_overrides[dependency] = _provide(value)

    async def _db():
        yield session

    app.dependency_overrides[get_session] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t10") as api:
        yield api


async def warning_of(session, seeded: Flagged) -> dict:
    """What the warning surfaces say about the client: its panel, the Agreements page filtered to Needs
    attention, the Pipeline's gap card (GET /pipeline/workspace) and the Command Center tile's count."""
    from app.routers import agreements_workspace, client_agreements

    async with api_for(session, seeded.legal, agreements_workspace.router, client_agreements.router,
                       pipeline_routes.router) as api:
        panel = (await api.get(f"/clients/{seeded.client_id}/agreements")).json()
        page = (await api.get("/agreements/workspace", params={"status": "attention"})).json()
        workspace = await api.get("/pipeline/workspace")
    assert workspace.status_code == 200, workspace.text
    card = next(c for c in page["cards"] if c["key"] == "needs_attention")
    return {
        "relationship": panel["relationship"], "requirement": panel["requirement"],
        "needs_attention": panel["needs_attention"], "nda": panel["nda"]["state"], "msa": panel["msa"]["state"],
        "missing_kinds": panel["missing_kinds"],
        "page": [row["name"] for row in page["items"]], "card": card["value"],
        "pipeline_card": workspace.json()["metrics"]["agreement_gap_clients"]["value"],
        "count": await needs_attention_count(session, seeded.legal),
    }


FLAGGED = {"relationship": "net_new", "requirement": "required", "needs_attention": True, "nda": "missing",
           "msa": "missing", "missing_kinds": ["NDA", "MSA"], "page": [CLIENT_NAME], "card": 1, "pipeline_card": 1,
           "count": 1}


async def nothing_on_file(session, client_id: uuid.UUID) -> bool:
    agreements = await session.scalar(select(func.count()).select_from(Agreement).where(Agreement.client_id == client_id))
    marks = await session.scalar(select(func.count()).select_from(AgreementMark).where(
        AgreementMark.client_id == client_id))
    return agreements == 0 and marks == 0


async def approve_all(session, seeded: Flagged, package_id: uuid.UUID) -> ApprovalPackage:
    """Delivery, HR and Sales, then Finance and Legal approve: every reviewer decides with no agreement on file."""
    package = None
    for function in ("delivery", "hr", "sales", "finance", "legal"):
        package = await decide(session, actor_id=seeded.reviewers[function].id, package_id=package_id,
                               function=function, decision="approve", reason=f"{function} reviewed the SOW")
    return package


async def ready_to_sign(session) -> tuple[Flagged, ApprovalPackage]:
    seeded = await seed_flagged(session)
    package = await submit_package(session, actor_id=seeded.owner.id, opportunity_id=seeded.opportunity_id)
    package = await approve_all(session, seeded, package.id)
    assert package.status == "ready_to_sign"
    return seeded, package


# --- the warning ------------------------------------------------------------------------------------------


async def test_a_net_new_client_past_stage_1_with_nothing_on_file_is_flagged(session):
    seeded = await seed_flagged(session)
    assert await warning_of(session, seeded) == FLAGGED
    # The same client one stage earlier is only "due at stage 2": no flag, nothing to do yet.
    await session.execute(Opportunity.__table__.update().where(Opportunity.id == seeded.opportunity_id).values(
        hubspot_stage_id=STAGES[0][0], stage_label=STAGES[0][1], sales_stage=STAGES[0][1], stage_order=0))
    await session.commit()
    early = await warning_of(session, seeded)
    # The SOW created after the cutover still makes it required (directive: "an SOW or engagement created after
    # the cutover"), so the flag stays while the deal is back at stage 1.
    assert (early["requirement"], early["needs_attention"], early["count"]) == ("required", True, 1)
    assert early["pipeline_card"] == early["card"] == 1  # the Pipeline's gap card is the same number
    await session.execute(Sow.__table__.update().values(archived_at=datetime.now(UTC)))  # an archived SOW
    await session.commit()
    no_sow = await warning_of(session, seeded)
    assert (no_sow["requirement"], no_sow["nda"], no_sow["needs_attention"], no_sow["count"]) == (
        "later", "due_later", False, 0)
    assert no_sow["pipeline_card"] == no_sow["card"] == 0


# --- nothing is blocked -----------------------------------------------------------------------------------


async def test_the_sow_is_submitted_for_approval_with_no_agreement_on_file(session):
    seeded = await seed_flagged(session)
    plan = await approval_routing.submission_plan(session, actor_id=seeded.owner.id,
                                                  opportunity_id=seeded.opportunity_id)
    blockers = [row["blocker"] for row in plan["rows"] if row["blocker"]]
    assert blockers == []  # no routing blocker, and none that names an NDA, an MSA or an agreement
    assert not any(word in str(plan).upper() for word in ("NDA", "MSA", "AGREEMENT"))
    package = await submit_package(session, actor_id=seeded.owner.id, opportunity_id=seeded.opportunity_id)
    assert package.status == "pending_delivery_hr" and package.submitted_by == seeded.owner.id
    assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.action == "package.submitted")) == 1
    # Warn only: the submission neither cleared the warning nor created an agreement or a mark.
    assert await nothing_on_file(session, seeded.client_id)
    assert await warning_of(session, seeded) == FLAGGED


async def test_every_reviewer_decides_and_legal_approves_with_no_agreement_on_file(session):
    seeded = await seed_flagged(session)
    package = await submit_package(session, actor_id=seeded.owner.id, opportunity_id=seeded.opportunity_id)
    statuses = []
    for function in ("delivery", "hr", "sales", "finance", "legal"):
        package = await decide(session, actor_id=seeded.reviewers[function].id, package_id=package.id,
                               function=function, decision="approve", reason=f"{function} reviewed the SOW")
        statuses.append(package.status)
    assert statuses == ["pending_delivery_hr", "pending_delivery_hr", "pending_finance_legal",
                        "pending_finance_legal", "ready_to_sign"]
    decided = (await session.scalars(select(AuditEvent.action).where(
        AuditEvent.action.like("approval.%.approve")))).all()
    assert sorted(decided) == sorted(f"approval.{fn}.approve" for fn in ("delivery", "hr", "sales", "finance",
                                                                          "legal"))
    assert await nothing_on_file(session, seeded.client_id)
    assert await warning_of(session, seeded) == FLAGGED
    assert (await session.get(Client, seeded.client_id)).relationship == "net_new"
