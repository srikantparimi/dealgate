"""S7 A — NDA + MSA hard block at submit_package.

Every Given/When/Then in ``docs/backlog/s7-nda-msa-hard-block.md``
(section A). Uses the same fixture helpers as test_approvals.py so the
seed shape stays consistent across the suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from app.services.coverage_gate import check_msa_and_nda_executed
import pytest_asyncio
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client, LegalEntity
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.approvals import ApprovalError, submit_package
from app.services.coverage_gate import check_msa_and_nda_executed
from app.services.delivery_model import (
    GmModelPayload,
    ResourceLinePayload,
    create_gm_model_version,
)


# --- helpers ---------------------------------------------------------------


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


async def _seed_owner(session, email: str = "owner@smartek21.com") -> User:
    u = User(id=_uid(email), email=email, name=email.split("@")[0], groups=["Sales"])
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _passing_payload(sow_version_id: uuid.UUID) -> GmModelPayload:
    start = date(2026, 3, 1)
    end = date(2026, 8, 31)
    return GmModelPayload(
        engagement_type="tm",
        sow_version_id=sow_version_id,
        delivery_pattern="hybrid",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        resource_lines=[
            ResourceLinePayload(
                role="Engineer",
                seniority="senior",
                location="US",
                person_name="Alice",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("1000"),
                hourly_bill_rate=Decimal("200"),
                hourly_cost=Decimal("100"),
                validated_by=uuid.uuid4(),
            ),
            ResourceLinePayload(
                role="Engineer",
                seniority="senior",
                location="India",
                person_name="Bob",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("800"),
                hourly_bill_rate=Decimal("100"),
                hourly_cost=Decimal("40"),
                validated_by=uuid.uuid4(),
            ),
        ],
        cost_lines=[],
    )


async def _seed_client_with_agreements(
    session,
    *,
    kinds_executed: tuple[str, ...] = ("NDA", "MSA"),
    expiry: date = date(2030, 12, 31),
    extra_entities: int = 0,
    executed_per_extra: tuple[str, ...] = (),
) -> tuple[Client, list[LegalEntity]]:
    """Seed a client + N legal entities + executed agreements.

    ``kinds_executed`` are executed against the first entity. Additional
    entities can be seeded with ``extra_entities``; ``executed_per_extra``
    executes those kinds against each extra entity (multi-entity coverage
    scenario).
    """

    client = Client(
        id=uuid.uuid4(),
        name=f"Client {uuid.uuid4().hex[:6]}",
        hubspot_company_id=f"HS-{uuid.uuid4().hex[:6]}",
    )
    session.add(client)
    await session.flush()

    entities: list[LegalEntity] = []
    first = LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Entity 1")
    session.add(first)
    entities.append(first)
    for i in range(extra_entities):
        extra = LegalEntity(
            id=uuid.uuid4(), client_id=client.id, name=f"Entity {i + 2}"
        )
        session.add(extra)
        entities.append(extra)
    await session.flush()

    for kind in kinds_executed:
        session.add(
            Agreement(
                id=uuid.uuid4(),
                legal_entity_id=first.id,
                kind=kind,
                state="executed",
                effective_date=date(2026, 1, 1),
                expiry=expiry,
            )
        )
    for entity in entities[1:]:
        for kind in executed_per_extra:
            session.add(
                Agreement(
                    id=uuid.uuid4(),
                    legal_entity_id=entity.id,
                    kind=kind,
                    state="executed",
                    effective_date=date(2026, 1, 1),
                    expiry=expiry,
                )
            )
    await session.commit()
    return client, entities


async def _seed_opp_gm(
    session, owner: User, client_id: uuid.UUID | None
) -> tuple[Opportunity, SowVersion]:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-CG-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        client_id=client_id,
        governance_status="SOWDraft.confirmed",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/{uuid.uuid4()}.pdf",
        file_hash="cafef00d" * 8,
        extract_status="complete",
        extracted_fields={
            "scope_summary": {"value": "x", "page_ref": 1, "status": "confirmed"},
            "price": {"value": "1", "page_ref": 1, "status": "confirmed"},
        },
        confirmed_by=owner.id,
        confirmed_at=datetime.now(UTC),
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    await create_gm_model_version(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        payload=_passing_payload(version.id),
    )
    return opp, version


async def _count_packages(session) -> int:
    return len(
        list(
            (await session.execute(select(ApprovalPackage))).scalars().all()
        )
    )


async def _count_audits(session, action: str) -> int:
    return len(
        list(
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.action == action)
                )
            )
            .scalars()
            .all()
        )
    )


# --- acceptance tests ------------------------------------------------------


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")


async def test_no_agreements_blocks_with_both_missing(session):
    owner = await _seed_owner(session)
    client, _ = await _seed_client_with_agreements(session, kinds_executed=())
    opp, _v = await _seed_opp_gm(session, owner, client.id)

    with pytest.raises(ApprovalError) as exc:
        await check_msa_and_nda_executed(session, opp)
    assert exc.value.status_code == 409
    assert exc.value.detail == "MSA + NDA required (missing: NDA, MSA)"
    # No partial write: no approval_package row, no package.submitted audit.
    assert await _count_packages(session) == 0
    assert await _count_audits(session, "package.submitted") == 0


async def test_only_nda_executed_blocks_with_msa_missing(session):
    owner = await _seed_owner(session)
    client, _ = await _seed_client_with_agreements(
        session, kinds_executed=("NDA",)
    )
    opp, _v = await _seed_opp_gm(session, owner, client.id)

    with pytest.raises(ApprovalError) as exc:
        await check_msa_and_nda_executed(session, opp)
    assert exc.value.status_code == 409
    assert exc.value.detail == "MSA + NDA required (missing: MSA)"
    assert await _count_packages(session) == 0


async def test_both_executed_allows_submit(session):
    owner = await _seed_owner(session)
    client, _ = await _seed_client_with_agreements(
        session, kinds_executed=("NDA", "MSA")
    )
    opp, _v = await _seed_opp_gm(session, owner, client.id)

    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert pkg.status == "pending_delivery_hr"
    assert await _count_audits(session, "package.submitted") == 1


async def test_expired_msa_blocks_even_when_executed(session):
    owner = await _seed_owner(session)
    client, _ = await _seed_client_with_agreements(
        session,
        kinds_executed=("NDA", "MSA"),
        expiry=date(2020, 1, 1),  # long past
    )
    opp, _v = await _seed_opp_gm(session, owner, client.id)

    with pytest.raises(ApprovalError) as exc:
        await check_msa_and_nda_executed(session, opp)
    assert exc.value.status_code == 409
    # Both expired → detail lists both as missing.
    assert exc.value.detail == "MSA + NDA required (missing: NDA, MSA)"
    assert await _count_packages(session) == 0


async def test_multi_entity_client_passes_when_any_entity_has_both(session):
    """Coverage aggregates across the client's legal entities.

    Entity 1 has NDA only, Entity 2 has MSA only. The client as a whole
    is covered, per blueprint §6.2 Legal coverage model."""

    owner = await _seed_owner(session)
    client = Client(
        id=uuid.uuid4(),
        name="Multi-entity client",
        hubspot_company_id=f"HS-{uuid.uuid4().hex[:6]}",
    )
    session.add(client)
    await session.flush()
    e1 = LegalEntity(id=uuid.uuid4(), client_id=client.id, name="US")
    e2 = LegalEntity(id=uuid.uuid4(), client_id=client.id, name="India")
    session.add_all([e1, e2])
    await session.flush()
    session.add(
        Agreement(
            id=uuid.uuid4(),
            legal_entity_id=e1.id,
            kind="NDA",
            state="executed",
            expiry=date(2030, 12, 31),
        )
    )
    session.add(
        Agreement(
            id=uuid.uuid4(),
            legal_entity_id=e2.id,
            kind="MSA",
            state="executed",
            expiry=date(2030, 12, 31),
        )
    )
    await session.commit()

    opp, _v = await _seed_opp_gm(session, owner, client.id)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert pkg.status == "pending_delivery_hr"


async def test_legacy_sow_without_client_link_is_gated(session):
    """Legacy sow_versions have no client_id — gate still applies (rollout rule)."""

    owner = await _seed_owner(session)
    # Skip client link entirely to model the legacy shape.
    opp, _v = await _seed_opp_gm(session, owner, client_id=None)

    with pytest.raises(ApprovalError) as exc:
        await check_msa_and_nda_executed(session, opp)
    assert exc.value.status_code == 409
    assert exc.value.detail == "MSA + NDA required (missing: NDA, MSA)"
    assert await _count_packages(session) == 0
