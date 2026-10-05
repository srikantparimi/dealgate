"""Disposable connected S21 staging journey.

Uses real Cognito identities, API, RDS, S3 and Bedrock. The server-issued
fixture is deleted in ``finally`` and its durable cleanup job is polled.
Secret values are read from Secrets Manager and never printed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import uuid
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import httpx

BASE = os.environ.get("S21_STAGING_BASE", "https://app.dealgateapp.com").rstrip("/")
PROFILE = os.environ.get("AWS_PROFILE", "lm-arbiter-poc")
REGION = os.environ.get("AWS_REGION", "us-east-2")
MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXTRACTED_FIELDS = (
    "client_legal_name",
    "client_domain",
    "billing_basis_normalized",
    "scope_summary",
    "price",
    "currency",
    "billing_basis",
    "term_start",
    "term_end",
    "notice_date",
    "deliverables",
    "milestones",
    "acceptance_criteria",
    "assumptions",
    "exclusions",
    "signatories",
    "engagement_type_suggested",
)


def aws_json(*args: str) -> dict:
    result = subprocess.run(
        ["aws", "--profile", PROFILE, "--region", REGION, *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def secret(secret_id: str) -> dict:
    result = aws_json(
        "secretsmanager",
        "get-secret-value",
        "--secret-id",
        secret_id,
    )
    return json.loads(result["SecretString"])


def mint(*, pool: str, client: str, username: str, password: str) -> str:
    result = aws_json(
        "cognito-idp",
        "admin-initiate-auth",
        "--user-pool-id",
        pool,
        "--client-id",
        client,
        "--auth-flow",
        "ADMIN_USER_PASSWORD_AUTH",
        "--auth-parameters",
        f"USERNAME={username},PASSWORD={password}",
    )
    return result["AuthenticationResult"]["IdToken"]


def document(name: str, run: str) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    lines = [
        f"STATEMENT OF WORK. Synthetic assessment {run}. Client: {name}. Supplier: SmarTek21.",
        "Fixed-price assessment. Total contract price: 24000.00. Currency: USD. Invoice upon delivery.",
        "Term start: 2026-10-01. Term end: 2026-10-31. Notice date: 2026-10-15.",
        "Scope: Assess the synthetic data platform and deliver a written assessment report.",
        "Deliverables: Written assessment report. Milestone: Report delivery on 2026-10-31.",
        "Acceptance criteria: Client reviews the delivered report within five business days.",
        "Assumptions: Client supplies synthetic data. Exclusions: No implementation or travel.",
        "Client domain: synthetic.example.test. No direct expenses or reimbursements.",
        "Confirmed staffing: one US senior engineer, full-time, October 1-31 2026.",
        "US fee allocation USD 24000 and approved total US cost USD 10000.",
        "Client signature block: Alex Example, Client, /s/ Alex Example.",
        "Supplier signature block: Casey Example, SmarTek21, /s/ Casey Example.",
        "These synthetic signatures are solely for isolated testing; no real contract.",
    ]
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in lines
    )
    xml = f'<w:document xmlns:w="{ns}"><w:body>{paragraphs}</w:body></w:document>'
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
    return output.getvalue()


def commercial_inputs(sow_id: str, version: str, policy: str) -> dict:
    return {
        "component_id": "assessment",
        "version": "1",
        "source_id": sow_id,
        "source_version": version,
        "workstream_id": "assessment",
        "profile": "fixed_assignment",
        "profile_version": "1",
        "policy_version": policy,
        "source_evidence": [f"sow:{version}:confirmed synthetic economics"],
        "service_start": "2026-10-01",
        "service_end": "2026-10-31",
        "timezone": "America/New_York",
        "currency": "USD",
        "billing_cadence": "upon_delivery",
        "cost_basis": "Synthetic SOW expressly confirms the US delivery cost",
        "costs_confirmed": True,
        "costs": [
            {
                "source_id": "assessment-team",
                "month": "2026-10-01",
                "location": "US",
                "amount": "10000",
            }
        ],
        "staffing": [],
        "pricing": {
            "total_fee": "24000",
            "allocations": [
                {"month": "2026-10-01", "location": "US", "weight": "1"}
            ],
            "allocation_basis": "Single October service month",
            "minor_unit": "0.01",
        },
    }


async def main() -> None:
    run = uuid.uuid4().hex
    label = f"S21 e2e staging-core {run[:12]}"
    system_creds = secret("officeapp-dev-e2e-user")
    reviewer_creds = secret("officeapp-dev-e2e-approvers-multirole")
    pool = reviewer_creds["user_pool_id"]
    client_id = system_creds["client_id"]
    tokens = {
        "system": mint(
            pool=system_creds["user_pool_id"],
            client=client_id,
            username=system_creds["username"],
            password=system_creds["password"],
        )
    }
    for role, creds in reviewer_creds["roles"].items():
        tokens[role] = mint(
            pool=pool,
            client=client_id,
            username=creds["username"],
            password=creds["password"],
        )

    fixture: dict | None = None
    receipt: dict = {"run": run, "label": label, "base": BASE, "steps": []}

    async with httpx.AsyncClient(base_url=f"{BASE}/api", timeout=360) as client:
        async def request(method: str, path: str, *, role: str = "system", **kwargs):
            headers = {"Authorization": f"Bearer {tokens[role]}"}
            headers.update(kwargs.pop("headers", {}))
            response = await client.request(method, path, headers=headers, **kwargs)
            if not response.is_success:
                raise AssertionError(
                    f"{method} {path} role={role}: {response.status_code} {response.text[:2000]}"
                )
            receipt["steps"].append(
                {"method": method, "path": path, "role": role, "status": response.status_code}
            )
            return response.json() if response.content else None

        try:
            identities = {}
            for role in tokens:
                await request("GET", "/clients?size=1", role=role)
                identities[role] = await request("GET", "/me", role=role)
            by_id = {row["id"]: role for role, row in identities.items()}
            assert len(by_id) == len(identities), "Cognito role slots must be distinct"

            fixture = await request(
                "POST",
                "/dev/test-fixtures",
                json={
                    "label": label,
                    "reviewer_ids": sorted(by_id),
                    "hours": 1,
                },
            )
            deal, account = fixture["opportunity_id"], fixture["client_id"]
            receipt["fixture"] = fixture

            pipeline = await request("GET", f"/pipeline/opportunities/{deal}")
            assert pipeline["opportunity_id"] == deal
            assert pipeline["source_origin"] == "local_test_fixture"
            assert deal in {
                row["opportunity_id"]
                for row in (await request("GET", "/pipeline/opportunities"))["items"]
            }
            detail = await request("GET", f"/deals/{deal}")
            assert detail["client_id"] == account

            content = document(label, run)
            upload = await request(
                "POST",
                "/sows/upload",
                data={"client_id": account, "opportunity_id": deal},
                files={"file": (f"staging-core-{run}.docx", content, MIME)},
            )
            assert upload["status"] == "done", upload
            version = upload["sow_version_id"]
            sow = await request("GET", f"/sow/versions/{version}")
            assert sow["extract_status"] == "complete", sow
            assert Decimal(str(sow["extracted_fields"]["price"]["value"])) == Decimal(24000)
            for field in EXTRACTED_FIELDS:
                cell = sow["extracted_fields"].get(field)
                assert cell is not None, f"extraction omitted {field}"
                await request(
                    "PATCH",
                    f"/sow/versions/{version}/fields/{field}",
                    json={"value": cell["value"]},
                )

            registry = await request("GET", "/delivery-model/commercial/profiles")
            current = (await request("GET", f"/delivery-model/{deal}"))["gm_model"]
            saved = await request(
                "POST",
                f"/delivery-model/{deal}/commercial/versions",
                json={
                    "sow_version_id": version,
                    "expected_gm_model_id": current["id"] if current else None,
                    "inputs": commercial_inputs(
                        sow["sow_id"], version, registry["policy"]["version"]
                    ),
                    "change_reason": "Connected staging proof of exact synthetic economics",
                },
            )
            gm = saved["gm_model"]["id"]
            computed = saved["gm_model"]["computed"]
            assert computed["complete"], computed
            assert Decimal(str(computed["revenue_us"])) == Decimal(24000), computed
            assert Decimal(str(computed["cost_us"])) == Decimal(10000), computed

            await request("POST", f"/sow/versions/{version}/submit")
            plan = await request("GET", f"/approvals/plan/{deal}")
            functions = [row["function"] for row in plan["rows"]]
            assert functions == ["delivery", "hr", "sales", "finance", "legal"], functions
            package = await request(
                "POST",
                f"/approvals/packages/{deal}",
                json={"sow_version_id": version, "gm_model_id": gm},
            )
            for function in functions:
                assignment = next(
                    row for row in package["assignments"] if row["function"] == function
                )
                role = by_id.get(assignment["approver_id"])
                assert role is not None, f"no token for {function} assignment {assignment}"
                current_package = await request(
                    "GET", f"/approvals/packages/{package['id']}", role=role
                )
                current_assignment = next(
                    row
                    for row in current_package["assignments"]
                    if row["function"] == function
                )
                assert current_assignment["can_decide"], current_assignment
                package = await request(
                    "POST",
                    f"/approvals/packages/{package['id']}/decisions/{function}",
                    role=role,
                    json={
                        "decision": "approve",
                        "reason": "Reviewed connected synthetic staging source",
                        "expected_package_hash": package["package_hash"],
                    },
                )
            assert package["status"] == "ready_to_sign", package

            signed = await request(
                "POST",
                f"/signed-sow/{package['id']}/file",
                files={"file": ("executed.docx", content, MIME)},
                data={"has_signature_evidence": "true"},
            )
            assert signed["file_hash"] == hashlib.sha256(content).hexdigest()
            verified = await request("POST", f"/signed-sow/{package['id']}/verify")
            assert verified["verify_status"] == "verified", verified
            await request(
                "POST",
                f"/handoff/{package['id']}/accept",
                role="delivery",
                json={
                    "staffing_confirmed": True,
                    "billing_setup_confirmed": True,
                    "po_confirmed": True,
                    "notes": "Connected staging delivery acceptance",
                },
            )
            await request("POST", f"/signed-sow/{package['id']}/release")
            projects = [
                row
                for row in (await request("GET", "/projects"))["items"]
                if row["package_id"] == package["id"]
            ]
            assert len(projects) == 1 and projects[0]["gm_model_id"] == gm

            forecast = await request(
                "POST", f"/forecast/{gm}", role="delivery", json={"lines": []}
            )
            assert forecast["forecast_revenue"] == "24000.00", forecast
            assert forecast["forecast_cost_us"] == "10000.00", forecast
            params = {"as_of": "2026-10-31T20:00:00Z", "future_quarters": 4}
            account_outlook = await request(
                "GET", "/forecast/outlook", params={**params, "account_id": account}
            )
            company_outlook = await request("GET", "/forecast/outlook", params=params)
            for outlook in (account_outlook, company_outlook):
                row = next(item for item in outlook["rows"] if item["source_id"] == gm)
                assert row["source_version"] == version
            assert Decimal(str(account_outlook["current_month"]["signed"])) == Decimal(24000)
            assert Decimal(str(account_outlook["current_month"]["cost"])) == Decimal(10000)

            # — release-push staging extensions (2026-10-04) —
            # Quarters reconcile: the e2e scope sees only this fixture, so the
            # account view and the company view must agree bucket by bucket,
            # including the next two quarters.
            assert len(account_outlook["quarters"]) >= 3, account_outlook["quarters"]
            assert account_outlook["quarters"] == company_outlook["quarters"]
            assert Decimal(str(company_outlook["current_month"]["signed"])) == Decimal(24000)

            # Resource demand reaches People planning from the released project.
            sources = await request("GET", "/people/demand", role="delivery")
            source = next(
                row for row in sources["items"]
                if row["source_id"] == projects[0]["project_id"]
            )
            publication = await request(
                "POST", "/people/demand/project-publications", role="delivery",
                json={
                    "project_id": projects[0]["project_id"],
                    "expected_source_version_id": source["source_version_id"],
                    "expected_publication_version_id": source.get("publication_version_id"),
                    "request_key": f"release-push:{run}",
                    "reason": "Connected staging release-push demand publication",
                },
            )
            allocation = await request("GET", "/people/demand/allocation", role="delivery")
            assert allocation is not None

            # An amendment draft on the signed contract defers supersession
            # (original stays active) and never double counts revenue.
            amendment_bytes = document(f"{label} amendment", uuid.uuid4().hex)
            draft = await request(
                "POST", f"/sows/{deal}/versions",
                files={"file": (f"amendment-{run}.docx", amendment_bytes, MIME)},
            )
            assert draft["amendment_draft_of"] == version, draft
            assert draft["supersedes"] is None, draft
            after_amend = await request("GET", "/forecast/outlook", params=params)
            amended_rows = [r for r in after_amend["rows"] if r["source_id"] == gm]
            baseline_rows = [r for r in company_outlook["rows"] if r["source_id"] == gm]
            assert len(amended_rows) == len(baseline_rows), (amended_rows, baseline_rows)
            assert Decimal(str(after_amend["current_month"]["signed"])) == Decimal(24000)

            # Comments, actions and navigation context persist around the deal.
            comment = await request(
                "POST", f"/deals/{deal}/comments",
                json={"body": "Release-push connected persistence check", "pinned": True},
            )
            listed = await request("GET", f"/deals/{deal}/comments")
            comment_rows = listed["items"] if isinstance(listed, dict) else listed
            assert any(c["id"] == comment["id"] and c["pinned"] for c in comment_rows)
            action = await request(
                "POST", "/next-actions",
                json={"opportunity_id": deal, "title": "Release-push action",
                      "assignee_user_id": identities["system"]["id"]},
            )
            fetched_action = await request("GET", f"/next-actions/{action['id']}")
            assert fetched_action["title"] == "Release-push action"
            revisit = await request("GET", f"/pipeline/opportunities/{deal}")
            assert revisit["opportunity_id"] == deal

            receipt.update(
                demand_publication_id=publication.get("version_id") or publication.get("id"),
                amendment_draft_version_id=draft["sow_version_id"],
                comment_id=comment["id"],
                next_action_id=action["id"],
            )
            receipt.update(
                status="passed",
                client_id=account,
                deal_id=deal,
                sow_version_id=version,
                gm_model_id=gm,
                package_id=package["id"],
                project_id=projects[0]["project_id"],
                forecast_id=forecast["id"],
                functions=functions,
                economics={"revenue": "24000", "cost": "10000"},
            )
        finally:
            if fixture is not None:
                deleted = await request(
                    "DELETE",
                    f"/clients/{fixture['client_id']}?reason=connected%20staging%20teardown",
                )
                receipt["deletion_job_id"] = deleted["job_id"]
                # Parent deletion is a three-level durable graph
                # (SOW -> opportunity -> client). Each level becomes eligible
                # on a later one-minute worker cycle, so observe the actual
                # asynchronous contract instead of imposing an HTTP timeout.
                for _ in range(60):
                    state = await request(
                        "GET", f"/deletion-jobs/{deleted['job_id']}"
                    )
                    if state["status"] == "done":
                        receipt["cleanup_status"] = "done"
                        break
                    await asyncio.sleep(4)
                else:
                    receipt["cleanup_status"] = state["status"]
                    raise AssertionError(f"cleanup did not finish: {state}")

    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
