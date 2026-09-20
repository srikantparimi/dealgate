"""Cognito JWT verification.

Environment variables (all required outside `DEALGATE_ENV=local`):

- ``COGNITO_USER_POOL_ID`` — e.g. ``us-east-1_abc123``.
- ``COGNITO_CLIENT_ID``   — the app-client id issuing tokens the API accepts.
- ``COGNITO_REGION``      — falls back to ``AWS_REGION`` when unset.

The verifier fetches the pool JWKS on first use, caches it in-process for 24h,
and validates signature, expiry, issuer and audience/client on every call.
Both ID tokens (``token_use=id`` + ``aud``) and access tokens
(``token_use=access`` + ``client_id``) are accepted; a mismatch on
``token_use`` is a hard 401.

Missing config raises :class:`CognitoConfigError` on first use, never at
import — the same image ships to local, staging and prod.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

_JWKS_TTL_SECONDS = 24 * 60 * 60


class CognitoConfigError(RuntimeError):
    """Raised when required Cognito env vars are missing at first verify()."""


class CognitoAuthError(RuntimeError):
    """Raised on any token validation failure. Callers translate to 401."""


@dataclass(frozen=True)
class _CognitoSettings:
    user_pool_id: str
    client_id: str
    region: str

    @property
    def issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"


def _load_settings() -> _CognitoSettings:
    pool = os.environ.get("COGNITO_USER_POOL_ID")
    client = os.environ.get("COGNITO_CLIENT_ID")
    region = os.environ.get("COGNITO_REGION") or os.environ.get("AWS_REGION")
    missing = [
        name
        for name, value in (
            ("COGNITO_USER_POOL_ID", pool),
            ("COGNITO_CLIENT_ID", client),
            ("COGNITO_REGION/AWS_REGION", region),
        )
        if not value
    ]
    if missing:
        raise CognitoConfigError(
            f"Cognito config missing: {', '.join(missing)}. "
            "Set these env vars or run with DEALGATE_ENV=local."
        )
    # After the missing check, mypy/type-checkers still see Optional[str];
    # narrow via assertions.
    assert pool and client and region
    return _CognitoSettings(user_pool_id=pool, client_id=client, region=region)


class _JWKSCache:
    """Thread-safe TTL cache for a single pool's JWKS.

    Uses :class:`jwt.PyJWKClient` under the hood, but wraps it so we can refresh
    on TTL and swap the HTTP fetcher out in tests.
    """

    def __init__(self, ttl_seconds: int = _JWKS_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._client: PyJWKClient | None = None
        self._url: str | None = None
        self._fetched_at: float = 0.0

    def get(self, url: str) -> PyJWKClient:
        now = time.monotonic()
        with self._lock:
            fresh = (
                self._client is not None
                and self._url == url
                and (now - self._fetched_at) < self._ttl
            )
            if not fresh:
                self._client = PyJWKClient(url, cache_keys=True)
                self._url = url
                self._fetched_at = now
            assert self._client is not None
            return self._client

    def clear(self) -> None:
        with self._lock:
            self._client = None
            self._url = None
            self._fetched_at = 0.0


_jwks_cache = _JWKSCache()


def _get_signing_key(token: str, jwks_url: str) -> Any:
    client = _jwks_cache.get(jwks_url)
    try:
        return client.get_signing_key_from_jwt(token).key
    except (PyJWTError, httpx.HTTPError, ValueError) as exc:
        raise CognitoAuthError(f"jwks lookup failed: {exc}") from exc


def verify_cognito_jwt(token: str) -> dict[str, Any]:
    """Verify a Cognito JWT and return its claims.

    Raises :class:`CognitoAuthError` on any validation failure.
    Raises :class:`CognitoConfigError` if env vars are missing.
    """

    if not token:
        raise CognitoAuthError("empty token")

    settings = _load_settings()
    signing_key = _get_signing_key(token, settings.jwks_url)

    try:
        unverified = jwt.get_unverified_header(token)
    except PyJWTError as exc:
        raise CognitoAuthError(f"malformed token header: {exc}") from exc
    alg = unverified.get("alg") or "RS256"
    if alg not in {"RS256", "RS384", "RS512"}:
        raise CognitoAuthError(f"unsupported alg: {alg}")

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[alg],
            issuer=settings.issuer,
            # `aud` is validated below per token_use (id tokens use aud;
            # access tokens use client_id). PyJWT's default aud validation
            # requires an `audience=` parameter and raises "Invalid audience"
            # when it isn't supplied even though the check we want happens
            # below; turn its check off so ours is the only one.
            options={
                "require": ["exp", "iss", "sub", "token_use"],
                "verify_aud": False,
            },
        )
    except PyJWTError as exc:
        raise CognitoAuthError(f"token invalid: {exc}") from exc

    token_use = claims.get("token_use")
    if token_use == "id":
        aud = claims.get("aud")
        aud_list = aud if isinstance(aud, list) else [aud]
        if settings.client_id not in aud_list:
            raise CognitoAuthError("id token aud does not match client_id")
    elif token_use == "access":
        if claims.get("client_id") != settings.client_id:
            raise CognitoAuthError("access token client_id mismatch")
    else:
        raise CognitoAuthError(f"unexpected token_use: {token_use!r}")

    return claims


__all__ = [
    "CognitoAuthError",
    "CognitoConfigError",
    "verify_cognito_jwt",
]
