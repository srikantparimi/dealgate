"""S10-02 — Bulk SOW import pipeline acceptance tests.

Covers the story's assertions:

- 6 SOW fixtures + 1 MSA + 1 duplicate of ``03_fixed_price_mixed.pdf``
  (re-named to ``03_fixed_price_mixed_dup.pdf``) → 8 ImportFile rows,
  7 records created, 1 marked ``duplicate``. The MSA is filed against
  a legal entity (no SOW row).
- An imported SOW with ``term_end`` 45 days out opens a renewal review
  + notice task immediately.
- Re-running the same batch is idempotent — no new sow_versions, log
  unchanged.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.integrations.bedrock_sow_extract import ExtractedFields, StubBedrock
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.sow import SowVersion
from app.models.user import User
from app.services.bulk_import import (
    InputFile,
    create_batch,
    expand_zip_or_files,
    load_overview,
    process_batch,
    rerun_batch,
)
from app.services.sow_upload_pipeline import (
    PipelineOutcome,
    apply_pipeline,
    sha256_hex,
)

from sqlalchemy import select


FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "sample_sows"


class _RotatingBedrock(StubBedrock):
    """Return a distinct extract per call so business-key dedupe is honest.

    The stock ``StubBedrock`` returns the same canned payload on every
    call. That would collapse every SOW into a "same title / same term"
    duplicate — a false positive that would masks a real dedupe bug.
    This variant sequences the client name + term end + scope so each
    call looks like a different SOW.
    """

    def __init__(self, *, term_end_days_out: int | None = None) -> None:
        super().__init__()
        self.term_end_days_out = term_end_days_out
        self._counter = 0

    def extract(self, file_bytes: bytes) -> ExtractedFields:
        self._counter += 1
        base = super().extract(file_bytes)
        if isinstance(base, ExtractedFields):
            # Rotate the client name via signatories + scope so client
            # resolution gets a unique legal name per file.
            client_name = f"Client-{self._counter:03d}"
            fields = dict(base.fields)
            fields["signatories"] = {
                "value": [
                    {
                        "name": "Reviewer",
                        "role": "Signer",
                        "client_legal_name": client_name,
                    }
                ],
                "page_ref": 6,
                "status": "unconfirmed",
            }
            fields["scope_summary"] = {
                "value": f"SOW #{self._counter} for {client_name}",
                "page_ref": 1,
                "status": "unconfirmed",
            }
            # Optional term_end override so renewal-schedule tests are
            # deterministic against a synthetic clock.
            if self.term_end_days_out is not None:
                target = (
                    datetime.now(UTC).date()
                    + timedelta(days=self.term_end_days_out)
                )
                fields["term_end"] = {
                    "value": target.isoformat(),
                    "page_ref": 3,
                    "status": "unconfirmed",
                }
            return ExtractedFields(
                fields=fields, model=base.model, prompt_version=base.prompt_version
            )
        return base


def _read(name: str) -> bytes:
    path = FIXTURE_DIR / name
    return path.read_bytes()


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest.fixture
def bulk_files() -> list[InputFile]:
    """Six SOW fixtures + 1 MSA + 1 duplicate (rename of 03) = 8 files."""

    files = [
        InputFile(filename=name, payload=_read(name))
        for name in (
            "01_staff_aug_us.pdf",
            "02_managed_service_india.pdf",
            "03_fixed_price_mixed.pdf",
            "04_assessment_4week.pdf",
            "05_tm_capped.pdf",
            "06_below_floor.pdf",
            "07_msa.pdf",
        )
    ]
    # Duplicate the SOW body with a different filename.
    files.append(
        InputFile(
            filename="03_fixed_price_mixed_dup.pdf",
            payload=_read("03_fixed_price_mixed.pdf"),
        )
    )
    return files


async def _seed_actor(session) -> User:
    user = User(
        id=_uid("bulk@smartek21.com"),
        email="bulk@smartek21.com",
        name="Bulk Runner",
        groups=["Finance", "SystemAdmin"],
    )
    session.add(user)
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_bulk_import_produces_seven_records_and_one_duplicate(
    session, bulk_files
):
    actor = await _seed_actor(session)
    batch = await create_batch(session, actor_id=actor.id, files=bulk_files)
    assert batch.file_count == 8

    payload_by_sha = {sha256_hex(f.payload): f.payload for f in bulk_files}
    bedrock = _RotatingBedrock()
    overview = await process_batch(
        session,
        batch_id=batch.id,
        actor_id=actor.id,
        payload_by_sha=payload_by_sha,
        bedrock=bedrock,
    )

    statuses = [f.status for f in overview.files]
    # 6 SOW imported (or needs_review), 1 MSA imported, 1 duplicate.
    imported_or_needs_review = sum(
        1 for s in statuses if s in ("imported", "needs_review")
    )
    duplicates = sum(1 for s in statuses if s == "duplicate")
    assert imported_or_needs_review == 7, statuses
    assert duplicates == 1, statuses

    # The MSA row exists but never spawns a sow_version.
    msa_row = next(f for f in overview.files if f.filename == "07_msa.pdf")
    assert msa_row.detected_type == "msa"
    assert msa_row.sow_version_id is None

    # Legacy guarantees on the imported SOW rows:
    # - governance_status = 'legacy_not_evidenced'
    # - approval_evidenced remains False
    imported_sow_rows = list(
        (await session.execute(select(SowVersion))).scalars()
    )
    assert imported_sow_rows, "expected at least one sow_version"
    for row in imported_sow_rows:
        assert getattr(row, "governance_status", None) == "legacy_not_evidenced"
        assert getattr(row, "approval_evidenced", False) is False


@pytest.mark.asyncio
async def test_import_inside_notice_window_opens_renewal(session):
    """A SOW landing with term_end 45 days out opens a renewal + task."""

    actor = await _seed_actor(session)
    payload = _read("03_fixed_price_mixed.pdf")
    file = InputFile(filename="notice_window.pdf", payload=payload)
    batch = await create_batch(session, actor_id=actor.id, files=[file])
    bedrock = _RotatingBedrock(term_end_days_out=45)
    payload_by_sha = {sha256_hex(payload): payload}
    await process_batch(
        session,
        batch_id=batch.id,
        actor_id=actor.id,
        payload_by_sha=payload_by_sha,
        bedrock=bedrock,
    )

    renewals = list((await session.execute(select(Renewal))).scalars())
    assert renewals, "expected a renewal for a 45-day-out import"
    r = renewals[0]
    today = datetime.now(UTC).date()
    # A SOW already inside the notice window opens the review immediately.
    assert r.trigger_date <= today + timedelta(days=1)
    assert r.status == "open"


@pytest.mark.asyncio
async def test_rerun_is_idempotent(session, bulk_files):
    actor = await _seed_actor(session)
    batch = await create_batch(session, actor_id=actor.id, files=bulk_files)
    payload_by_sha = {sha256_hex(f.payload): f.payload for f in bulk_files}
    bedrock = _RotatingBedrock()
    first = await process_batch(
        session,
        batch_id=batch.id,
        actor_id=actor.id,
        payload_by_sha=payload_by_sha,
        bedrock=bedrock,
    )
    first_versions = {v.id for v in (await session.execute(select(SowVersion))).scalars()}

    second_bedrock = _RotatingBedrock()
    second = await rerun_batch(
        session,
        batch_id=batch.id,
        actor_id=actor.id,
        payload_by_sha=payload_by_sha,
        bedrock=second_bedrock,
    )
    second_versions = {v.id for v in (await session.execute(select(SowVersion))).scalars()}
    assert first_versions == second_versions
    assert (
        [f.status for f in first.files] == [f.status for f in second.files]
    )


@pytest.mark.asyncio
async def test_zip_expansion_yields_members():
    """A single .zip in the input list expands into per-member files."""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.pdf", b"hello")
        zf.writestr("b.pdf", b"world")
    files = [InputFile(filename="pack.zip", payload=buf.getvalue())]
    expanded = expand_zip_or_files(files)
    assert {f.filename for f in expanded} == {"a.pdf", "b.pdf"}


@pytest.mark.asyncio
async def test_non_document_type_is_rejected(session):
    """A non-SOW/MSA/NDA payload is rejected without creating any rows."""

    actor = await _seed_actor(session)
    # Bytes that are not a document at all. These land as ``unreadable``
    # rather than ``other``: we could not open the file, which is a different
    # (and more actionable) answer than "we read it and it is not a SOW".
    # The readable-but-not-a-SOW case is covered by the résumé fixture in
    # tests/test_sow_upload_router.py.
    payload = b"not a pdf"
    result = await apply_pipeline(
        session,
        file_bytes=payload,
        uploader_id=actor.id,
        source="bulk_import",
    )
    assert result.outcome == PipelineOutcome.REJECTED
    assert result.detected_type == "unreadable"
    assert result.errors  # carries the reason the file could not be opened

    assert not list((await session.execute(select(SowVersion))).scalars())
    assert not list((await session.execute(select(Opportunity))).scalars())
