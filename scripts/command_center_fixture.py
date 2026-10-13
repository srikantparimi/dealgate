"""Seed the isolated local Command Center browser fixture.

This script refuses every target except the dedicated local database. It
creates source records only; the browser and API exercise the production read
models, forecast engine, filters and navigation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "command-center-owner@example.test"
DATABASE = "dealgate_command_center"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def configuration():
    require(os.environ.get("DEALGATE_ENV") == "local", "DEALGATE_ENV must be local")
    url = make_url(os.environ["COMMAND_CENTER_DATABASE_URL"])
    require(
        url.drivername == "postgresql+asyncpg"
        and url.host == "127.0.0.1"
        and url.port == 55432
        and url.database == DATABASE,
        "The fixture only runs against the dedicated local Command Center database",
    )
    os.environ.update(
        POSTGRES_URL=str(url),
        AWS_EC2_METADATA_DISABLED="true",
        PYTHONDONTWRITEBYTECODE="1",
    )
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    return url


async def seed(url) -> dict[str, object]:
    from app.models.client import Client
    from app.models.engagement import Allocation, Engagement, EngagementCost, Resource
    from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
    from app.models.next_action import NextAction
    from app.models.opportunity import Opportunity
    from app.models.user import User
    from app.services.hubspot_properties import HubspotPropertyMapping

    engine = create_async_engine(url)
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "dealgate:command-center-fixture")
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{EMAIL}")
    now = datetime(2026, 10, 13, 7, 30, tzinfo=UTC)

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            existing = await session.scalar(select(User).where(User.email == EMAIL))
            if existing is not None:
                mapping = await session.get(HubspotPropertyMapping, "business_unit")
                if mapping is None:
                    session.add(
                        HubspotPropertyMapping(
                            key="business_unit",
                            internal_name="business_unit",
                            object_type="deal",
                            label="Business unit",
                            field_type="enumeration",
                            options=[
                                {
                                    "value": "ST21",
                                    "label": "ST21",
                                    "displayOrder": 0,
                                    "hidden": False,
                                }
                            ],
                            availability_state="configured",
                            mapping_version=1,
                            checked_at=now,
                            last_success_at=now,
                        )
                    )
                fixture_opportunities = (
                    await session.scalars(
                        select(Opportunity).where(
                            Opportunity.hubspot_pipeline_id == "cc-primary"
                        )
                    )
                ).all()
                for opportunity in fixture_opportunities:
                    opportunity.business_unit_mapping_version = 1
                    opportunity.business_unit_observed_at = now
                await session.commit()
                clients = int(await session.scalar(select(func.count()).select_from(Client)) or 0)
                return {"status": "already_seeded", "clients": clients, "actor": EMAIL}

            require(
                int(await session.scalar(select(func.count()).select_from(Client)) or 0) == 0,
                "The dedicated fixture database must be empty before its first seed",
            )

            actor = User(
                id=actor_id,
                email=EMAIL,
                name="Command Owner",
                groups=["SystemAdmin", "Sales", "Finance", "Delivery", "HR"],
            )
            pipeline = HubspotPipeline(
                id="cc-primary", label="Command Center Sales", display_order=10, archived=False
            )
            mapping = HubspotPropertyMapping(
                key="business_unit",
                internal_name="business_unit",
                object_type="deal",
                label="Business unit",
                field_type="enumeration",
                options=[
                    {
                        "value": "ST21",
                        "label": "ST21",
                        "displayOrder": 0,
                        "hidden": False,
                    }
                ],
                availability_state="configured",
                mapping_version=1,
                checked_at=now,
                last_success_at=now,
            )
            session.add_all([actor, pipeline, mapping])
            stages: list[HubspotStage] = []
            probabilities = ("0.05", "0.15", "0.30", "0.45", "0.65", "0.85", "1.00")
            for index, probability in enumerate(probabilities, start=1):
                stage = HubspotStage(
                    id=f"cc-stage-{index}",
                    pipeline_id=pipeline.id,
                    label=f"Sales stage {index}",
                    display_order=index * 10,
                    is_closed=index == 7,
                    probability=Decimal(probability),
                    archived=False,
                )
                stages.append(stage)
                session.add(stage)
            await session.flush()

            opportunities: list[Opportunity] = []
            definitions = (
                ("Stage Four Account", 4, "120000", "Discovery review", date(2026, 11, 4), False),
                ("Stage Five Account", 5, "90000", "Confirm delivery start", date(2026, 11, 5), False),
                ("Stage Six Account", 6, "200000", "Complete commercial review", date(2026, 11, 6), False),
                ("Historical Won Account", 7, "78736", "Create delivery release", date(2025, 10, 2), True),
            )
            for label, stage_number, amount, next_action, close_date, is_closed_won in definitions:
                key = label.lower().replace(" ", "-")
                client = Client(
                    id=uuid.uuid5(namespace, f"client:{key}"),
                    name=label,
                    hubspot_company_id=f"cc-company-{stage_number}",
                    business_unit_value="ST21",
                    hubspot_last_seen_at=now,
                )
                opportunity = Opportunity(
                    id=uuid.uuid5(namespace, f"opportunity:{key}"),
                    source="hubspot",
                    hubspot_deal_id=f"cc-deal-{stage_number}",
                    client_id=client.id,
                    primary_client_id=client.id,
                    owner_id=actor.id,
                    business_unit_value="ST21",
                    business_unit_mapping_version=1,
                    business_unit_observed_at=now,
                    sales_stage=stages[stage_number - 1].id,
                    governance_status="Intake",
                    next_client_action=next_action,
                    next_client_date=date(2026, 10, 12 + stage_number),
                    amount=Decimal(amount),
                    close_date=close_date,
                    stage_label=stages[stage_number - 1].label,
                    name=f"{label} expansion",
                    hubspot_pipeline_id=pipeline.id,
                    hubspot_stage_id=stages[stage_number - 1].id,
                    stage_order=stage_number * 10,
                    is_closed_won=is_closed_won,
                    is_closed_lost=False,
                    currency="USD",
                    hubspot_last_seen_at=now,
                    hubspot_last_activity_at=now,
                    hubspot_last_modified_at=now,
                )
                session.add_all([client, opportunity])
                opportunities.append(opportunity)
            await session.flush()

            stage_five = opportunities[1]
            action = NextAction(
                opportunity_id=stage_five.id,
                description="Confirm delivery start",
                title="Confirm delivery start",
                owner_user_id=actor.id,
                assignee_user_id=actor.id,
                due_date=date(2026, 10, 10),
                status="open",
                created_by=actor.id,
            )
            engagement = Engagement(
                id=uuid.uuid5(namespace, "engagement:stage-five"),
                client_id=stage_five.client_id,
                opportunity_id=stage_five.id,
                hubspot_deal_id=stage_five.hubspot_deal_id,
                name="Stage Five signed delivery",
                type="fixed_cost",
                start=date(2026, 10, 1),
                end=date(2026, 12, 31),
                total_price=Decimal(90000),
                currency="USD",
                same_dates_for_all=True,
                owner_user_id=actor.id,
                business_unit="ST21",
                sales_owner="Command Owner",
                delivery_owner="Delivery Owner",
            )
            resource = Resource(
                id=uuid.uuid5(namespace, "resource:consultant"),
                name="Fixture Consultant",
                location="US",
                employment_type="w2_employee",
                seniority="Senior",
            )
            session.add_all([action, engagement, resource])
            await session.flush()
            session.add_all(
                [
                    Allocation(
                        engagement_id=engagement.id,
                        resource_id=resource.id,
                        role="Consultant",
                        seniority="Senior",
                        location="US",
                        employment_type="w2_employee",
                        utilization=Decimal(1),
                        cost_per_hour=Decimal(50),
                        rate_basis="hourly",
                    ),
                    EngagementCost(
                        engagement_id=engagement.id,
                        description="Delivery software",
                        category="software",
                        amount=Decimal(3000),
                        frequency="one_time",
                        billed_to_client=False,
                    ),
                ]
            )
            await session.commit()
            return {
                "status": "seeded",
                "actor": EMAIL,
                "stage4": str(opportunities[0].id),
                "stage5": str(opportunities[1].id),
                "stage6": str(opportunities[2].id),
            }
    finally:
        await engine.dispose()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(seed(configuration())), sort_keys=True))
