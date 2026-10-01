"""T37 · upload/extraction interrupt recovery (S20 · W5).

Per review:
> Interrupt upload/extraction and restart workers; recover without
> duplicate SOWs or approved-version mutation. Direct-deal binding
> survives every step.

Per A7:
> Extraction lifecycle boundaries: for lengthy work persist job state
> and provide polling/status recovery. A schema-valid AI result is still
> a draft requiring human confirmation. Preserve immutable SOW/GM/decision
> evidence.

**Skeleton — asserts against SowUploadJob state machine.**

Test cases:
  1. Interrupt mid-upload: on restart the client resumes at the last
     completed part; no partial file appears in S3.
  2. Interrupt mid-extraction: the job status persists (`extracting`,
     `awaiting_confirmation`, `failed`); a re-run of the same job id
     is idempotent.
  3. After successful upload, re-uploading the SAME file with the
     SAME (deal_id, content_hash) offers "link to existing" instead
     of creating a duplicate SOW.
  4. Approved-version mutation: even a full worker restart between
     approval and signature does NOT change the approved package's
     bytes; the record is immutable (rule 4).
  5. Direct-deal binding survives every step: dealId in the URL
     carries through upload → extraction → confirm → package_create.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="skeleton", strict=False)
@pytest.mark.asyncio
async def test_upload_resumes_at_last_completed_part(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_extraction_job_is_idempotent(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_duplicate_upload_offers_link_not_create(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_approved_version_immutable_across_restart(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_deal_binding_survives_every_step(session):
    raise AssertionError("skeleton")
