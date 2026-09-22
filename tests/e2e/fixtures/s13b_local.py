"""Isolated SQLite fixture server for the S13b browser proof.

Run from api/ with PYTHONPATH=. and POSTGRES_URL pointing to a disposable
SQLite file. Production databases and authentication modes are refused.
"""

import asyncio
import os
import uuid

import uvicorn
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.db import Base, DATABASE_URL, engine, session_factory
from app.main import app
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.delivery_model import create_gm_model_version, parse_gm_model_payload
from app.services.provenance import wrap


OPPORTUNITY_ID = uuid.UUID("13130000-0000-0000-0000-000000000001")
MIXED_ID = uuid.UUID("13130000-0000-0000-0000-000000000002")
EMAIL = "s13b-reviewer@example.test"
USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{EMAIL}")


async def seed():
    if os.environ.get("DEALGATE_ENV") != "local" or not DATABASE_URL.startswith("sqlite+"):
        raise RuntimeError("The S13b fixture server requires local mode and disposable SQLite")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        if await session.get(Opportunity, OPPORTUNITY_ID):
            return
        session.add(User(id=USER_ID, email=EMAIL, name="Finance Reviewer", groups=["SystemAdmin", "Finance", "Delivery", "CEO"]))
        client = Client(id=uuid.uuid4(), name="S13b fixture client")
        session.add(client)
        await session.flush()
        for opp_id, mixed in [(OPPORTUNITY_ID, False), (MIXED_ID, True)]:
            opp = Opportunity(id=opp_id, owner_id=USER_ID, client_id=client.id, source="manual", engagement_type="fixed_price", governance_status="SOWDraft")
            session.add(opp)
            sow = Sow(id=uuid.uuid4(), opportunity_id=opp_id, version_counter=1)
            session.add(sow)
            await session.flush()
            raw = {
                "client_legal_name": client.name, "client_domain": "example.test",
                "scope_summary": "Finance GM acceptance fixture",
                "price": "50000", "currency": "USD", "billing_basis": "fixed_price",
                "billing_basis_normalized": "fixed_price", "engagement_type_suggested": "fixed_price",
                "term_start": "2026-10-01", "term_end": "2026-12-31", "notice_date": "2026-12-01",
                "deliverables": ["Delivery report"], "milestones": ["Final delivery"],
                "acceptance_criteria": "Client sign-off", "assumptions": "Client access available",
                "exclusions": "Taxes", "signatories": [{"source": "internal", "name": "Finance Reviewer", "email": EMAIL, "user_id": str(USER_ID)}],
            }
            version = SowVersion(
                id=uuid.uuid4(), sow_id=sow.id, uploaded_by=USER_ID, version_no=1,
                file_s3_key="s13b/fixture.pdf", file_hash=f"s13b-{opp_id}",
                extracted_fields={key: wrap(value, provenance="extracted", page_ref=1, status="confirmed") for key, value in raw.items()},
                extract_status="confirmed", engagement_type_confirmed="fixed_price",
            )
            session.add(version)
            await session.flush()
            rows = [{
                "role": "SME", "seniority": "Senior", "location": "India" if mixed and i else "US",
                "person_name": None, "allocation_pct": "1", "start_date": "2026-10-01",
                "end_date": "2026-12-31", "hours_billable": hours,
                "hourly_bill_rate": "0", "hourly_cost": "120", "validated_by": str(USER_ID),
            } for i, hours in enumerate(["80", "160"])]
            await create_gm_model_version(session, opportunity_id=opp_id, actor_id=USER_ID, payload=parse_gm_model_payload({
                "engagement_type": "fixed_price", "sow_version_id": str(version.id),
                "total_price": "50000", "resource_lines": rows, "cost_lines": [],
            }))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5174", "http://localhost:5174"], allow_methods=["*"], allow_headers=["*"])
    uvicorn.run(app, host="127.0.0.1", port=8014)
