"""HubSpot API client.

Blueprint §6.1: never trust the webhook payload — re-read the deal via the
CRM v3 API before touching state.

The real client uses `httpx.AsyncClient` and a bearer token loaded from
`HUBSPOT_TOKEN` (the name Terraform uses when injecting the secret) with
a fall-back to the older `HUBSPOT_ACCESS_TOKEN` name for tests and local
dev. `StubHubSpotClient` returns canned fixtures for tests; wire it in
via FastAPI's `dependency_overrides`.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger("hubspot")


HUBSPOT_API_BASE = "https://api.hubapi.com"

# S18 §2 · F7 — HubSpot's public rate limit is 100 req / 10s per portal.
# We respect Retry-After when present, otherwise back off exponentially.
_RATE_LIMIT_MAX_RETRIES = 4
_RATE_LIMIT_BASE_DELAY = 1.0


class HubSpotClient:
    """Thin async wrapper over the HubSpot CRM v3 REST API."""

    def __init__(self, access_token: str | None = None, base_url: str = HUBSPOT_API_BASE) -> None:
        token = (
            access_token
            or os.environ.get("HUBSPOT_TOKEN", "")
            or os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
        )
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

    def scan_scope(self) -> dict[str, str]:
        values = {"tenant": os.environ.get("DEALGATE_TENANT_ID"),
            "environment": os.environ.get("DEALGATE_ENV"),
            "portal_id": os.environ.get("HUBSPOT_PORTAL_ID")}
        if not all(values.values()):
            raise ValueError("HubSpot scan requires explicit tenant, environment and portal ID")
        return values

    async def get_archived_deal(self, deal_id: str) -> dict[str, Any] | None:
        """Only an explicit archived record proves deletion; a 404 is unresolved."""
        try:
            return await self._get(f"/crm/v3/objects/deals/{deal_id}", params={"archived": "true"})
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return None
            raise

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET with 429 retry (S18 §2 F7).

        HubSpot returns 429 with a ``Retry-After`` header (seconds) when the
        portal exceeds 100 req / 10s. We honour it; if the header is missing
        we back off exponentially (1s, 2s, 4s, 8s) up to
        ``_RATE_LIMIT_MAX_RETRIES``. On the final failure we re-raise the
        ``HTTPStatusError`` so the caller (backfill / webhook worker) can
        count it as an error rather than silently dropping the deal.
        """

        attempts = 0
        while True:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self._base_url}{path}",
                    headers=self._headers(),
                    params=params,
                )
            if r.status_code == 429 and attempts < _RATE_LIMIT_MAX_RETRIES:
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else _RATE_LIMIT_BASE_DELAY * (2 ** attempts)
                except ValueError:
                    delay = _RATE_LIMIT_BASE_DELAY * (2 ** attempts)
                log.info(
                    "hubspot_429_backoff",
                    attempt=attempts + 1,
                    delay=delay,
                    path=path,
                )
                await asyncio.sleep(delay)
                attempts += 1
                continue
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

    # S18 §2 + S19 slice 1: every column the Pipeline surface caches on
    # `opportunity` gets pulled in one CRM read. The label itself lives on
    # the pipelines endpoint (see `list_pipelines`) — the mapper resolves
    # `dealstage` (id) to its label via the mirror.
    _DEAL_PROPERTIES: str = (
        "dealname,dealstage,pipeline,hubspot_owner_id,engagement_type,"
        "amount,closedate,deal_currency_code,createdate,"
        "hs_lastmodifieddate,notes_last_updated"
    )

    async def get_deal(self, deal_id: str, *, additional_properties: tuple[str, ...] = ()) -> dict[str, Any]:
        """Return the deal record including hubspot_owner_id and associated company."""

        return await self._get(
            f"/crm/v3/objects/deals/{deal_id}",
            params={
                "properties": ",".join(dict.fromkeys([*self._DEAL_PROPERTIES.split(","), *additional_properties])),
                "associations": "companies",
            },
        )

    async def list_deals_page(
        self, *, after: str | None = None, limit: int = 100,
        additional_properties: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Paged deal fetch for the backfill worker. Returns raw payload —
        caller handles ``.results`` and ``.paging.next.after``."""

        params: dict[str, Any] = {
            "properties": ",".join(dict.fromkeys([*self._DEAL_PROPERTIES.split(","), *additional_properties])),
            "associations": "companies",
            "limit": limit,
        }
        if after:
            params["after"] = after
        return await self._get("/crm/v3/objects/deals", params=params)

    async def get_deal_owner(self, owner_id: str) -> dict[str, Any]:
        """Return the owner record for a HubSpot user id."""

        return await self._get(f"/crm/v3/owners/{owner_id}")

    async def list_pipelines(self) -> dict[str, Any]:
        """S19 slice 1 B1 — pull every deal pipeline + its stages.

        The mapper caches this once per backfill / webhook run and resolves
        deal stage ids to labels + closed flags. Portals with more than one
        pipeline get one row each; a single-pipeline portal like SmarTek21
        still uses the mirror so unknown-stage drift raises loudly (G11).
        """

        return await self._get("/crm/v3/pipelines/deals")

    async def get_company(self, company_id: str, *, additional_properties: tuple[str, ...] = ()) -> dict[str, Any]:
        """Return the company record."""

        return await self._get(
            f"/crm/v3/objects/companies/{company_id}",
            params={"properties": ",".join(dict.fromkeys([
                "name", "domain", "hubspot_owner_id", "hs_lastmodifieddate", *additional_properties,
            ]))},
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
        pipelines: list[dict[str, Any]] | None = None,
    ) -> None:
        # Skip the parent __init__ so we don't require the env var in tests.
        self._token = "stub"
        self._base_url = "http://stub"
        self.deals: dict[str, dict[str, Any]] = deals or {}
        self.owners: dict[str, dict[str, Any] | None] = owners or {}
        self.companies: dict[str, dict[str, Any]] = companies or {}
        self.pipelines: list[dict[str, Any]] = pipelines or []
        # Records every ``update_deal`` call so write-back tests can assert
        # on the exact HubSpot payload the service sent.
        self.updates: list[dict[str, Any]] = []
        # When set, the next ``update_deal`` call raises the given error.
        # Tests use this to simulate HubSpot 429 / 404 / 500 responses.
        self.update_error: Exception | None = None

    def scan_scope(self) -> dict[str, str]:
        return {"tenant": "synthetic", "environment": "local", "portal_id": "stub"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == "/crm/v3/owners":
            archived = (params or {}).get("archived") == "true"
            return {"results": [row for row in self.owners.values()
                if row and bool(row.get("archived", False)) == archived]}
        if path in {"/crm/v3/properties/deals", "/crm/v3/properties/companies"}:
            return {"results": []}
        raise KeyError(f"No stub response for {path}")

    async def get_archived_deal(self, deal_id: str) -> dict[str, Any] | None:
        return {"id": deal_id, "archived": True} if deal_id not in self.deals else None

    async def get_deal(self, deal_id: str, *, additional_properties: tuple[str, ...] = ()) -> dict[str, Any]:
        return self.deals[deal_id]

    async def list_pipelines(self) -> dict[str, Any]:
        return {"results": list(getattr(self, "pipelines", []))}

    async def list_deals_page(
        self, *, after: str | None = None, limit: int = 100,
        additional_properties: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        deal_ids = sorted(self.deals.keys())
        start = 0
        if after:
            try:
                start = deal_ids.index(after) + 1
            except ValueError:
                start = 0
        page = deal_ids[start : start + limit]
        results = [self.deals[did] for did in page]
        next_after = page[-1] if len(page) == limit and start + limit < len(deal_ids) else None
        payload: dict[str, Any] = {"results": results}
        if next_after:
            payload["paging"] = {"next": {"after": next_after}}
        return payload

    async def get_deal_owner(self, owner_id: str) -> dict[str, Any]:
        owner = self.owners.get(owner_id)
        if owner is None:
            # Simulate HubSpot returning 404 when the owner is missing/inactive.
            raise KeyError(owner_id)
        return owner

    async def get_company(self, company_id: str, *, additional_properties: tuple[str, ...] = ()) -> dict[str, Any]:
        return self.companies[company_id]

    async def update_deal(self, deal_id: str, properties: dict[str, Any]) -> None:
        if self.update_error is not None:
            raise self.update_error
        self.updates.append({"deal_id": deal_id, "properties": dict(properties)})


def get_hubspot_client() -> HubSpotClient:
    """FastAPI dependency. Override with `StubHubSpotClient` in tests."""

    return HubSpotClient()
