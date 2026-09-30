"""T15 + T41 · NDA/MSA rules per D3 (S20 · W5).

Per D3 (contracts.md §2):
- Two independent facts per client:
  * **on file** = document uploaded (✓/-, file link, uploader, time,
    explicit "on file ≠ signed/verified").
  * **signed/verified** = set only through existing SOW Legal review
    or an explicit verification record.
- Neither is a blocker for review or submission (S17).
- Remove NDA/MSA from Signature hold reasons UNLESS an explicit
  verification requirement exists in code; if it does, record in
  `decisions.md`.

**Skeleton, xfail until W3 (SOW) + W2 (client detail display) land.**

Assertions (skeleton):
  1. Uploading an NDA sets `on_file = True` and `verified = False` by
     default; the checkmark does not imply execution.
  2. A Legal-approved decision that references the NDA sets
     `verified = True`; the same document is now shown as both on-file
     AND verified.
  3. Signature UI does NOT list NDA/MSA as a hold reason for a package
     whose only unmet criterion is verification (D3 says remove).
  4. If a verification requirement lives in code (rule id), the row
     for that requirement lists the SOW Legal decision id, not the
     upload row.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W3 NDA/MSA fact split (D3)", strict=False)
@pytest.mark.asyncio
async def test_upload_sets_on_file_true_verified_false(session):
    """
    Given: client C with no agreements.
    When:  we upload NDA.pdf via `POST /clients/{id}/agreements`.
    Then:  `Agreement.on_file` is True, `Agreement.verified` is False.
           Client detail renders "NDA on file (not verified)".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 Legal approval → verification path")
@pytest.mark.asyncio
async def test_legal_decision_flips_verified_true(session):
    """
    Given: NDA on file for client C, and a SOW package with a Legal
    approve decision that references NDA.
    When:  the decision commits.
    Then:  the client's NDA row now shows `verified = True` and
           `verified_by = <legal user>` and `verified_at = <ts>`.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 signature hold-reasons list (D3)")
@pytest.mark.asyncio
async def test_signature_holds_do_not_list_nda_msa_by_default(session):
    """
    Given: SOW package ready for signature; NDA on file but unverified.
    When:  we call `GET /signature/holds/{package_id}`.
    Then:  the response does NOT list "NDA missing" or "MSA missing"
           unless a code-level verification requirement exists.
           If a rule is present, its `rule_id` is emitted and recorded
           in decisions.md — the test opens the decisions file and
           asserts the rule_id is present as evidence.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W2 client detail page render")
@pytest.mark.asyncio
async def test_client_detail_shows_two_independent_facts(session):
    """
    Given: NDA uploaded but not verified.
    When:  we render `/clients/:id`.
    Then:  the client detail page emits two rows for NDA — one
           "On file: yes (link, uploader, ts)" and one
           "Verified/signed: no (needs Legal review)".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 approval submission gate")
@pytest.mark.asyncio
async def test_neither_on_file_nor_verified_blocks_submission(session):
    """
    Given: SOW package with NO NDA on file, ready in all other ways.
    When:  submitter submits for approval.
    Then:  the server returns 200 (or the next expected state),
           NOT a 4xx with reason "NDA missing". D3 says neither
           on-file nor verified blocks review or submission.
    """
    raise AssertionError("skeleton")
