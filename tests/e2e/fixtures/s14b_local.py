"""Disposable local database and distinct identities for S14b browser proof."""
import asyncio
import os
import uuid

import uvicorn
from app import models  # noqa: F401
from app.auth import AuthUser, current_user
from app.db import DATABASE_URL, Base, engine, session_factory
from app.main import app
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.approval_routing import save_group
from app.services.delivery_model import create_gm_model_version, parse_gm_model_payload
from app.services.provenance import wrap
from fastapi import Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

PEOPLE = {
    "owner": ("Morgan Owner", ["Sales", "SystemAdmin"]),
    "delivery": ("Dana Delivery", ["Delivery"]),
    "hr": ("Harper HR", ["HR"]),
    "finance": ("Frankie Finance", ["Finance"]),
    "legal": ("Lee Legal", ["Legal"]),
    "ceo": ("Cameron CEO", ["CEO"]),
}


def email(key):
    return f"s14b-{key}@example.test"


def uid(key):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email(key)}")


async def seed():
    if os.environ.get("DEALGATE_ENV") != "local" or not DATABASE_URL.startswith("sqlite+") or 's14b' not in DATABASE_URL:
        raise RuntimeError("Use a disposable s14b SQLite database in local mode")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        if await session.get(User, uid('owner')):
            return
        for key, (name, roles) in PEOPLE.items():
            session.add(User(id=uid(key), email=email(key), name=name, groups=roles))
        await session.commit()
        for fn in ('delivery', 'hr', 'finance', 'legal'):
            members = [str(uid(fn)), str(uid('owner'))] if fn == 'delivery' else [str(uid(fn))]
            await save_group(session, actor_id=uid('owner'), function=fn, member_ids=members, backup_ids=[], default_approver_id=uid(fn))
        for index, below in [(1, False), (2, True)]:
            client = Client(id=uuid.uuid4(), name=f"Peppermill S14b {'exception' if below else 'review'}", hubspot_company_id=f"s14b-{index}")
            session.add(client)
            await session.flush()
            opp = Opportunity(id=uuid.UUID(f"14140000-0000-0000-0000-{index:012d}"), owner_id=uid('owner'), client_id=client.id,
                              source='manual', engagement_type='fixed_price', governance_status='SOWDraft')
            session.add(opp)
            sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id, version_counter=1)
            session.add(sow)
            await session.flush()
            raw = {
                "sow_title": "Data platform modernization" + (" - exception" if below else ""),
                "client_legal_name": client.name, "client_domain": "example.test",
                "scope_summary": "Modernize the reporting platform and deliver the migration plan.",
                "price": "50000", "currency": "USD", "billing_basis": "fixed_price", "billing_basis_normalized": "fixed_price",
                "engagement_type_suggested": "fixed_price", "term_start": "2026-10-01", "term_end": "2026-12-31",
                "notice_date": "2026-12-01", "deliverables": ["Migration plan", "Reporting platform"],
                "milestones": ["Final delivery"], "acceptance_criteria": "Client sign-off", "assumptions": "Client access available",
                "exclusions": "Taxes", "signatories": [{"source": "internal", "name": PEOPLE['owner'][0], "email": email('owner'), "user_id": str(uid('owner'))}],
            }
            version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=uid('owner'), version_no=1,
                file_s3_key='s14b/fixture.pdf', file_hash=f's14b-{index}', extract_status='complete', engagement_type_confirmed='fixed_price',
                extracted_fields={key: wrap(value, provenance='extracted', page_ref=1, status='confirmed') for key, value in raw.items()})
            session.add(version)
            await session.flush()
            await create_gm_model_version(session, opportunity_id=opp.id, actor_id=uid('owner'), payload=parse_gm_model_payload({
                "engagement_type": "fixed_price", "sow_version_id": str(version.id), "delivery_pattern": "milestone",
                "total_price": "50000", "direct_costs_reviewed": True,
                "resource_lines": [{"role": "Engineer", "seniority": "Senior", "location": "US", "person_name": "Dana Delivery",
                    "allocation_pct": "1", "start_date": "2026-10-01", "end_date": "2026-12-31", "hours_billable": "400",
                    "hourly_bill_rate": "0", "hourly_cost": "100" if below else "20", "validated_by": str(uid('owner'))}], "cost_lines": [],
            }))
        await session.commit()


async def fixture_identity(x_test_user: str | None = Header(default=None, alias='X-Test-User')):
    key = next((k for k in PEOPLE if email(k) == x_test_user), None)
    if not key:
        raise HTTPException(401, 'Unknown fixture identity')
    name, roles = PEOPLE[key]
    return AuthUser(id=uid(key), email=email(key), name=name, groups=tuple(roles))


if __name__ == '__main__':
    asyncio.run(seed())
    app.dependency_overrides[current_user] = fixture_identity
    app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5175', 'http://localhost:5175'], allow_methods=['*'], allow_headers=['*'])
    uvicorn.run(app, host='127.0.0.1', port=8025)
