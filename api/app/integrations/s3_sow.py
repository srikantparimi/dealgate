"""SOW file uploads for the ``officeapp-*-sows-{account_id}`` bucket.

Modelled on :mod:`app.integrations.s3_evidence` so the URL wire format is
identical and the same SigV4 signing helpers apply. The differences:

- default bucket name (``SOW_BUCKET`` env → ``officeapp-dev-sows-{account_id}``);
- key prefix is ``sow/{opportunity_id}/...``;
- otherwise identical (PDF/DOCX only, 5-minute pre-signed PUT/GET).

The story enforces a 25 MB upload cap. S3 pre-signed URLs cannot enforce a
byte cap directly without a POST policy; we therefore enforce the cap at
`POST /versions` time via the client-provided ``file_size`` hint.
:class:`StubS3` mirrors :class:`s3_evidence.StubS3` so tests never hit AWS.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import structlog

log = structlog.get_logger("s3_sow")


_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

_URL_TTL_SECONDS = 300

_EXT_FOR_CT: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

# 25 MB, enforced at the POST /versions endpoint. S3 pre-signed PUTs cannot
# cap payload size by themselves; the client sends a size hint that the API
# validates before issuing the URL.
MAX_SOW_BYTES = 25 * 1024 * 1024


class UnsupportedContentType(Exception):
    """Raised when the caller requests a URL for a non-PDF/DOCX file."""


class FileTooLarge(Exception):
    """Raised when the requested file size exceeds :data:`MAX_SOW_BYTES`."""


@dataclass(frozen=True)
class UploadUrl:
    url: str
    s3_key: str
    method: str = "PUT"
    expires_in: int = _URL_TTL_SECONDS
    required_headers: dict[str, str] | None = None


def _bucket_name() -> str:
    explicit = os.environ.get("SOW_BUCKET")
    if explicit:
        return explicit
    account_id = os.environ.get("AWS_ACCOUNT_ID", "000000000000")
    return f"officeapp-dev-sows-{account_id}"


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1")


def _now() -> datetime:
    return datetime.now(UTC)


def _build_s3_key(opportunity_id: uuid.UUID, filename: str, content_type: str) -> str:
    ext = _EXT_FOR_CT.get(content_type, "bin")
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    safe_name = "".join(c if c.isalnum() or c in "-._" else "_" for c in filename)
    nonce = uuid.uuid4().hex[:8]
    return f"sow/{opportunity_id}/{stamp}-{nonce}-{safe_name}.{ext}"


# --- SigV4 URL signing (mirrors s3_evidence) -----------------------------


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def _presign(
    *,
    method: str,
    bucket: str,
    key: str,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None,
    ttl_seconds: int,
    signed_headers: dict[str, str],
) -> str:
    host = f"{bucket}.s3.{region}.amazonaws.com"
    now = _now()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential = f"{access_key}/{date_stamp}/{region}/s3/aws4_request"

    header_names = sorted({"host", *[h.lower() for h in signed_headers]})
    signed_header_list = ";".join(header_names)

    canonical_query_parts = [
        ("X-Amz-Algorithm", "AWS4-HMAC-SHA256"),
        ("X-Amz-Credential", credential),
        ("X-Amz-Date", amz_date),
        ("X-Amz-Expires", str(ttl_seconds)),
        ("X-Amz-SignedHeaders", signed_header_list),
    ]
    if session_token:
        canonical_query_parts.append(("X-Amz-Security-Token", session_token))
    canonical_query_parts.sort(key=lambda p: p[0])
    canonical_query = "&".join(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}"
        for k, v in canonical_query_parts
    )

    headers_lower = {"host": host, **{k.lower(): v for k, v in signed_headers.items()}}
    canonical_headers = "".join(
        f"{name}:{headers_lower[name].strip()}\n" for name in header_names
    )

    canonical_uri = "/" + quote(key, safe="/-_.~")
    payload_hash = "UNSIGNED-PAYLOAD"
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_header_list,
            payload_hash,
        ]
    )

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

    return (
        f"https://{host}{canonical_uri}?{canonical_query}&X-Amz-Signature={signature}"
    )


def _aws_credentials() -> tuple[str, str, str | None]:
    access = os.environ.get("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "SECRETEXAMPLE")
    token = os.environ.get("AWS_SESSION_TOKEN")
    return access, secret, token


# --- Public interface ---------------------------------------------------


class SowS3:
    """Real S3 client. Instantiate once per process; methods are stateless."""

    def __init__(self, bucket: str | None = None, region: str | None = None) -> None:
        self._bucket = bucket or _bucket_name()
        self._region = region or _region()

    def generate_upload_url(
        self,
        opportunity_id: uuid.UUID,
        filename: str,
        content_type: str,
    ) -> UploadUrl:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType(
                f"content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}"
            )
        key = _build_s3_key(opportunity_id, filename, content_type)
        access, secret, token = _aws_credentials()
        url = _presign(
            method="PUT",
            bucket=self._bucket,
            key=key,
            region=self._region,
            access_key=access,
            secret_key=secret,
            session_token=token,
            ttl_seconds=_URL_TTL_SECONDS,
            signed_headers={"content-type": content_type},
        )
        return UploadUrl(
            url=url,
            s3_key=key,
            method="PUT",
            expires_in=_URL_TTL_SECONDS,
            required_headers={"Content-Type": content_type},
        )

    def generate_download_url(self, s3_key: str) -> str:
        access, secret, token = _aws_credentials()
        return _presign(
            method="GET",
            bucket=self._bucket,
            key=s3_key,
            region=self._region,
            access_key=access,
            secret_key=secret,
            session_token=token,
            ttl_seconds=_URL_TTL_SECONDS,
            signed_headers={},
        )


class StubS3(SowS3):
    """Deterministic in-process client for tests / offline dev.

    Every generated URL is a fake ``https://stub-sows.local/...`` string that
    never hits AWS. Callers can assert on ``upload_calls`` / ``download_calls``.
    """

    def __init__(self, bucket: str = "stub-sows") -> None:
        # Skip parent __init__ so no env vars are required.
        self._bucket = bucket
        self._region = "us-east-1"
        self.upload_calls: list[tuple[uuid.UUID, str, str]] = []
        self.download_calls: list[str] = []

    def generate_upload_url(
        self,
        opportunity_id: uuid.UUID,
        filename: str,
        content_type: str,
    ) -> UploadUrl:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType(
                f"content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}"
            )
        self.upload_calls.append((opportunity_id, filename, content_type))
        key = _build_s3_key(opportunity_id, filename, content_type)
        url = f"https://{self._bucket}.local/put/{key}?stub=1"
        return UploadUrl(
            url=url,
            s3_key=key,
            method="PUT",
            expires_in=_URL_TTL_SECONDS,
            required_headers={"Content-Type": content_type},
        )

    def generate_download_url(self, s3_key: str) -> str:
        self.download_calls.append(s3_key)
        return f"https://{self._bucket}.local/get/{s3_key}?stub=1"


def get_sow_s3() -> SowS3:
    """FastAPI dependency. Override with :class:`StubS3` in tests."""

    return SowS3()


__all__ = [
    "FileTooLarge",
    "MAX_SOW_BYTES",
    "SowS3",
    "StubS3",
    "UnsupportedContentType",
    "UploadUrl",
    "get_sow_s3",
]
