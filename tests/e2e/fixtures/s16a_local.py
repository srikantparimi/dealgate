"""S16a local proof only: disposable SQLite, fictional records, stub external I/O."""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import uvicorn
from fastapi import Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import DATABASE_URL, Base, engine, session_factory
from app.main import app
from app.integrations.bedrock_sow_extract import StubBedrock, get_bedrock_sow
from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.gm_model import GmModel, ResourceLine
from app.models.user import User
from app.services.forecast import update_forecast
from app.services.sow_upload_job_service import _create_opportunity
from tests.test_coverage_gate import _seed_opp_gm

EMAIL = "s16-owner@example.test"
USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{EMAIL}")
ROLES = ("SystemAdmin", "Sales", "Legal", "Delivery")


async def seed():
    if (
        os.environ.get("DEALGATE_ENV") != "local"
        or not DATABASE_URL.startswith("sqlite+")
        or "s16a" not in DATABASE_URL
    ):
        raise RuntimeError("Use a disposable s16a SQLite database in local mode")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        if await session.get(User, USER_ID):
            return
        owner = User(id=USER_ID, email=EMAIL, name="Morgan Example", groups=list(ROLES))
        client = Client(id=uuid.uuid4(), name="Example Systems")
        session.add_all([owner, client])
        await session.flush()
        await _create_opportunity(session, uploader_id=owner.id, client_id=client.id)
        opp, version = await _seed_opp_gm(session, owner, client.id)
        version.extracted_fields = {
            **version.extracted_fields,
            "sow_title": {"value": "Reporting platform delivery", "page_ref": 1},
            "term_end": {"value": "2027-03-31", "page_ref": 1},
        }
        model = await session.scalar(select(GmModel).where(GmModel.opportunity_id == opp.id))
        package = ApprovalPackage(
            id=uuid.uuid4(),
            opportunity_id=opp.id,
            sow_version_id=version.id,
            gm_model_id=model.id,
            package_hash="s16-local-fixture",
            status="released",
            submitted_by=owner.id,
            released_at=datetime.now(UTC),
        )
        session.add(package)
        await session.flush()
        resources = list(
            (
                await session.scalars(
                    select(ResourceLine).where(ResourceLine.gm_model_id == model.id)
                )
            ).all()
        )
        await update_forecast(
            session,
            actor=owner,
            gm_model_id=model.id,
            lines=[{"resource_line_id": str(r.id), "remaining_hours": "100"} for r in resources],
        )
        await session.commit()


async def identity(x_test_user: str | None = Header(default=None, alias="X-Test-User")):
    if x_test_user != EMAIL:
        raise HTTPException(401, "Unknown fixture identity")
    return AuthUser(id=USER_ID, email=EMAIL, name="Morgan Example", groups=ROLES)


def fixture_document():
    data = BytesIO()
    with ZipFile(data, "w") as doc:
        doc.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Signed NDA or MSA for Example Systems. Effective 2026-01-01 through 2027-12-31. Signed by Morgan Example and Avery Example.</w:t></w:r></w:p></w:body></w:document>',
        )
    return Response(
        data.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


if __name__ == "__main__":
    asyncio.run(seed())
    evidence = StubS3()
    app.dependency_overrides[current_user] = identity
    app.dependency_overrides[get_evidence_s3] = lambda: evidence
    app.dependency_overrides[get_bedrock_sow] = StubBedrock
    app.add_api_route("/__s16/fixture.docx", fixture_document, methods=["GET"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5176", "http://localhost:5176"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    uvicorn.run(app, host="127.0.0.1", port=8026)
