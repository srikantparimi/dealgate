"""HubSpot v3 webhook signature verification.

Docs: https://developers.hubspot.com/docs/api/webhooks/validating-requests

The v3 scheme signs `method + uri + body + timestamp` with HMAC-SHA256 using
the app secret, then base64 encodes the digest. HubSpot sends the digest in
`X-HubSpot-Signature-v3` and the timestamp in `X-HubSpot-Request-Timestamp`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def verify_v3(
    secret: str,
    method: str,
    uri: str,
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """Return True iff `signature` matches the recomputed HMAC.

    - `secret`: `HUBSPOT_APP_SECRET`.
    - `method`: HTTP method (uppercase, e.g. `POST`).
    - `uri`: full request URI including scheme, host, path, and query.
    - `body`: raw request body bytes.
    - `timestamp`: value of `X-HubSpot-Request-Timestamp` header (ms).
    - `signature`: value of `X-HubSpot-Signature-v3` header (base64).

    Uses constant-time comparison.
    """

    if not secret or not signature or not timestamp:
        return False

    body_str = body.decode("utf-8", errors="replace")
    base_string = f"{method}{uri}{body_str}{timestamp}"
    digest = hmac.new(
        secret.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)
