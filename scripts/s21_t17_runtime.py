"""Lead-only isolated T17 fixture/runtime; no completed business states seeded."""
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

from sqlalchemy import text
from sqlalchemy.engine import make_url


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


url = make_url(os.environ["POSTGRES_URL"])
require((url.drivername, url.username, url.host, url.port) ==
        ("postgresql+asyncpg", "s21", "127.0.0.1", 55421) and not url.password and not url.query,
        "Exact owned loopback database required")
require(re.fullmatch(r"s21_t17_[0-9a-f]{32}", url.database or ""), "Fresh T17 database required")
require(os.environ.get("DEALGATE_ENV") == "local" and os.environ.get("DEALGATE_TENANT_ID") == url.database,
        "Explicit local environment and matching tenant required")
require(os.environ.get("S21_T17_PROVIDER_CALLS") == "lead-authorized", "Explicit provider authorization required")
require(not any(k.startswith("PG") for k in os.environ), "Remove PG overrides")
RUN = uuid.UUID(url.database.removeprefix("s21_t17_"))
RECEIPT = Path(os.environ["S21_T17_RECEIPT"])
require(RECEIPT.parent.resolve() == Path("/tmp").resolve() and not RECEIPT.is_symlink(), "Literal /tmp receipt required")
PREFIX = f"verification/s21/{RUN.hex}/"
os.environ.update(ALLOW_DEV_SEED_ENDPOINT="1", AWS_REGION="us-east-2",
                  AWS_EC2_METADATA_DISABLED="true", SOW_BUCKET="officeapp-dev-sows-669810405473",
                  AGREEMENTS_BUCKET="officeapp-dev-agreements-669810405473")

from app.auth import AuthUser, current_user
from app.db import session_factory
from app.integrations.bedrock_sow_extract import BedrockSowExtract, get_bedrock_sow
from app.integrations.s3_sow import SowS3, get_sow_s3
from app.integrations import s3_evidence
from app.integrations.ses import StubSES, get_ses_client
from app.main import app
from app.models.user import User
from fastapi import Header, HTTPException


def read_receipt():
    require(not RECEIPT.is_symlink(), "Receipt must not become a symlink")
    value = json.loads(RECEIPT.read_text())
    require(value["database"] == url.database and value["run"] == str(RUN), "Receipt target mismatch")
    return value


def event(value):
    log = Path(str(RECEIPT) + ".operations.jsonl")
    require(not log.is_symlink(), "Operation log must not be a symlink")
    with log.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


original_evidence_key = s3_evidence._build_s3_key
def owned_evidence_key(*args, **kwargs):
    key = PREFIX + original_evidence_key(*args, **kwargs)
    event({"operation": "agreement_key_intent", "bucket": "officeapp-dev-agreements-669810405473", "key": key})
    return key


s3_evidence._build_s3_key = owned_evidence_key


class OwnedEvidence(s3_evidence.EvidenceS3):
    def __init__(self):
        super().__init__(bucket="officeapp-dev-agreements-669810405473", region="us-east-2")

    def generate_upload_url(self, *args, **kwargs):
        raise RuntimeError("Use server-mediated agreement upload")

    def generate_download_url(self, key):
        require(key.startswith(PREFIX), "Agreement key outside run")
        return super().generate_download_url(key)


async def guard(session, empty=False):
    row = (await session.execute(text("SELECT current_database(),current_user,pg_get_userbyid(datdba),"
        "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))).one()
    require(tuple(row) == (url.database, "s21", "s21", f"owned-s21-t17:{RUN}"), "Ownership mismatch")
    require((await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            == ["20261003_0063_agreement_versions"], "Schema mismatch")
    if empty:
        for table in ("client", "opportunity", "sow", "sow_version", "gm_model", "approval_package", "task", "project"):
            require(await session.scalar(text(f'SELECT count(*) FROM "{table}"')) == 0, f"Nonempty {table}")


async def identity(x_test_user: str = Header()):
    person = next((p for p in read_receipt()["people"].values() if p["email"] == x_test_user), None)
    if person is None:
        raise HTTPException(401, "Unknown isolated fixture identity")
    return AuthUser(id=uuid.UUID(person["id"]), email=person["email"], name=person["name"], groups=tuple(person["groups"]))


class OwnedStorage(SowS3):
    def __init__(self):
        super().__init__(bucket="officeapp-dev-sows-669810405473", region="us-east-2")

    def check(self, key):
        require(key.startswith(PREFIX), "Storage key outside exact run prefix")

    def build_key(self, *args, **kwargs):
        key = PREFIX + super().build_key(*args, **kwargs)
        event({"operation": "key_intent", "key": key})
        return key

    def put_object(self, key, body, content_type):
        self.check(key)
        event({"operation": "put_intent", "key": key, "bytes": len(body)})
        result = super().put_object(key, body, content_type)
        event({"operation": "put_complete", "key": key})
        return result

    def download_bytes(self, key):
        self.check(key)
        return super().download_bytes(key)

    def generate_download_url(self, key):
        self.check(key)
        return super().generate_download_url(key)

    def generate_upload_url(self, *args, **kwargs):
        raise RuntimeError("T17 requires actual server-mediated upload, not untracked presigned PUT")

    def delete_object(self, key):
        self.check(key)
        event({"operation": "delete_marker_intent", "key": key})
        return super().delete_object(key)


app.dependency_overrides[current_user] = identity
storage, mail = OwnedStorage(), StubSES()
evidence = OwnedEvidence()
app.dependency_overrides[get_sow_s3] = lambda: storage
app.dependency_overrides[get_bedrock_sow] = lambda: BedrockSowExtract()
app.dependency_overrides[get_ses_client] = lambda: mail
app.dependency_overrides[s3_evidence.get_evidence_s3] = lambda: evidence


async def seed():
    import httpx
    require(not RECEIPT.exists() and not Path(str(RECEIPT) + ".operations.jsonl").exists()
            and not Path(str(RECEIPT) + ".operations.jsonl").is_symlink(),
            "Receipt exists: inspect partial operations, never reseed")
    roles = {"owner": ["Sales", "SystemAdmin"], "delivery": ["Delivery"], "hr": ["HR"],
             "sales": ["Sales"], "finance": ["Finance"], "legal": ["Legal"], "normal": ["SystemAdmin"]}
    people = {}
    for role, groups in roles.items():
        email = f"t17-{RUN.hex[:8]}-{role}@example.test"
        people[role] = dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")), email=email,
            name=f"T17 {role.title()} {RUN.hex[:8]}", groups=groups + ([] if role == "normal" else ["officeapp-e2e"]))
    value = dict(database=url.database, run=str(RUN), prefix=PREFIX, people=people, status="seed_intent",
        boundary="Local named identities, real PG/S3/Bedrock, explicit SES sink. No staging or inbox proof.")
    async with session_factory() as session:
        await guard(session, empty=True)
        with RECEIPT.open("x") as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for person in people.values():
            session.add(User(**{**person, "id": uuid.UUID(person["id"])}))
        await session.commit()
    event({"operation": "identities_committed"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/dev/test-fixtures", headers={"X-Test-User": people["owner"]["email"]},
            json={"label": f"T17 connected {RUN.hex[:8]}", "hours": 8,
                  "reviewer_ids": [p["id"] for key, p in people.items() if key != "normal"]})
        event({"operation": "fixture_grant", "status": response.status_code, "body": response.json()})
        require(response.status_code == 201, "Fixture grant failed; preserve receipt")
        value.update(fixture=response.json(), status="ready_for_browser")
    with tempfile.NamedTemporaryFile(mode="w", dir=RECEIPT.parent, prefix=RECEIPT.name + ".", delete=False) as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = stream.name
    os.replace(temporary, RECEIPT)
    print(json.dumps(value), flush=True)


if __name__ == "__main__":
    require(sys.argv[1:] in (["seed"], ["serve"]), "Use seed or serve")
    if sys.argv[1] == "seed":
        asyncio.run(seed())
    else:
        import uvicorn
        require(read_receipt()["status"] == "ready_for_browser", "Incomplete seed")
        async def verify_target():
            async with session_factory() as session:
                await guard(session)
        app.on_event("startup")(verify_target)
        port = int(os.environ.get("S21_T17_PORT", "8211"))
        require(port in (8211, 8212), "Use an explicitly owned T17 API port")
        uvicorn.run(app, host="127.0.0.1", port=port)
