"""Tavily web-search adapter — public research for the Opportunity Adviser.

The Opportunity Adviser (S7 wave 2) does a *public* research pass before it
asks Bedrock to propose a team. The query is built by
:func:`app.services.adviser.public_search_terms` and is guaranteed to contain
only publicly-safe fields (client_name, website, industry, geography). The
confidential problem statement and any uploaded notes are never put into a
search query — Blueprint §5 guardrail.

Design mirrors the other integrations in this package:

- A real client (:class:`TavilyClient`) that talks to
  ``POST https://api.tavily.com/search`` with an ``httpx.AsyncClient``.
- A tiny in-process :class:`StubTavily` used by tests + local dev.
- Any failure (missing API key, 5xx, 4xx, timeout, malformed body) is
  swallowed and returns an empty list. The caller flips
  ``research_status = "unavailable"`` — Blueprint rule 6: never invent
  sources.
"""

from __future__ import annotations

import os
from typing import Any, TypedDict

import httpx
import structlog

log = structlog.get_logger("integrations.tavily")


TAVILY_API_BASE = "https://api.tavily.com/search"


class Source(TypedDict):
    """Public-research citation. Matches the ``sources`` JSON shape on
    ``adviser_estimate`` — the UI + persisted row use the same schema."""

    url: str
    title: str
    snippet: str


class TavilyClient:
    """Thin async wrapper over the Tavily ``/search`` endpoint.

    ``TAVILY_API_KEY`` is read from the environment. When it is missing, or
    the upstream call fails for any reason, :meth:`search` returns ``[]`` and
    logs the failure. Callers must not raise on our behalf.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = TAVILY_API_BASE,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = (api_key or os.environ.get("TAVILY_API_KEY", "")).strip()
        self._base_url = base_url
        self._timeout = timeout

    async def search(self, query: str, max_results: int = 5) -> list[Source]:
        """Return up to ``max_results`` public-web citations for ``query``.

        Never raises — a missing key, HTTP error, or malformed body all
        collapse to an empty list. The adviser service treats an empty list
        as "research unavailable" and continues without invented sources.
        """

        if not self._api_key:
            log.info("tavily_api_key_missing", query=query)
            return []
        if not query or not query.strip():
            return []

        body = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(self._base_url, json=body)
            if r.status_code >= 400:
                log.warning(
                    "tavily_http_error",
                    status=r.status_code,
                    query=query,
                )
                return []
            payload = r.json()
        except Exception as exc:  # noqa: BLE001 — never raise to caller.
            log.warning("tavily_request_failed", query=query, error=str(exc))
            return []

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        out: list[Source] = []
        for item in results[:max_results]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("content") or item.get("snippet") or "").strip()
            if not url:
                continue
            out.append({"url": url, "title": title, "snippet": snippet})
        return out


class StubTavily(TavilyClient):
    """In-process Tavily for tests + local dev.

    Set :attr:`results` to control the return value of :meth:`search`. When
    :attr:`fail_with` is set, the call raises after being recorded so we can
    exercise the "unavailable" branch without a network stub. The service
    layer still swallows the exception per the real-client contract, so this
    doubles as an integration test of that contract.
    """

    def __init__(
        self,
        *,
        results: list[Source] | None = None,
        fail_with: str | None = None,
    ) -> None:
        # Skip the parent constructor so we don't require TAVILY_API_KEY in
        # tests; StubTavily deliberately ignores it.
        self._api_key = "stub"
        self._base_url = TAVILY_API_BASE
        self._timeout = 10.0
        self.results: list[Source] = list(results or [])
        self.fail_with = fail_with
        self.calls: list[dict[str, Any]] = []

    async def search(self, query: str, max_results: int = 5) -> list[Source]:
        self.calls.append({"query": query, "max_results": max_results})
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        return list(self.results[:max_results])


def get_tavily_client() -> TavilyClient:
    """Factory the service layer uses. Tests override with :class:`StubTavily`."""

    return TavilyClient()


__all__ = [
    "Source",
    "StubTavily",
    "TAVILY_API_BASE",
    "TavilyClient",
    "get_tavily_client",
]
