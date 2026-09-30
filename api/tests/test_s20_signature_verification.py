"""T22 + T41 · signature: unsigned upload, executed vs approved, decline/expire, retry (S20 · W5).

Per review:
> Test unsigned upload, executed document with changed terms,
> declined/expired request and retry. No false execution or duplicate
> external send.
>
> With all other signature prerequisites met, test the exact approved
> on-file rule across client, workspace, signature UI and server. No
> conflicting note-only versus blocking state (T41).

**Skeleton, xfail until W7 lands the signature service.**

Test cases:
  1. Uploading an unsigned document does NOT flip the package to
     `executed`. The state stays `awaiting_signature` (or similar).
  2. Uploading an executed document whose terms diverge from approved
     terms is REJECTED with reason "executed_terms_diverge"; audit
     event names the divergent fields.
  3. Signature request declined → state `declined`; can be re-sent
     only after material rework (T21 linkage).
  4. Signature request expired → state `expired`; retry creates a
     new envelope but does NOT resend the previous one (no duplicate
     external send).
  5. NDA/MSA on-file rule per D3 is applied consistently across
     client detail, workspace, signature UI and server (T41 linkage).
     If NDA/MSA is not a code-level blocker, the signature UI does
     NOT list it as a hold reason.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W7 signature service", strict=False)
@pytest.mark.asyncio
async def test_unsigned_upload_does_not_execute(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 executed-vs-approved diff")
@pytest.mark.asyncio
async def test_executed_document_diverging_terms_rejected(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 decline path")
@pytest.mark.asyncio
async def test_declined_signature_requires_rework(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 expire + retry path")
@pytest.mark.asyncio
async def test_expired_signature_retry_no_duplicate_send(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 + W7 NDA/MSA rule alignment (D3, T41)")
@pytest.mark.asyncio
async def test_nda_msa_rule_consistent_across_surfaces(session):
    raise AssertionError("skeleton")
