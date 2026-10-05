"""Generate explicit synthetic fixed-deliverable terms, never a real agreement."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def document(client):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = ET.Element(f"{{{ns}}}document")
    body = ET.SubElement(root, f"{{{ns}}}body")
    lines = [
        f"STATEMENT OF WORK: T17 synthetic assessment. Client: {client}. Supplier: SmarTek21.",
        "This is an isolated synthetic test, not a real agreement or signature.",
        "Fixed-price deliverable-based assessment. Total contract fee USD 24000.00. Currency USD.",
        "Service start 2026-10-01. Service end 2026-10-31. Notice date 2026-10-15.",
        "Scope: Assess the synthetic data platform and deliver a written assessment report.",
        "Deliverable: Written assessment report on 2026-10-31. Client accepts within five business days.",
        "Billing: invoice USD 24000 upon delivery in October 2026, allocated entirely to US.",
        "All delivery costs are confirmed at USD 10000 in October 2026, allocated entirely to US.",
        "Cost basis: fixed subcontracted assessment fee, inclusive of all labor. No additional hourly staff or expenses.",
        "No travel, reimbursements, recurring fees, or additional tax charges in these synthetic economics.",
        "Workstream assessment. Location US. Timezone America/New_York. Currency minor unit 0.01.",
        "Assumptions: client supplies synthetic data. Exclusions: implementation and production access.",
        "Client domain synthetic.example.test. No NDA or MSA is required for this fictional exercise.",
        "Client signature block: Signatory name Alex Example. Organization Client. Signature [synthetic executed signature].",
        "Supplier signature block: Signatory name Casey Example. Organization SmarTek21. Signature [synthetic executed signature].",
    ]
    for line in lines:
        ET.SubElement(ET.SubElement(ET.SubElement(body, f"{{{ns}}}p"), f"{{{ns}}}r"), f"{{{ns}}}t").text = line
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", ET.tostring(root))
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
    return output.getvalue()


if __name__ == "__main__":
    receipt = json.loads(Path(sys.argv[1]).read_text())
    run = receipt["run"].replace("-", "")
    target = Path(f"/tmp/s21-t17-{run[:8]}-sow.docx")
    content = document(f"S21 e2e {receipt['fixture']['run_id']} T17 connected {run[:8]}")
    with target.open("xb") as stream:
        stream.write(content)
    print(json.dumps({"path": str(target), "sha256": hashlib.sha256(content).hexdigest(),
        "expected_revenue": "24000", "expected_cost": "10000", "expected_gm": "14000"}))
