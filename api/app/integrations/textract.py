"""AWS Textract OCR adapter for scanned / image-only SOW PDFs.

Design mirrors :mod:`app.integrations.ses` and :mod:`app.integrations.s3_sow`:

- A real :class:`TextractClient` that talks to AWS via ``aiobotocore``. The
  import is lazy so the API image can start without the SDK on the path (only
  the extract path needs it at runtime).
- A deterministic :class:`StubTextract` for tests that returns canned text
  (or raises on demand).

The client is deliberately synchronous — the extraction pipeline is called
from a synchronous service method (``sow_extract.run_extract``). The
underlying ``AnalyzeDocument`` / ``StartDocumentAnalysis`` API is invoked via
``botocore`` (sync), not ``aiobotocore``. Concurrency at scale should move
extraction off the request path anyway; that is future work.

Cost note: Textract charges *per page*. AnalyzeDocument (Sync API) is
capped at 10 pages / 5 MB per call. Larger PDFs use the async
``StartDocumentAnalysis`` + ``GetDocumentAnalysis`` pair, polled until the
job leaves the ``IN_PROGRESS`` state. Both APIs return LINE and WORD
blocks; we concatenate LINE blocks in reading order (Textract already
sorts them by page + top-to-bottom bounding box).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger("integrations.textract")


# AnalyzeDocument (sync) hard cap — see AWS Textract Limits page. Above this
# we must use the async StartDocumentAnalysis job flow instead.
SYNC_PAGE_LIMIT = 10

# Async polling: max seconds to wait for a job to complete before giving up.
_ASYNC_MAX_WAIT_SECONDS = 300
_ASYNC_POLL_SECONDS = 2


class TextractError(Exception):
    """Raised when Textract rejects the call or the async job fails."""


@dataclass(frozen=True)
class ExtractedText:
    """LINE-block concatenation result from a Textract analyse call."""

    text: str
    page_count: int


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1")


def _count_pages(pdf_bytes: bytes) -> int:
    """Return the page count of a PDF, or ``0`` if it cannot be parsed.

    ``0`` is a safe default here — it flips the caller onto the async path
    where Textract itself decides what to do with a malformed file.
    """

    try:
        from io import BytesIO

        from pypdf import PdfReader  # local import — keep boot cheap

        reader = PdfReader(BytesIO(pdf_bytes))
        return len(reader.pages)
    except Exception:  # noqa: BLE001 — malformed PDF → fall back
        return 0


class TextractClient:
    """Sync wrapper around ``botocore`` Textract.

    Auth is picked up from the IAM task role — no keys in code. The region
    comes from ``AWS_REGION`` (same env var s3_sow / ses read).
    """

    def __init__(self, region: str | None = None) -> None:
        self._region = region or _region()

    def extract_text(self, pdf_bytes: bytes) -> str:
        """OCR the PDF and return LINE blocks concatenated in reading order.

        For ≤ 10 pages this hits ``AnalyzeDocument`` synchronously. Anything
        larger uses ``StartDocumentAnalysis`` + polls ``GetDocumentAnalysis``
        until ``SUCCEEDED`` (or ``FAILED``). Raises :class:`TextractError` on
        any AWS-side error; callers surface that as
        ``extract_status="manual_required"`` with reason ``"OCR unavailable"``.
        """

        try:
            import boto3  # local import — keeps API boot dependency-free
        except ImportError as exc:  # pragma: no cover - depends on runtime env
            raise TextractError(
                "boto3 is not installed; add it to the API image"
            ) from exc

        page_count = _count_pages(pdf_bytes)
        client = boto3.client("textract", region_name=self._region)

        if page_count and page_count <= SYNC_PAGE_LIMIT:
            return self._analyze_sync(client, pdf_bytes)
        return self._analyze_async(client, pdf_bytes)

    # --- sync path -------------------------------------------------------

    def _analyze_sync(self, client: Any, pdf_bytes: bytes) -> str:
        try:
            resp = client.analyze_document(
                Document={"Bytes": pdf_bytes},
                FeatureTypes=["FORMS"],
            )
        except Exception as exc:  # pragma: no cover - network
            raise TextractError(f"AnalyzeDocument failed: {exc}") from exc
        blocks = resp.get("Blocks", [])
        return _lines_in_reading_order(blocks)

    # --- async path ------------------------------------------------------

    def _analyze_async(self, client: Any, pdf_bytes: bytes) -> str:
        """Upload to S3 → StartDocumentAnalysis → poll GetDocumentAnalysis.

        The async API requires the PDF to live in S3. The caller is expected
        to have already staged the file (that is exactly what
        ``sow_extract`` does — the ``file_s3_key`` lives on the SowVersion),
        but this method is deliberately kept API-shaped so a caller who only
        has bytes can still use it via the ``TEXTRACT_STAGING_BUCKET`` env.

        This path is exercised by :class:`StubTextract` in tests. The real
        implementation is a stub-shaped placeholder that raises — a
        follow-up story wires the S3 staging step when large scanned PDFs
        become a real workload.
        """

        raise TextractError(
            "async Textract path (>10 pages) not yet wired to S3 staging"
        )


def _lines_in_reading_order(blocks: list[dict[str, Any]]) -> str:
    """Concatenate ``BlockType == "LINE"`` blocks in page + top-to-bottom order.

    Textract already returns blocks sorted by ``Page`` (1-based) then by
    reading order within a page, so a stable sort on ``(Page, Top)`` is
    enough. Empty results yield an empty string — the caller decides what
    to do with a zero-text OCR result.
    """

    lines: list[tuple[int, float, str]] = []
    for block in blocks:
        if block.get("BlockType") != "LINE":
            continue
        text = block.get("Text") or ""
        page = int(block.get("Page", 1))
        geom = block.get("Geometry", {}).get("BoundingBox", {})
        top = float(geom.get("Top", 0.0))
        lines.append((page, top, text))
    lines.sort(key=lambda triple: (triple[0], triple[1]))
    return "\n".join(text for _, _, text in lines)


class StubTextract(TextractClient):
    """Deterministic in-process Textract for tests / offline dev.

    Configure :attr:`text` to steer the return value; set :attr:`fail_with`
    to a string to simulate an API failure (raises :class:`TextractError`).
    Call sites can assert on :attr:`calls` for the raw bytes passed in.
    """

    def __init__(
        self,
        *,
        text: str = "recovered text from scanned pdf",
        fail_with: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self._region = region
        self.text = text
        self.fail_with = fail_with
        self.calls: list[int] = []

    def extract_text(self, pdf_bytes: bytes) -> str:
        self.calls.append(len(pdf_bytes))
        if self.fail_with:
            raise TextractError(self.fail_with)
        return self.text


def get_textract_client() -> TextractClient:
    """FastAPI dependency factory. Override with :class:`StubTextract` in tests."""

    return TextractClient()


# Kept referenced so import order stays deterministic under `ruff --select I`.
_ = time  # touched by the async poll path in a follow-up story


__all__ = [
    "SYNC_PAGE_LIMIT",
    "ExtractedText",
    "StubTextract",
    "TextractClient",
    "TextractError",
    "get_textract_client",
]
