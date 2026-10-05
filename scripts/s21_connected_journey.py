"""Connected local integration proof; lead execution only.

Real HTTP services, PostgreSQL, S3, Bedrock and separate sourcing worker.
Local identity, synthetic document and SES sink are explicit boundaries.
Safe fixture provenance stays explicit; local proof is not live HubSpot or
staging acceptance. Preserve failed run logs before another invocation.
"""

import asyncio
import hashlib
import json
import os
import sys
import uuid
import xml.etree.ElementTree as ET
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from urllib.parse import urlparse

target = urlparse(os.environ["POSTGRES_URL"])
if (target.hostname, target.port, target.path) != ("127.0.0.1", 55421, "/s21_journey"):
    raise RuntimeError("Requires owned local s21_journey on literal 127.0.0.1:55421")

TENANT = os.environ["S21_CONNECTED_TENANT"]
if not TENANT.startswith("s21-connected-") or len(TENANT) > 100:
    raise RuntimeError("Provision a fresh dedicated s21-connected-* tenant first")
if os.environ.get("S21_CONNECTED_PROVIDER_CALLS") != "lead-authorized":
    raise RuntimeError("Lead must explicitly authorize this real S3/Bedrock run")

# The existing helper enforces the dedicated local s21_journey PostgreSQL URL.
from s21_real_journey import OwnedStorage, document

os.environ.update(DEALGATE_TENANT_ID=TENANT, DEALGATE_ENV="local",
                  DEALGATE_REPORTING_TIMEZONE="America/Los_Angeles",
                  DEALGATE_REPORTING_CURRENCY="USD")

import httpx
from fastapi import Header, HTTPException
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import session_factory
from app.integrations.bedrock_sow_extract import BedrockSowExtract, get_bedrock_sow
from app.integrations.s3_sow import get_sow_s3
from app.integrations.ses import StubSES, get_ses_client
from app.main import app
from app.models.actual import FinancialActual
from app.models.project import Project
from app.models.user import User
from app.services.sow_extract import EXTRACTED_FIELDS

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MONTH, END = "2026-10-01", "2026-10-31"
TEAM = (("US", 2, "America/New_York", "10000", "4000"),
        ("India", 5, "Asia/Kolkata", "14000", "6000"))


def source_document(name, run):
    original, output = BytesIO(document(name, run)), BytesIO()
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with ZipFile(original) as source, ZipFile(output, "w") as target:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename == "word/document.xml":
                tree = ET.fromstring(data)
                body = tree.find(f"{{{ns}}}body")
                assert body is not None
                for paragraph in list(body):
                    value = "".join(paragraph.itertext())
                    if value.startswith(("Authorized test signatories:", "Executed solely for isolated testing:")):
                        body.remove(paragraph)
                lines = [
                    "Client signature block: Signatory name: Alex Example. Organization: Client. Signature: [synthetic executed signature].",
                    "Supplier signature block: Signatory name: Casey Example. Organization: SmarTek21. Signature: [synthetic executed signature].",
                    "These two synthetic signatures are solely for isolated testing; no real contract.",
                    "Confirmed staffing: 2 US Engineers and 5 India Engineers, each full-time, October 1-31 2026.",
                    "US fee allocation USD 10000 and approved total US cost USD 4000; India fee USD 14000 and approved total India cost USD 6000.",
                    "Loaded hourly staffing costs: US USD 10, India USD 5, cost version synthetic-1. Additional nonstaff costs: US USD 480 and India USD 1600 for October.",
                    "Both teams work Monday-Friday 8 scheduled, billable and paid hours; Saturday-Sunday zero; no holidays in this synthetic calendar.",
                    "US timezone America/New_York; India timezone Asia/Kolkata. Delivery separately confirms Python skill and Senior level for both teams.",
                ]
                for line in lines:
                    ET.SubElement(ET.SubElement(ET.SubElement(body, f"{{{ns}}}p"), f"{{{ns}}}r"), f"{{{ns}}}t").text = line
                data = ET.tostring(tree)
            target.writestr(entry, data)
    return output.getvalue()


def component(sow_id, version, policy):
    common = dict(version="1", source_id=sow_id, source_version=version,
        workstream_id="assessment", profile_version="1", policy_version=policy,
        source_evidence=[f"sow:{version}:confirmed synthetic staffing and fee clauses"],
        service_start=MONTH, service_end=END, currency="USD", billing_cadence="upon_delivery",
        cost_basis="Synthetic document expressly confirms costs by location", costs_confirmed=True)
    children = []
    for location, quantity, zone, fee, cost in TEAM:
        identity = f"assessment-{location}"
        calendar = dict(calendar_id=f"synthetic-{location}", version="1", timezone=zone,
            coverage_start=MONTH, coverage_end=END,
            week=[dict(scheduled=h, billable=h, paid=h) for h in ["8"] * 5 + ["0"] * 2], overrides=[])
        assignment = dict(assignment_id=f"team-{location}", source_id=sow_id, source_version=version,
            component_id=identity, profile_version="1", policy_version=policy,
            role="Engineer", location=location, timezone=zone, currency="USD",
            quantity=quantity, allocation="1", calendar=calendar, bill_rate=None,
            cost_rate="10" if location == "US" else "5", rate_version=None,
            cost_version="synthetic-1", start=MONTH, end=END)
        children.append(dict(**common, component_id=identity, profile="fixed_assignment", timezone=zone,
            staffing=[assignment], costs=[dict(source_id=f"cost-{location}", month=MONTH,
                location=location, amount="480" if location == "US" else "1600")],
            pricing=dict(total_fee=fee, allocations=[dict(month=MONTH, location=location, weight="1")],
                allocation_basis="Explicit single-month location fee in synthetic document", minor_unit="0.01")))
    return dict(**common, component_id="assessment", profile="hybrid", timezone="America/New_York",
                staffing=[], costs=[], pricing=dict(components=children, shared_cost_allocations=[]))


async def worker():
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "worker.sourcing_automation",
        cwd=ROOT, env=os.environ.copy(), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    result = json.loads(stdout.decode().splitlines()[-1])
    assert result["worker"] == "sourcing_automation"
    print(json.dumps(result), flush=True)


async def main():
    from app.gm.commercial import calculate_component
    from app.services.commercial_models import parse_component

    schedule = calculate_component(parse_component(component("fixture", "version", "policy")))
    assert schedule.status == "ok", schedule.missing
    assert {row.location: (row.revenue, row.cost) for row in schedule.rows} == {
        "US": (D("10000"), D("4000")), "India": (D("14000"), D("6000"))}
    run, roster = uuid.uuid4().hex, {}
    storage, mail = OwnedStorage(uuid.uuid4().hex), StubSES()
    saved_overrides = dict(app.dependency_overrides)
    async with session_factory() as session:
        for role, groups in {"owner": ["Sales", "SystemAdmin"], "delivery": ["Delivery"],
                "hr": ["HR"], "sales": ["Sales"], "finance": ["Finance"], "legal": ["Legal"]}.items():
            person = User(id=uuid.uuid4(), name=f"Connected {role} {run}",
                email=f"{run}-{role}@example.test", groups=groups + ["officeapp-e2e"])
            session.add(person)
            roster[role] = person
        await session.commit()

    async def identity(x_test_user: str = Header()):
        person = roster.get(x_test_user)
        if person is None:
            raise HTTPException(401, "Unknown connected-run identity")
        return AuthUser(id=person.id, email=person.email, name=person.name, groups=tuple(person.groups))

    app.dependency_overrides.update({current_user: identity, get_sow_s3: lambda: storage,
        get_bedrock_sow: BedrockSowExtract, get_ses_client: lambda: mail})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://connected", timeout=360) as client:
            async def request(method, path, role="owner", **kwargs):
                response = await client.request(method, path, headers={"X-Test-User": role}, **kwargs)
                assert response.is_success, f"{method} {path}: {response.status_code} {response.text[:2000]}"
                return response.json()

            rule = await request("GET", "/people/sourcing/automation")
            assert rule["enabled"] and rule["source_scope"] == "authorized_sources", "Lead prerequisite: enabled scoped rule"
            rules = await request("GET", "/people/sourcing/rules")
            assert sorted(rules["rules"], key=lambda r: r["location"]) == [
                dict(skill="python", location="India", lead_days=30), dict(skill="python", location="US", lead_days=30)]
            assert (await request("GET", "/people/demand"))["items"] == [], "Fresh tenant required; never mutate old fixtures"
            assert (await request("GET", "/people/availability"))["people"] == []
            assert (await request("GET", "/people/sourcing/automation/jobs"))["items"] == []
            async with session_factory() as session:
                authority = await session.get(User, uuid.UUID(rule["created_by"]))
                assert authority and {"SystemAdmin", "officeapp-e2e"} <= set(authority.groups)
            fixture = await request("POST", "/dev/test-fixtures", json={"label": f"connected {run}",
                "reviewer_ids": [str(p.id) for p in roster.values()] + [str(authority.id)]})
            deal, account = fixture["opportunity_id"], fixture["client_id"]
            print(json.dumps({"run": run, "tenant": TENANT, "fixture": fixture,
                              "rule_version": rule["id"], "lead_time_version": rules["id"]}), flush=True)
            # Do not change source='sow_upload': CRM classification would invalidate the grant.
            pipeline = await request("GET", f"/pipeline/opportunities/{deal}")
            assert pipeline["opportunity_id"] == deal
            assert pipeline["source_origin"] == "local_test_fixture"
            assert pipeline["hubspot_deal_id"] is None
            pipeline_list = await request("GET", "/pipeline/opportunities")
            assert deal in {row["opportunity_id"] for row in pipeline_list["items"]}
            assert deal in {row["id"] for row in (await request("GET", "/deals?size=200"))["items"]}
            detail = await request("GET", f"/deals/{deal}")
            assert detail["id"] == deal and detail["client_id"] == account
            assert detail["client_name"] and detail["hubspot_deal_id"] is None
            content = source_document(f"Synthetic connected {run}", run)
            upload = await request("POST", "/sows/upload", data={"client_id": account, "opportunity_id": deal},
                files={"file": (f"connected-{run}.docx", content, MIME)})
            assert upload["status"] == "done", upload
            version = upload["sow_version_id"]
            sow = await request("GET", f"/sow/versions/{version}")
            assert sow["extract_status"] == "complete"
            assert D(str(sow["extracted_fields"]["price"]["value"])) == D("24000")
            extracted_signers = sow["extracted_fields"]["signatories"]["value"]
            assert {(row["name"] if isinstance(row, dict) else row).strip().lower()
                for row in extracted_signers} == {"alex example", "casey example"}, extracted_signers
            for field in EXTRACTED_FIELDS:
                await request("PATCH", f"/sow/versions/{version}/fields/{field}", json={"value": sow["extracted_fields"][field]["value"]})
            registry = await request("GET", "/delivery-model/commercial/profiles")
            current_gm = (await request("GET", f"/delivery-model/{deal}"))["gm_model"]
            saved = await request("POST", f"/delivery-model/{deal}/commercial/versions", json={
                "sow_version_id": version, "expected_gm_model_id": current_gm["id"] if current_gm else None,
                "inputs": component(sow["sow_id"], version, registry["policy"]["version"]),
                "change_reason": "Confirm exact independent synthetic document economics and seven-person team"})
            gm = saved["gm_model"]["id"]
            assert saved["gm_model"]["computed"]["complete"], saved["gm_model"]["computed"]
            await request("POST", f"/sow/versions/{version}/submit")
            functions = [r["function"] for r in (await request("GET", f"/approvals/plan/{deal}"))["rows"]]
            assert functions == ["delivery", "hr", "sales", "finance", "legal"]
            package = await request("POST", f"/approvals/packages/{deal}", json={"sow_version_id": version, "gm_model_id": gm})
            for function in functions:
                current = await request("GET", f"/approvals/packages/{package['id']}", role=function)
                assert next(a for a in current["assignments"] if a["function"] == function)["can_decide"]
                package = await request("POST", f"/approvals/packages/{package['id']}/decisions/{function}", role=function,
                    json={"decision": "approve", "reason": "Reviewed independent synthetic source",
                          "expected_package_hash": package["package_hash"]})
            assert package["status"] == "ready_to_sign"
            signed = await request("POST", f"/signed-sow/{package['id']}/upload-url", json={"filename": "executed.docx", "content_type": MIME})
            storage.put_object(signed["s3_key"], content, MIME)
            await request("POST", f"/signed-sow/{package['id']}", json={"file_s3_key": signed["s3_key"],
                "file_hash": hashlib.sha256(content).hexdigest(), "has_signature_evidence": True})
            verification = await request("POST", f"/signed-sow/{package['id']}/verify")
            assert verification["verify_status"] == "verified", verification
            await request("POST", f"/handoff/{package['id']}/accept", role="delivery", json={
                "staffing_confirmed": True, "billing_setup_confirmed": True, "po_confirmed": True,
                "notes": "Seven-person synthetic source accepted"})
            await request("POST", f"/signed-sow/{package['id']}/release")
            projects = [r for r in (await request("GET", "/projects"))["items"] if r["package_id"] == package["id"]]
            assert len(projects) == 1 and projects[0]["gm_model_id"] == gm
            project_id = projects[0]["project_id"]
            async with session_factory() as session:
                project = await session.get(Project, uuid.UUID(project_id))
                baseline = json.dumps(project.baseline_snapshot_json, sort_keys=True)
                scope = project.baseline_snapshot_json["source_scope"]
                assert scope["gm_model_id"] == gm and scope["sow_version_id"] == version
                assert scope["opportunity_id"] == deal and scope["account_id"] == account
                assert scope["fixture_grant_id"] and scope["tenant_id"] == TENANT
            params = dict(account_id=account, as_of="2026-10-31T20:00:00Z", future_quarters=4)
            outlook = await request("GET", "/forecast/outlook", params=params)
            assert len(outlook["months"]) == 15 and not outlook["pending_sources"] and not outlook["excluded"]
            assert {r["source_id"] for r in outlook["rows"]} == {gm}
            assert {r["source_version"] for r in outlook["rows"]} == {version}
            assert D(outlook["current_month"]["signed"]) == D("24000")
            assert D(outlook["current_month"]["cost"]) == D("10000")
            assert D(outlook["current_month"]["potential"]) == 0

            await request("POST", "/people/imports", role="hr", json={"source_system": f"connected-{run}",
                "request_key": str(uuid.uuid4()), "expected_previous_batch_id": None,
                "source_as_of": "2026-10-01T00:00:00Z", "basis": "gross_with_commitments",
                "reason": "Synthetic dedicated tenant has no available people", "people": []})
            await worker()
            async def jobs():
                rows, page = [], 1
                while True:
                    batch = (await request("GET", "/people/sourcing/automation/jobs", params={"page": page, "size": 100}))["items"]
                    rows.extend(r for r in batch if r["source_id"] == project_id)
                    if len(batch) < 100:
                        return rows
                    page += 1
            old_jobs = await jobs()
            assert old_jobs and all(r["status"] == "review" for r in old_jobs), old_jobs
            source = next(r for r in (await request("GET", "/people/demand"))["items"] if r["source_id"] == project_id)
            assert source["source_kind"] == "project" and source["source_version_id"] == gm
            assert {r["location"]: r["quantity"] for r in source["lines"]} == {"US": 2, "India": 5}
            assert source["missing"] and D(source["probability"]) == 1
            old_history = await request("GET", "/people/sourcing/drafts", params={"publication_id": source["publication_id"]})
            assert old_history["items"] and not old_history["items"][0]["snapshot"]["complete"]
            published = await request("POST", "/people/demand/project-publications", role="delivery", json={
                "project_id": project_id, "expected_source_version_id": gm,
                "expected_publication_version_id": source["publication_version_id"], "request_key": str(uuid.uuid4()),
                "reason": "Delivery confirms explicit Python and Senior source clause",
                "enrichments": {r["line_key"]: {"skills": ["python"], "level": "Senior",
                    "evidence": [f"sow:{version}:synthetic capability clause"]} for r in source["lines"]}})
            await worker()
            repaired_jobs = await jobs()
            assert all(row in repaired_jobs for row in old_jobs), "Prior job history changed"
            done = [r for r in repaired_jobs if r["status"] == "done"]
            assert done and all(r["source_version"] == gm for r in done)
            history = await request("GET", "/people/sourcing/drafts", params={"publication_id": source["publication_id"]})
            assert history["state"] == "current"
            latest = next(r for r in history["items"] if r["id"] == history["current_version_id"])
            assert latest["id"] in {r["result_version_id"] for r in done}
            assert latest["demand_version_id"] == published["version_id"] and latest["snapshot"]["complete"]
            assert D(latest["snapshot"]["probability"]) == 1
            assert all(row in history["items"] for row in old_history["items"])
            rows = latest["snapshot"]["rows"]
            assert {r["location"]: r["quantity"] for r in rows} == {"US": 2, "India": 5}
            assert sum(r["quantity"] for r in rows) == 7
            assert all(r["source_id"] == project_id and r["sourcing_by"] == "2026-09-01" for r in rows)
            assert all(r["incremental_gap_quantity"] == r["quantity"] for r in rows)
            assert all(r["retained_quantity"] == 0 and r["continuity_gap_quantity"] == 0 for r in rows)
            assert sum(D(r["gap_fte"]) for r in rows) == D("7")
            await worker()
            assert (await request("GET", "/people/sourcing/drafts", params={"publication_id": source["publication_id"]}))["current_version_id"] == latest["id"]

            expected = {"recognized_revenue": "12000.01", "billed": "15000", "cash_collected": "8000", "delivery_cost": "6000"}
            financial = {"source_system": f"connected-finance-{run}", "idempotency_key": str(uuid.uuid4()), "rows": [
                dict(account_id=account, gm_model_id=gm, source_id=measure, revision=1,
                     period_month=MONTH, measure=measure, amount=amount, currency="USD", source_date=END,
                     reason="Independent synthetic project ledger") for measure, amount in expected.items()]}
            imported = await request("POST", "/actuals/financial-import", role="finance", json=financial)
            assert (await request("POST", "/actuals/financial-import", role="finance", json=financial))["id"] == imported["id"]
            facts = await request("GET", "/actuals/financial-records", role="finance", params={"account_id": account})
            assert facts["total"] == 4 and all(r["gm_model_id"] == gm for r in facts["items"])
            financial.update(idempotency_key=str(uuid.uuid4()), rows=[{**financial["rows"][0],
                "revision": 2, "expected_previous_revision": 1, "amount": "11000.99", "reason": "Finance correction to same project"}])
            await request("POST", "/actuals/financial-import", role="finance", json=financial)
            corrected = await request("GET", "/forecast/outlook", params=params)
            expected["recognized_revenue"] = "11000.99"
            assert {r["measure"]: D(r["amount"]) for r in corrected["financial_actuals"]["totals"]} == {k: D(v) for k, v in expected.items()}
            assert corrected["rows"] == outlook["rows"], "Actuals must not silently mutate service schedule"
            async with session_factory() as session:
                project = await session.get(Project, uuid.UUID(project_id))
                assert json.dumps(project.baseline_snapshot_json, sort_keys=True) == baseline
                records = list((await session.scalars(select(FinancialActual).where(
                    FinancialActual.source_system == financial["source_system"], FinancialActual.source_id == "recognized_revenue")
                    .order_by(FinancialActual.revision))).all())
                assert [r.amount for r in records] == [D("12000.01"), D("11000.99")]
                assert all(str(r.original_gm_model_id) == scope["gm_model_id"] for r in records)
            print(json.dumps({"status": "connected_local_journey_passed", "project_id": project_id,
                "deal": deal, "sow_version": version, "gm": gm, "package": package["id"],
                "publication": published, "draft": latest["id"], "headcount": 7,
                "actual_bases": expected, "full_journey_passed": True, "staging_verified": False}), flush=True)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)
        if storage.keys:
            storage.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
