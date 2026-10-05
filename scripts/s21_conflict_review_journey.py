"""Seed a declared review-state fixture, not live extractor quality evidence."""
import asyncio
import hashlib
import json
import os
import uuid
from urllib.parse import urlparse

from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.provenance import wrap
from app.services.test_fixtures import reviewer_scope
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname == "127.0.0.1" and parsed.port == 55421 and parsed.path == "/s21_journey"
    assert os.environ["DEALGATE_ENV"] == "local" and os.environ["DEALGATE_TENANT_ID"] == "s21-lead"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            deal = await session.get(Opportunity, uuid.UUID(os.environ["S21_REVIEW_DEAL"]))
            assert deal and deal.source == "sow_upload" and deal.hubspot_deal_id is None
            owner = await session.get(User, deal.owner_id)
            assert owner and {"SystemAdmin", "officeapp-e2e"} <= set(owner.groups)
            sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
            session.add(sow)
            await session.flush()
            values = {"client_entity": "Synthetic review client", "scope_summary": "Fixed assessment of synthetic systems",
                "price": "25000.00", "currency": "USD", "term_start": "2026-11-01", "term_end": "2026-11-30",
                "deliverables": "Synthetic assessment report", "signatories": [{"name": "Synthetic signer", "role": "Client"}],
                "billing_basis": "fixed_price", "engagement_type_suggested": "assessment", "sow_title": "Source conflict review"}
            fields = {name: wrap(value, provenance="manual", page_ref=1, status="confirmed") for name, value in values.items()}
            fields["metadata"] = {"reextract_conflicts": {"price": wrap("90000.00", provenance="extracted", page_ref=2, status="unconfirmed")}}
            missing_currency = os.environ.get("S21_REVIEW_MISSING_CURRENCY") == "1"
            if missing_currency:
                fields["currency"] = wrap(None, provenance="extracted", page_ref=2, status="disputed")
                fields["metadata"] = {"reextract_conflicts": {}}
            version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner.id,
                file_s3_key=f"synthetic-review/{sow.id}.pdf", file_hash=hashlib.sha256(str(sow.id).encode()).hexdigest(),
                extracted_fields=fields, extract_status="complete" if missing_currency else "manual_required", extract_model="seeded-review-fixture",
                extract_prompt_version="not-live-extraction", engagement_type_suggested="assessment",
                engagement_type_confirmed="assessment", extract_error=None if missing_currency else "Re-extraction conflicts with confirmed fields: price")
            session.add(version)
            await session.flush()
            scope = await reviewer_scope(session, version)
            assert scope and owner.id in scope
            await session.commit()
            print(json.dumps({"version_id": str(version.id), "sow_id": str(sow.id), "deal_id": str(deal.id),
                "fixture_kind": "seeded_conflict_review_not_extraction_quality"}))
    finally:
        await engine.dispose()


asyncio.run(main())
