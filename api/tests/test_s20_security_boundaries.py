"""T38 · security boundaries (S20 · W5).

Per review + A8:
> Verify token/role checks, private API responses, real notification
> constraints and cleanup isolation; document deferred production
> controls.
>
> Verify /api caching is disabled or safely private and Authorization
> is forwarded, SPA rewriting excludes APIs, and webhook signature
> checks use the correct external URL, method, timestamp and body.
> Verify Cognito issuer, signature, expiry, intended client and
> token_use, then server-side role/scope checks.

**Skeleton — one test per boundary; most are exercised by the FastAPI
test client with tampered / expired / wrong-audience tokens.**

Test cases:
  1. /api responses set `Cache-Control: private, no-store` (or the
     equivalent) so CloudFront cannot cache authorized responses.
  2. Authorization header is forwarded end-to-end (CloudFront →
     ALB → API). A regression that strips it renders every route 401.
  3. Webhook signature validation: HMAC over method + URL + timestamp
     + body; a tampered body fails; a replayed timestamp older than
     the window fails.
  4. Cognito token validation:
     a. wrong issuer → 401.
     b. expired token → 401.
     c. token_use != "access" on an access-token endpoint → 401.
     d. wrong client_id in `aud` → 401.
     e. missing `cognito:groups` for a role-gated endpoint → 403.
  5. Test-data cleanup: `worker/e2e_cleanup.py::_PREFIX_RE` cannot
     match a real client name (74 Sky, Capitec Bank Limited). This
     was validated in isolation.md; the test locks it in.
"""

from __future__ import annotations

import re

import pytest


def test_e2e_cleanup_regex_does_not_match_real_clients():
    """
    Directly imports the regex from `worker.e2e_cleanup` and asserts
    it does not match any real client name we know of. If W1 changes
    the regex, this test catches an over-broad match.
    """
    from worker.e2e_cleanup import _PREFIX_RE  # noqa: WPS433 — intentional import

    real_names = [
        "74 Sky",
        "Capitec Bank Limited",
        "BSC Staffing - UX/UI Designer",
        "Sky Group",
        "3M Company",
    ]
    matches = [n for n in real_names if _PREFIX_RE.match(n)]
    assert matches == [], f"cleanup regex over-matches real names: {matches}"


@pytest.mark.xfail(reason="skeleton; wire to CloudFront + FastAPI headers", strict=False)
@pytest.mark.asyncio
async def test_api_responses_are_not_cacheable(session):
    """
    Given: an authenticated call to /api/pipeline/opportunities.
    Then:  the response Cache-Control includes `private` and either
           `no-store` or `max-age=0`. A shared caching proxy could
           NOT serve the same body to a different Authorization
           header.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_authorization_forwarded_end_to_end(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_webhook_signature_hmac_correct(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_webhook_replay_rejected(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_cognito_wrong_issuer_rejected(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_cognito_expired_rejected(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_cognito_wrong_token_use_rejected(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_cognito_wrong_audience_rejected(session):
    raise AssertionError("skeleton")
