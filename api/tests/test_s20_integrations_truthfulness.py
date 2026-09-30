"""T43 · integrations page truthfulness (S20 · W5).

Per review + L19:
> Settings claims HubSpot writes three governance properties, contrary
> to the supplied read-only architecture. It marks Cognito Not
> configured despite successful Cognito sign-in, and combines document
> storage/signature as Not configured despite an uploaded SOW.
> Separate component states and derive them from verified configuration.

Per contract §1: `Not configured` is truthful only when the config is
actually absent. When configuration IS present, the card MUST show it
verified.

**Skeleton, xfail until W4 lands the derived-from-config integrations
surface.**

Test cases:
  1. HubSpot card: `read_only` when only read scopes are granted (F1
     in isolation.md is definitive tonight). MUST NOT claim writeback.
  2. Cognito card: `verified` when the caller's own token was minted
     against the configured pool (the fact you made the request
     proves it).
  3. Document storage card: `verified` when S3 bucket policy + KMS
     grants exist and at least one document has been uploaded.
  4. Document signature card: separate row; NOT combined with storage.
  5. Health surface: an empty stuck-events list is NOT "every webhook
     has been processed"; the card must show received / processed /
     last reconcile watermarks + backlog age.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W4 integrations page derivation", strict=False)
@pytest.mark.asyncio
async def test_hubspot_read_only_shown_when_write_scope_missing(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4")
@pytest.mark.asyncio
async def test_cognito_verified_by_current_request(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4")
@pytest.mark.asyncio
async def test_document_storage_verified_from_config(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4")
@pytest.mark.asyncio
async def test_document_signature_is_separate_row(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W4 health surface (L20)")
@pytest.mark.asyncio
async def test_health_page_shows_watermarks_not_empty_queue(session):
    raise AssertionError("skeleton")
