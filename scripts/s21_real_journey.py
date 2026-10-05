"""Isolated HTTP journey with migrated Postgres, real S3 and real Bedrock.

Local identity adapter and external mail sink are explicit test boundaries.
No approval, extraction, signature or forecast feature response is replaced.
This is integration evidence, not Cognito/browser/staging acceptance.
"""

import asyncio
import hashlib
import json
import os
import uuid
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import urlparse
from zipfile import ZipFile

import httpx
from fastapi import Header, HTTPException
from sqlalchemy import select

url = urlparse(os.environ["POSTGRES_URL"])
if url.hostname not in {"127.0.0.1", "localhost"} or url.path != "/s21_journey":
    raise RuntimeError("This runner requires the dedicated local s21_journey database")
os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID="s21-lead",
                  ALLOW_DEV_SEED_ENDPOINT="1", AWS_REGION="us-east-2")

from app.auth import AuthUser, current_user
from app.db import session_factory
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    get_bedrock_sow,
)
from app.integrations.s3_sow import SowS3, get_sow_s3
from app.integrations.ses import StubSES, get_ses_client
from app.main import app
from app.models.audit import AuditEvent
from app.models.user import User
from app.services.sow_extract import EXTRACTED_FIELDS

from worker.notification_sender import process_batch


def document(name, run):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = ET.Element(f"{{{ns}}}document")
    body = ET.SubElement(root, f"{{{ns}}}body")
    lines = [
        f"STATEMENT OF WORK. Synthetic assessment {run}. Client: {name}. Supplier: SmarTek21.",
        "Fixed-price assessment. Total contract price: 24000.00. Currency: USD. Invoice upon delivery.",
        "Term start: 2026-10-01. Term end: 2026-10-31. Notice date: 2026-10-15.",
        "Scope: Assess the synthetic data platform and deliver a written assessment report.",
        "Deliverables: Written assessment report. Milestone: Report delivery on 2026-10-31.",
        "Acceptance criteria: Client reviews the delivered report within five business days.",
        "Assumptions: Client supplies synthetic data. Exclusions: No implementation or travel.",
        "Client domain: synthetic.example.test. No direct expenses or reimbursements.",
        "Authorized test signatories: Alex Example for Client; Casey Example for SmarTek21.",
        "Executed solely for isolated testing: /s/ Alex Example; /s/ Casey Example. No real contract.",
    ]
    for line in lines:
        ET.SubElement(ET.SubElement(ET.SubElement(body, f"{{{ns}}}p"), f"{{{ns}}}r"), f"{{{ns}}}t").text = line
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", ET.tostring(root))
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
    return output.getvalue()


class OwnedStorage(SowS3):
    def __init__(self, run):
        super().__init__(bucket="officeapp-dev-sows-669810405473", region="us-east-2")
        self.run, self.keys = run, set()

    def build_key(self, *args, **kwargs):
        return f"verification/s21/{self.run}/" + super().build_key(*args, **kwargs)

    def put_object(self, key, body, content_type):
        self.keys.add(key)
        return super().put_object(key, body, content_type)

    def cleanup(self):
        client = self._client_or_new()
        for key in sorted(self.keys):
            # Remove only this run's exact keys, including all their versions.
            for page in client.get_paginator("list_object_versions").paginate(Bucket=self._bucket, Prefix=key):
                objects = [{"Key": row["Key"], "VersionId": row["VersionId"]}
                    for row in page.get("Versions", []) + page.get("DeleteMarkers", []) if row["Key"] == key]
                if objects:
                    result = client.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})
                    assert not result.get("Errors"), result.get("Errors")
            print(json.dumps({"storage_deleted": key}), flush=True)


async def main():
    run = uuid.uuid4().hex
    roster = {}
    roles = {"owner": ["Sales", "SystemAdmin"], "delivery": ["Delivery"], "hr": ["HR"],
             "sales": ["Sales"], "finance": ["Finance"], "legal": ["Legal"]}
    async with session_factory() as session:
        for role, groups in roles.items():
            person = User(id=uuid.uuid4(), name=f"S21 {role}", email=f"{run}-{role}@example.test",
                          groups=groups + ["officeapp-e2e"])
            session.add(person)
            roster[role] = person
        await session.commit()

    async def local_identity(x_test_user: str = Header()):
        person = roster.get(x_test_user)
        if not person:
            raise HTTPException(401, "Unknown isolated journey identity")
        return AuthUser(id=person.id, email=person.email, name=person.name, groups=tuple(person.groups))

    storage, mail = OwnedStorage(run), StubSES()
    app.dependency_overrides[current_user] = local_identity
    app.dependency_overrides[get_sow_s3] = lambda: storage
    app.dependency_overrides[get_bedrock_sow] = BedrockSowExtract
    app.dependency_overrides[get_ses_client] = lambda: mail
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://journey", timeout=360) as client:
            async def request(method, path, role="owner", **kwargs):
                response = await client.request(method, path, headers={"X-Test-User": role}, **kwargs)
                assert response.is_success, f"{method} {path}: {response.status_code} {response.text[:2000]}"
                return response.json()

            issued = await request("POST", "/dev/test-fixtures", json={"label": run,
                "reviewer_ids": [str(person.id) for person in roster.values()]})
            deal, account = issued["opportunity_id"], issued["client_id"]
            print(json.dumps({"run": run, "fixture": issued}), flush=True)
            listing = await request("GET", "/deals?size=200")
            assert deal in {row["id"] for row in listing["items"]}
            await request("GET", f"/deals/{deal}")
            content = document(f"Synthetic Northstar {run}", run)
            job = await request("POST", "/sows/upload", data={"client_id": account, "opportunity_id": deal},
                files={"file": (f"assessment-{run}.docx", content, mime)})
            assert job["status"] == "done", job
            version = job["sow_version_id"]
            sow = await request("GET", f"/sow/versions/{version}")
            assert sow["extract_status"] == "complete", sow
            print(json.dumps({"uploaded": version, "extract_status": sow["extract_status"]}), flush=True)
            for name in EXTRACTED_FIELDS:
                entry = sow["extracted_fields"][name]
                await request("PATCH", f"/sow/versions/{version}/fields/{name}", json={"value": entry["value"]})
            gm = await request("POST", f"/delivery-model/{deal}/versions", json={
                "engagement_type": "assessment", "sow_version_id": version,
                "delivery_pattern": "us_only", "total_price": "24000", "contingency_pct": "0", "warranty_days": 0,
                "resource_lines": [{"role": "Engineer", "seniority": "senior", "location": "US",
                    "person_name": "Test Engineer", "allocation_pct": "1", "start_date": "2026-10-01",
                    "end_date": "2026-10-31", "hours_billable": "100", "hourly_bill_rate": "240",
                    "hourly_cost": "100", "validated_by": str(roster["hr"].id)}], "cost_lines": []})
            gm_id = gm["gm_model"]["id"]
            commercial = os.environ.get("S21_COMMERCIAL") == "1"
            if commercial:
                registry = await request("GET", "/delivery-model/commercial/profiles")
                inputs = {
                    "component_id": "assessment", "version": "1", "source_id": sow["sow_id"],
                    "source_version": version, "workstream_id": "assessment",
                    "profile": "fixed_assignment", "profile_version": "1",
                    "policy_version": registry["policy"]["version"],
                    "source_evidence": [f"sow:{version}:page:1"],
                    "service_start": "2026-10-01", "service_end": "2026-10-31",
                    "timezone": "America/New_York", "currency": "USD", "billing_cadence": "upon_delivery",
                    "cost_basis": "Confirmed synthetic assessment team cost", "costs_confirmed": True,
                    "costs": [{"source_id": "assessment-team", "month": "2026-10-01",
                               "location": "US", "amount": "10000"}], "staffing": [],
                    "pricing": {"total_fee": "24000", "allocations": [
                        {"month": "2026-10-01", "location": "US", "weight": "1"}],
                        "allocation_basis": "Single October service month", "minor_unit": "0.01"},
                }
                gm = await request("POST", f"/delivery-model/{deal}/commercial/versions", json={
                    "sow_version_id": version, "expected_gm_model_id": gm_id,
                    "inputs": inputs, "change_reason": "Confirmed synthetic assessment service economics"})
                gm_id = gm["gm_model"]["id"]
                assert gm["gm_model"]["computed"]["cost_us"] == "10000", gm
                fresh = await request("GET", f"/delivery-model/{deal}")
                assert fresh["gm_model"]["commercial_inputs"]["pricing"]["total_fee"] == "24000"
                if os.environ.get("S21_DRAFT_ONLY") == "1":
                    print(json.dumps({"draft_deal": deal, "gm_model_id": gm_id,
                                      "sow_version_id": version, "staging_verified": False}), flush=True)
                    return
            await request("POST", f"/sow/versions/{version}/submit")
            plan = await request("GET", f"/approvals/plan/{deal}")
            functions = [row["function"] for row in plan["rows"]]
            assert functions == ["delivery", "hr", "sales", "finance", "legal"], functions
            package = await request("POST", f"/approvals/packages/{deal}", json={
                "sow_version_id": version, "gm_model_id": gm_id})
            package_id = package["id"]
            for function in functions:
                current = await request("GET", f"/approvals/packages/{package_id}", role=function)
                assert next(a for a in current["assignments"] if a["function"] == function)["can_decide"], current
                package = await request("POST", f"/approvals/packages/{package_id}/decisions/{function}", role=function,
                    json={"decision": "approve", "reason": "Reviewed synthetic source and economics",
                          "expected_package_hash": package["package_hash"]})
            assert package["status"] == "ready_to_sign", package
            print(json.dumps({"approved": package_id, "functions": functions}), flush=True)
            signed = await request("POST", f"/signed-sow/{package_id}/upload-url",
                json={"filename": "executed.docx", "content_type": mime})
            storage.put_object(signed["s3_key"], content, mime)
            await request("POST", f"/signed-sow/{package_id}", json={"file_s3_key": signed["s3_key"],
                "file_hash": hashlib.sha256(content).hexdigest(), "has_signature_evidence": True})
            verified = await request("POST", f"/signed-sow/{package_id}/verify")
            assert verified["verify_status"] == "verified", verified
            await request("POST", f"/handoff/{package_id}/accept", role="delivery", json={
                "staffing_confirmed": True, "billing_setup_confirmed": True, "po_confirmed": True,
                "notes": "Synthetic fixture delivery acceptance"})
            await request("POST", f"/signed-sow/{package_id}/release")
            projects = await request("GET", "/projects")
            assert any(row["package_id"] == package_id for row in projects["items"])
            forecast = await request("POST", f"/forecast/{gm_id}", role="delivery", json={"lines": []})
            assert forecast["forecast_revenue"] == "24000.00", forecast
            if commercial:
                assert forecast["forecast_cost_us"] == "10000.00", forecast
                assert forecast["forecast_gm_us"] == "0.5833", forecast
                assert forecast["forecast_lines_json"][0]["source_version"] == version
            async with session_factory() as session:
                handled = await process_batch(session, ses=mail, limit=200)
                audits = list((await session.scalars(select(AuditEvent.action).where(
                    AuditEvent.actor_id.in_([person.id for person in roster.values()])
                ))).all())
                assert "signed_sow.verified" in audits and "forecast.updated" in audits
            print(json.dumps({"journey": "sales-path-passed", "forecast": forecast["id"],
                "worker_rows": handled, "mail_sink_messages": len(mail.sent),
                "s21_sales_present": "sales" in functions, "staging_verified": False}), flush=True)
    finally:
        app.dependency_overrides.clear()
        storage.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
