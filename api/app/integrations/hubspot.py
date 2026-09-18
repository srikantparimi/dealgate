"""HubSpot API client.

Blueprint §6.1: never trust the webhook payload — re-read the deal via the
CRM v3 API before touching state.

The real client uses `httpx.AsyncClient` and a bearer token loaded from
`HUBSPOT_ACCESS_TOKEN`. `StubHubSpotClient` returns canned fixtures for
tests and local dev; wire it in via FastAPI's `dependency_overrides`.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger("hubspot")


HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotClient:
    """Thin async wrapper over the HubSpot CRM v3 REST API."""

    def __init__(self, access_token: str | None = None, base_url: str = HUBSPOT_API_BASE) -> None:
        token = access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
        if not token:
            # Loud but not fatal: unit tests always use the stub. Production
            # deployments fail-fast on the first request rather than at import.
            log.warning("hubspot_access_token_missing")
        self._token = token
        self._base_url = base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{self._base_url}{path}",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()

    async def _patch(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        headers = {**self._headers(), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.patch(
                f"{self._base_url}{path}",
                headers=headers,
                json=json_body,
            )
            r.raise_for_status()
            return r.json() if r.content else {}

    async def get_deal(self, deal_id: str) -> dict[str, Any]:
        """Return the deal record including hubspot_owner_id and associated company."""

        return await self._get(
            f"/crm/v3/objects/deals/{deal_id}",
            params={
                "properties": "dealname,dealstage,pipeline,hubspot_owner_id,engagement_type",
                "associations": "companies",
            },
        )

    async def get_deal_owner(self, owner_id: str) -> dict[str, Any]:
        """Return the owner record for a HubSpot user id."""

        return await self._get(f"/crm/v3/owners/{owner_id}")

    async def get_company(self, company_id: str) -> dict[str, Any]:
        """Return the company record."""

        return await self._get(
            f"/crm/v3/objects/companies/{company_id}",
            params={"properties": "name,domain"},
        )

    async def update_deal(self, deal_id: str, properties: dict[str, Any]) -> None:
        """Write DealGate governance properties back to a HubSpot deal.

        Uses the CRM v3 ``PATCH /crm/v3/objects/deals/{deal_id}`` endpoint.
        The caller (`app.services.hubspot_writeback`) is responsible for
        restricting ``properties`` to the three governance keys DealGate is
        allowed to write; this method does not re-validate.

        On non-2xx, ``httpx.HTTPStatusError`` bubbles up so the worker can
        distinguish 429 (retry with back-off) from 404 (deal missing) from
        other 4xx/5xx (final failure).
        """

        await self._patch(
            f"/crm/v3/objects/deals/{deal_id}",
            {"properties": properties},
        )


class StubHubSpotClient(HubSpotClient):
    """In-memory HubSpot client for tests and local dev.

    Set `deals`, `owners`, `companies` on construction (or mutate them) to
    control what each `get_*` method returns. Missing keys raise
    `KeyError` so tests fail loudly on unexpected lookups.
    """

    def __init__(
        self,
        deals: dict[str, dict[str, Any]] | None = None,
        owners: dict[str, dict[str, Any] | None] | None = None,
        companies: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        # Skip the parent __init__ so we don't require the env var in tests.
        self._token = "stub"
        self._base_url = "http://stub"
        self.deals: dict[str, dict[str, Any]] = deals or {}
        self.owners: dict[str, dict[str, Any] | None] = owners or {}
        self.companies: dict[str, dict[str, Any]] = companies or {}
        # Records every ``update_deal`` call so write-back tests can assert
        # on the exact HubSpot payload the service sent.
        self.updates: list[dict[str, Any]] = []
        # When set, the next ``update_deal`` call raises the given error.
        # Tests use this to simulate HubSpot 429 / 404 / 500 responses.
        self.update_error: Exception | None = None

    async def get_deal(self, deal_id: str) -> dict[str, Any]:
        return self.deals[deal_id]

    async def get_deal_owner(self, owner_id: str) -> dict[str, Any]:
        owner = self.owners.get(owner_id)
        if owner is None:
            # Simulate HubSpot returning 404 when the owner is missing/inactive.
            raise KeyError(owner_id)
        return owner

    async def get_company(self, company_id: str) -> dict[str, Any]:
        return self.companies[company_id]

    async def update_deal(self, deal_id: str, properties: dict[str, Any]) -> None:
        if self.update_error is not None:
            raise self.update_error
        self.updates.append({"deal_id": deal_id, "properties": dict(properties)})


def get_hubspot_client() -> HubSpotClient:
    """FastAPI dependency. Override with `StubHubSpotClient` in tests."""

    return HubSpotClient()
