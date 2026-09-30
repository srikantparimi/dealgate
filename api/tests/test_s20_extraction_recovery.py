"""T12 · SOW extraction recovery (S20 · W5).

Per review:
> Test extraction failure, ambiguous fields, duplicate file, saved
> draft, reload and resume. Preserve original file and entered
> corrections.

**Skeleton — asserts on `app.services.sow_upload_pipeline` behavior.**

Test cases:
  1. Extraction failure preserves the original file in S3; a retry
     picks up from the persisted file (no re-upload needed).
  2. Ambiguous fields (e.g. two possible amount candidates) surface as
     `needs_confirmation` with candidate values, not zero.
  3. Duplicate file upload (same content hash) is detected and offers
     "link to existing package" instead of creating a duplicate.
  4. Saved draft persists entered corrections; reload restores every
     field the user typed.
  5. Extraction is a job with polling; a schema-valid AI result is
     still a draft requiring human confirmation (A7, CLAUDE.md rule 6).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="skeleton", strict=False)
@pytest.mark.asyncio
async def test_extraction_failure_preserves_file(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_ambiguous_fields_are_needs_confirmation(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_duplicate_upload_offers_link(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton")
@pytest.mark.asyncio
async def test_saved_draft_restores_corrections(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; A7 lifecycle boundary")
@pytest.mark.asyncio
async def test_ai_result_is_a_draft_needing_confirmation(session):
    raise AssertionError("skeleton")
