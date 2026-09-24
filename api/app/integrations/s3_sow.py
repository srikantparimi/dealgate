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

import os
from typing import Any
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

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


# --- AWS client ----------------------------------------------------------
#
# The hand-rolled SigV4 signer that used to live here is gone, along with
# `_aws_credentials()`, which read AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# from the environment and fell back to the literals "AKIAEXAMPLE" /
# "SECRETEXAMPLE". ECS Fargate task roles do not set those variables — they
# publish credentials on the container credentials endpoint — so in the
# deployed container every signature was built from the placeholder key. That
# turns "no credentials" into "signature mismatch", which is a strictly worse
# error to debug. boto3's default provider chain handles the task role, a
# local profile and CI env vars without a branch.


def _client() -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        region_name=_region(),
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


# --- Public interface ---------------------------------------------------


class SowS3:
    """Real S3 client. Instantiate once per process; methods are stateless."""

    def __init__(self, bucket: str | None = None, region: str | None = None) -> None:
        self._bucket = bucket or _bucket_name()
        self._region = region or _region()
        if self._bucket.endswith("-000000000000"):
            # `_bucket_name()` fell through to its placeholder account id,
            # which means neither SOW_BUCKET nor AWS_ACCOUNT_ID is set. Fail
            # here with the reason rather than 404-ing against a bucket that
            # was never going to exist.
            raise RuntimeError(
                "SOW_BUCKET is not set and AWS_ACCOUNT_ID is unavailable — "
                "cannot resolve the SOW bucket name"
            )

    def put_object(self, s3_key: str, body: bytes, content_type: str) -> str:
        """Upload bytes directly and return the key.

        Server-side uploads do not need a pre-signed URL: presigning exists so
        a *third party* (the browser) can upload without our credentials. Here
        the API already holds the bytes, so signing a URL and then PUTting to
        it from the same process is a pointless network round-trip and a
        second signing implementation to keep correct.

        Synchronous — callers on the event loop wrap this in a thread.
        """

        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType(
                f"content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}"
            )
        if len(body) > MAX_SOW_BYTES:
            raise FileTooLarge(f"file exceeds {MAX_SOW_BYTES} bytes")
        self._client_or_new().put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=body,
            ContentType=content_type,
        )
        return s3_key

    def delete_object(self, s3_key: str) -> None:
        """Remove a stored object.

        Only ever called after the database transaction that removed the
        row has committed. S3 is not transactional with the database, so an
        orphaned object is a janitorial problem while a rolled-back delete
        with a missing file would be a correctness one.
        """

        self._client_or_new().delete_object(Bucket=self._bucket, Key=s3_key)

    def build_key(
        self,
        filename: str,
        content_type: str,
        opportunity_id: uuid.UUID | None = None,
    ) -> str:
        """Key for a file that may not have an opportunity yet.

        The SOW-first flow uploads before the opportunity exists, so the key
        is namespaced by a fresh uuid in that case.
        """

        return _build_s3_key(opportunity_id or uuid.uuid4(), filename, content_type)

    def _client_or_new(self) -> Any:
        return _client()

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
        url = self._client_or_new().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=_URL_TTL_SECONDS,
        )
        return UploadUrl(
            url=url,
            s3_key=key,
            method="PUT",
            expires_in=_URL_TTL_SECONDS,
            required_headers={"Content-Type": content_type},
        )

    def generate_download_url(self, s3_key: str) -> str:
        return self._client_or_new().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": s3_key},
            ExpiresIn=_URL_TTL_SECONDS,
        )

    def download_bytes(self, s3_key: str) -> bytes:
        """Read the object's bytes directly. Used by the S15 re-extract endpoint
        so the API can rerun Bedrock on an existing SOW without asking the
        browser to re-upload."""

        resp = self._client_or_new().get_object(Bucket=self._bucket, Key=s3_key)
        return resp["Body"].read()


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
        self.put_calls: list[tuple[str, int, str]] = []
        self.deleted_keys: list[str] = []

    def delete_object(self, s3_key: str) -> None:
        self.deleted_keys.append(s3_key)

    def put_object(self, s3_key: str, body: bytes, content_type: str) -> str:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentType(
                f"content_type must be one of {sorted(_ALLOWED_CONTENT_TYPES)}"
            )
        if len(body) > MAX_SOW_BYTES:
            raise FileTooLarge(f"file exceeds {MAX_SOW_BYTES} bytes")
        self.put_calls.append((s3_key, len(body), content_type))
        return s3_key

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

    def download_bytes(self, s3_key: str) -> bytes:
        self.download_calls.append(s3_key)
        # Empty bytes exercise the extractor's "no readable text" branch,
        # which is what tests want from an offline fake anyway.
        return b""


def get_sow_s3() -> SowS3:
    """FastAPI dependency. Override with :class:`StubS3` in tests.

    ``S3_STUB=1`` selects the stub. That variable was already exported by
    ``.github/workflows/e2e.yml`` but read by nothing, so the e2e job believed
    it was running offline while the code reached for real S3.
    """

    if os.environ.get("S3_STUB") == "1":
        return StubS3()
    if os.environ.get("DEALGATE_ENV") in ("local", "test"):
        return StubS3()
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
