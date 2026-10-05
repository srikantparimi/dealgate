"""Seed one declared CRM-note presentation fixture; not connector ingestion proof."""
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.deal_comment import DealComment
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.deal_comment import upsert_hubspot_note
from app.services.test_fixtures import account_scope


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert (parsed.hostname, parsed.port, parsed.path) == ("127.0.0.1", 55421, "/s21_journey")
    assert os.environ["DEALGATE_ENV"] == "local"
    assert os.environ["DEALGATE_TENANT_ID"] == "s21-lead"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            deal = await session.get(Opportunity, uuid.UUID(os.environ["S21_TRACKING_DEAL"]))
            assert deal and deal.source == "sow_upload" and deal.hubspot_deal_id is None
            owner = await session.get(User, deal.owner_id)
            assert owner and owner.email.startswith("s21-t11-") and owner.email.endswith("@example.test")
            assert {"SystemAdmin", "officeapp-e2e"} <= set(owner.groups)
            scope = await account_scope(session, deal.client_id, opportunity_id=deal.id)
            assert scope and owner.id in scope
            assert not await session.scalar(select(DealComment.id).where(DealComment.opportunity_id == deal.id).limit(1))
            note = await upsert_hubspot_note(session, opportunity_id=deal.id,
                hubspot_note_id=f"s21-t11-{uuid.uuid4()}",
                body="Synthetic CRM note <script>not executable</script>",
                author_name="Synthetic CRM Author", created_at=datetime(2026, 10, 2, 12, tzinfo=UTC))
            await session.commit()
            print(json.dumps({"note_id": str(note.id), "deal_id": str(deal.id),
                "fixture_kind": "synthetic_crm_note_presentation_not_connector_ingestion"}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
