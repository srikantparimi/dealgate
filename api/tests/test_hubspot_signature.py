"""Unit tests for the HubSpot v3 signature helper.

The scheme:
  base_string = method + uri + body + timestamp
  signature   = base64(hmac_sha256(secret, base_string))
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from app.integrations.hubspot_signature import verify_v3

SECRET = "unit-test-secret"


def _sign(method: str, uri: str, body: bytes, timestamp: str, secret: str = SECRET) -> str:
    base = f"{method}{uri}{body.decode('utf-8')}{timestamp}"
    digest = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def test_valid_signature_verifies():
    method = "POST"
    uri = "https://dealgate.example.com/integrations/hubspot/webhook"
    body = b'{"eventId": 1, "subscriptionType": "deal.creation"}'
    ts = "1737000000000"
    sig = _sign(method, uri, body, ts)
    assert verify_v3(SECRET, method, uri, body, ts, sig) is True


def test_tampered_body_fails():
    method = "POST"
    uri = "https://dealgate.example.com/integrations/hubspot/webhook"
    body = b'{"eventId": 1}'
    ts = "1737000000000"
    sig = _sign(method, uri, body, ts)
    tampered = b'{"eventId": 2}'
    assert verify_v3(SECRET, method, uri, tampered, ts, sig) is False


def test_wrong_secret_fails():
    method = "POST"
    uri = "https://dealgate.example.com/integrations/hubspot/webhook"
    body = b"{}"
    ts = "1737000000000"
    sig = _sign(method, uri, body, ts, secret="other-secret")
    assert verify_v3(SECRET, method, uri, body, ts, sig) is False


def test_missing_secret_or_headers_fails():
    assert verify_v3("", "POST", "https://x", b"{}", "1", "sig") is False
    assert verify_v3(SECRET, "POST", "https://x", b"{}", "", "sig") is False
    assert verify_v3(SECRET, "POST", "https://x", b"{}", "1", "") is False


def test_uses_constant_time_compare(monkeypatch):
    """Regression guard: verify_v3 must not fall back to `==` comparison."""

    called = {"n": 0}
    real_compare = hmac.compare_digest

    def _spy(a, b):
        called["n"] += 1
        return real_compare(a, b)

    monkeypatch.setattr("app.integrations.hubspot_signature.hmac.compare_digest", _spy)

    method = "POST"
    uri = "https://dealgate.example.com/hook"
    body = b"{}"
    ts = "1737000000000"
    sig = _sign(method, uri, body, ts)
    verify_v3(SECRET, method, uri, body, ts, sig)
    assert called["n"] == 1
