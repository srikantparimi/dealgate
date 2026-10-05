"""Provision only a fresh local tenant for the real connected proof."""
import asyncio
import json
import os
import uuid
from urllib.parse import urlparse

url = urlparse(os.environ["POSTGRES_URL"])
if (url.hostname, url.port, url.path) != ("127.0.0.1", 55421, "/s21_journey"):
    raise RuntimeError("Requires owned local s21_journey on literal 127.0.0.1:55421")
tenant = "s21-connected-" + uuid.uuid4().hex
os.environ.update(DEALGATE_TENANT_ID=tenant, DEALGATE_ENV="local",
    DEALGATE_REPORTING_TIMEZONE="America/Los_Angeles", DEALGATE_REPORTING_CURRENCY="USD")

import httpx
from app.auth import AuthUser, current_user
from app.db import session_factory
from app.main import app
from app.models.user import User


async def main():
    async with session_factory() as session:
        owner = User(id=uuid.uuid4(), email=tenant + "@example.test", name="Isolated journey rule owner",
            groups=["SystemAdmin", "officeapp-e2e"])
        session.add(owner)
        await session.commit()
    actor = AuthUser(owner.id, owner.email, owner.name, tuple(owner.groups))
    app.dependency_overrides[current_user] = lambda: actor
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://setup") as client:
            async def request(method, path, **kwargs):
                response = await client.request(method, path, **kwargs)
                assert response.is_success, f"{response.status_code}: {response.text}"
                return response.json()

            assert (await request("GET", "/people/sourcing/rules"))["state"] == "unconfigured"
            assert (await request("GET", "/people/sourcing/automation"))["state"] == "unconfigured"
            rules = await request("POST", "/people/sourcing/rules", json={
                "expected_version_id": None, "request_key": str(uuid.uuid4()),
                "reason": "New isolated connected proof tenant; no existing rules changed",
                "rules": [{"skill": "python", "location": location, "lead_days": 30}
                    for location in ("US", "India")]})
            rule = await request("POST", "/people/sourcing/automation", json={
                "expected_version_id": None, "request_key": str(uuid.uuid4()),
                "reason": "Enable only the newly created isolated proof tenant",
                "enabled": True, "source_scope": "authorized_sources"})
            assert (await request("GET", "/people/sourcing/automation/jobs"))["items"] == []
            print(json.dumps({"tenant": tenant, "owner_id": str(owner.id),
                "sourcing_rule": rules["id"], "automation_rule": rule["id"],
                "scope": "local test_fixture only", "existing_rules_changed": False}), flush=True)
    finally:
        app.dependency_overrides.pop(current_user, None)


if __name__ == "__main__":
    asyncio.run(main())
