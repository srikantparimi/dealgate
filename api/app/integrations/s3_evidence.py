"""Evidence file uploads for the agreements bucket.

Signed PDF/DOCX evidence is stored by the extraction service and filed only
after Legal confirms the extracted draft. Uploads and downloads use the AWS
default credential chain, including the ECS task role.

Sprint 2 uses versioning + SSE-AES256 on the bucket. Object Lock lands in
a later sprint (build-guide §12).

The legacy presigned PUT interface remains for API compatibility. For local
tests, `StubS3` stores bytes in memory and returns synthetic URLs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import structlog

log = structlog.get_logger("s3_evidence")


# Content types the pre-signed PUT will accept. Anything outside this list is
# rejected at request time; S3 further enforces it via the signed header.
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

# 5 minutes: long enough for a browser upload of a small PDF, short enough
# that a leaked URL is not a lasting exposure. Blueprint §12.
_URL_TTL_SECONDS = 300

# Extension inferred from the content type; keeps the s3 key human-scannable.
_EXT_FOR_CT: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


class UnsupportedContentType(Exception):
    """Raised when the caller requests a URL for a non-PDF/DOCX file."""


@dataclass(frozen=True)
class UploadUrl:
    url: str
    s3_key: str
    method: str = "PUT"
    expires_in: int = _URL_TTL_SECONDS
    required_headers: dict[str, str] | None = None


def _bucket_name() -> str:
    """Read the bucket name from env; the default matches infra-tf.

    In staging / prod the API task's env carries the concrete bucket name
    injected by CDK / Terraform (`AGREEMENTS_BUCKET`). The default here is
    only meant for dev boxes where the developer has run `terraform apply`.
    """

    explicit = os.environ.get("AGREEMENTS_BUCKET")
    if explicit:
        return explicit
    account_id = os.environ.get("AWS_ACCOUNT_ID", "000000000000")
    return f"officeapp-dev-agreements-{account_id}"


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1")


def _now() -> datetime:
    return datetime.now(UTC)


def _build_s3_key(agreement_id: uuid.UUID, filename: str, content_type: str) -> str:
    # Keep the object under a per-agreement prefix so bucket-level lifecycle
    # rules can act on all versions of one agreement at once.
    ext = _EXT_FOR_CT.get(content_type, "bin")
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    safe_name = "".join(c if c.isalnum() or c in "-._" else "_" for c in filename)
    # 8 bytes of randomness prevents accidental overwrite on the same second.
    nonce = uuid.uuid4().hex[:8]
    return f"agreements/{agreement_id}/{stamp}-{nonce}-{safe_name}.{ext}"


# --- SigV4 URL signing ----------------------------------------------------


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
    """Return a pre-signed virtual-hosted-style S3 URL.

    `signed_headers` are the ones the client MUST send with the request; they
    are baked into the signature. For a PUT we sign `host` + `content-type`
    so S3 rejects uploads with a mismatching MIME.
    """

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

    # Canonical headers block: name:value, one per line, sorted.
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
    """Read credentials from env. Falls back to bogus values so the URL still
    parses on a dev laptop without AWS access; StubS3 is what tests use."""

    access = os.environ.get("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "SECRETEXAMPLE")
    token = os.environ.get("AWS_SESSION_TOKEN")
    return access, secret, token


# --- Public interface ----------------------------------------------------


class EvidenceS3:
    """Real S3 client. Instantiate once per process; methods are stateless."""

    def __init__(self, bucket: str | None = None, region: str | None = None) -> None:
        self._bucket = bucket or _bucket_name()
        self._region = region or _region()

    def generate_upload_url(
        self,
        agreement_id: uuid.UUID,
        filename: str,
        content_type: str,
    ) -> UploadUrl:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType(
                f"content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}"
            )
        key = _build_s3_key(agreement_id, filename, content_type)
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
        from app.integrations.s3_sow import _client

        return _client().generate_presigned_url("get_object",
            Params={"Bucket": self._bucket, "Key": s3_key}, ExpiresIn=_URL_TTL_SECONDS)

    def put_object(self, agreement_id: uuid.UUID, filename: str, content_type: str, body: bytes) -> str:
        from app.integrations.s3_sow import _client

        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType("Only PDF and DOCX files are accepted")
        key = _build_s3_key(agreement_id, filename, content_type)
        _client().put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type)
        return key


class StubS3(EvidenceS3):
    """Deterministic in-process client for tests / offline dev.

    Every generated URL is safe to hand to a test client — the URL is a
    fake `https://stub-agreements.local/...` string that never hits AWS.
    """

    def __init__(self, bucket: str = "stub-agreements") -> None:
        # Skip the parent __init__ so no env vars are required.
        self._bucket = bucket
        self._region = "us-east-1"
        # Record every call so tests can assert on ordering / arguments.
        self.upload_calls: list[tuple[uuid.UUID, str, str]] = []
        self.download_calls: list[str] = []
        self.objects: dict[str, bytes] = {}

    def put_object(self, agreement_id: uuid.UUID, filename: str, content_type: str, body: bytes) -> str:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType("Only PDF and DOCX files are accepted")
        key = _build_s3_key(agreement_id, filename, content_type)
        self.objects[key] = body
        return key

    def generate_upload_url(
        self,
        agreement_id: uuid.UUID,
        filename: str,
        content_type: str,
    ) -> UploadUrl:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType(
                f"content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}"
            )
        self.upload_calls.append((agreement_id, filename, content_type))
        key = _build_s3_key(agreement_id, filename, content_type)
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


def get_evidence_s3() -> EvidenceS3:
    """FastAPI dependency. Override with :class:`StubS3` in tests."""

    return EvidenceS3()


__all__ = [
    "EvidenceS3",
    "StubS3",
    "UnsupportedContentType",
    "UploadUrl",
    "get_evidence_s3",
]


_ = timedelta  # kept for future TTL-per-role tuning; silences lint.
