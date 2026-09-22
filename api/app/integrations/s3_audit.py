"""S3 client for the nightly audit-export bucket.

Thin async wrapper around SigV4-signed HEAD / PUT requests, mirroring
Agent K's stdlib-only signing pattern in ``s3_evidence.py``. No boto3 —
this whole module is ~200 LOC and one third-party dep (``httpx``) that
the API already imports for HubSpot.

The API service itself never talks to this bucket; only the
``worker.audit_export`` task does. The stub class is what tests inject.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote

import httpx
import structlog

log = structlog.get_logger("s3_audit")


# The exports are small (a day of audit rows gzipped is tens of KB).
# 30 s covers a slow uplink; the worker will retry on the next run.
_DEFAULT_TIMEOUT = 30.0


def _default_bucket() -> str:
    explicit = os.environ.get("AUDIT_EXPORT_BUCKET")
    if explicit:
        return explicit
    account_id = os.environ.get("AWS_ACCOUNT_ID", "000000000000")
    return f"officeapp-dev-audit-exports-{account_id}"


def _default_region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1")


def _now() -> datetime:
    return datetime.now(UTC)


# --- SigV4 primitives (stdlib) --------------------------------------------


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def _sigv4_headers(
    *,
    method: str,
    bucket: str,
    key: str,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None,
    extra_headers: dict[str, str],
    payload_sha256: str,
) -> tuple[str, dict[str, str]]:
    """Return ``(url, headers)`` for a SigV4-signed S3 request.

    ``payload_sha256`` is the hex sha256 of the request body (or the
    literal ``"UNSIGNED-PAYLOAD"`` for HEAD/GET). The header
    ``x-amz-content-sha256`` is always signed, per the SigV4 spec.
    """

    host = f"{bucket}.s3.{region}.amazonaws.com"
    now = _now()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    canonical_uri = "/" + quote(key, safe="/-_.~")

    headers = {
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_sha256,
    }
    if session_token:
        headers["x-amz-security-token"] = session_token
    for k, v in extra_headers.items():
        headers[k.lower()] = v

    header_names = sorted(headers.keys())
    signed_header_list = ";".join(header_names)
    canonical_headers = "".join(
        f"{name}:{headers[name].strip()}\n" for name in header_names
    )

    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            "",  # no query string on writes/reads by key
            canonical_headers,
            signed_header_list,
            payload_sha256,
        ]
    )

    credential = f"{access_key}/{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            f"{date_stamp}/{region}/s3/aws4_request",
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _signing_key(secret_key, date_stamp, region, "s3")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={credential}, "
        f"SignedHeaders={signed_header_list}, Signature={signature}"
    )
    # httpx wants Title-Case-ish header names; casing does not affect SigV4
    # because the signer canonicalised on lower-case. We return the exact
    # header dict the client should send.
    out = {
        "Host": host,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-SHA256": payload_sha256,
        "Authorization": authorization,
    }
    if session_token:
        out["X-Amz-Security-Token"] = session_token
    for k, v in extra_headers.items():
        out[k] = v
    return f"https://{host}{canonical_uri}", out


def _aws_credentials() -> tuple[str, str, str | None]:
    # Fargate task role credentials are served by the ECS container credentials
    # endpoint (169.254.170.2$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI), not env
    # vars — the placeholder fallback below made every worker task 403 against
    # S3 until this was fixed (S14a.3b). Defer to botocore's credential
    # resolver, which already handles env, container endpoint, IMDS, and
    # config-file chains in the right order.
    access = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    token = os.environ.get("AWS_SESSION_TOKEN")
    if access and secret:
        return access, secret, token

    import boto3

    session = boto3.Session()
    creds = session.get_credentials()
    if creds is None:
        # Preserve the historical placeholder behaviour so unit tests that
        # never enter this branch keep working.
        return "AKIAEXAMPLE", "SECRETEXAMPLE", None
    frozen = creds.get_frozen_credentials()
    return frozen.access_key, frozen.secret_key, frozen.token


# --- Public interface -----------------------------------------------------


@dataclass(frozen=True)
class HeadResult:
    exists: bool
    content_md5: str | None = None  # base64-encoded 128-bit md5 of the object


class AuditExportS3Protocol(Protocol):
    async def head(self, key: str) -> HeadResult: ...

    async def put(
        self,
        key: str,
        *,
        body: bytes,
        content_type: str,
        content_md5: str,
    ) -> None: ...


class AuditExportS3:
    """Real S3 client for the audit-exports bucket.

    Object-Lock retention is configured at the bucket level (Terraform;
    COMPLIANCE mode, 7-year default). PUTs inherit the default retention
    automatically — no per-request ``x-amz-object-lock-*`` headers
    needed.
    """

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._bucket = bucket or _default_bucket()
        self._region = region or _default_region()
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        return self._client

    async def head(self, key: str) -> HeadResult:
        access, secret, token = _aws_credentials()
        url, headers = _sigv4_headers(
            method="HEAD",
            bucket=self._bucket,
            key=key,
            region=self._region,
            access_key=access,
            secret_key=secret,
            session_token=token,
            extra_headers={},
            payload_sha256="UNSIGNED-PAYLOAD",
        )
        client = await self._get_client()
        resp = await client.request("HEAD", url, headers=headers)
        if resp.status_code == 404:
            return HeadResult(exists=False)
        resp.raise_for_status()
        # Prefer the object metadata we set on PUT; fall back to ETag when
        # the object was single-part-uploaded (ETag == md5 in that case).
        md5 = resp.headers.get("x-amz-meta-content-md5")
        if md5 is None:
            etag = resp.headers.get("etag", "").strip('"')
            md5 = etag or None
        return HeadResult(exists=True, content_md5=md5)

    async def put(
        self,
        key: str,
        *,
        body: bytes,
        content_type: str,
        content_md5: str,
    ) -> None:
        access, secret, token = _aws_credentials()
        payload_sha256 = hashlib.sha256(body).hexdigest()
        # ``Content-MD5`` is the base64 md5 (S3 verifies on PUT).
        # ``x-amz-meta-content-md5`` mirrors it so HEAD can compare later
        # (versus the multipart ETag which is not an md5).
        extra = {
            "Content-Type": content_type,
            "Content-MD5": content_md5,
            "x-amz-meta-content-md5": content_md5,
        }
        url, headers = _sigv4_headers(
            method="PUT",
            bucket=self._bucket,
            key=key,
            region=self._region,
            access_key=access,
            secret_key=secret,
            session_token=token,
            extra_headers=extra,
            payload_sha256=payload_sha256,
        )
        client = await self._get_client()
        resp = await client.request("PUT", url, content=body, headers=headers)
        resp.raise_for_status()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


@dataclass
class StubAuditExportS3:
    """In-memory audit-export bucket for tests. No network I/O."""

    bucket: str = "stub-audit-exports"
    region: str = "us-east-1"
    # key -> (body, content_type, content_md5)
    objects: dict[str, tuple[bytes, str, str]] = field(default_factory=dict)
    head_calls: list[str] = field(default_factory=list)
    put_calls: list[str] = field(default_factory=list)
    # Test override: force ``head`` to return this md5 (mismatched HEAD).
    md5_override: dict[str, str] = field(default_factory=dict)

    async def head(self, key: str) -> HeadResult:
        self.head_calls.append(key)
        if key in self.md5_override:
            return HeadResult(exists=True, content_md5=self.md5_override[key])
        stored = self.objects.get(key)
        if stored is None:
            return HeadResult(exists=False)
        return HeadResult(exists=True, content_md5=stored[2])

    async def put(
        self,
        key: str,
        *,
        body: bytes,
        content_type: str,
        content_md5: str,
    ) -> None:
        self.put_calls.append(key)
        self.objects[key] = (body, content_type, content_md5)


def compute_content_md5(body: bytes) -> str:
    """Return the base64-encoded md5 S3 accepts as ``Content-MD5``."""

    return base64.b64encode(hashlib.md5(body).digest()).decode("ascii")


__all__ = [
    "AuditExportS3",
    "AuditExportS3Protocol",
    "HeadResult",
    "StubAuditExportS3",
    "compute_content_md5",
]
