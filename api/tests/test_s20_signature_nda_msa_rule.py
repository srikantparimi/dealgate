"""T41 · signature NDA/MSA rule alignment (S20 · W5).

Per L13:
> The same SOW's readiness says NDA/MSA is note only and nothing is
> blocked; Signature lists NDA/MSA among Held reasons. Other
> prerequisites are also pending.

Per D3 (contracts.md §2):
> Neither on-file nor signed/verified blocks review or submission.
> Remove NDA/MSA from Signature hold reasons UNLESS an explicit
> verification requirement exists in code — if it does, record in
> decisions.md.

**Skeleton, xfail until W3 + W7 remove the contradiction.**

Test cases:
  1. With every other signature prereq met + NDA on-file but NOT
     verified, signature/holds does NOT include NDA/MSA (contradiction
     with readiness fixed).
  2. If a code-level verification requirement exists (rule id), it
     lives in decisions.md AND appears in signature/holds; the surface
     is consistent.
  3. Client detail, workspace, signature UI and server all agree on
     the two facts.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W3 + W7 alignment (L13 contradiction, D3)", strict=False)
@pytest.mark.asyncio
async def test_signature_holds_omits_nda_msa_when_no_code_rule(session):
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on decisions.md documenting the rule if it exists")
@pytest.mark.asyncio
async def test_if_rule_exists_it_is_documented_and_uniformly_applied(session):
    """
    If a verification requirement exists in code:
      - It appears in signature/holds with a `rule_id`.
      - It is named in decisions.md.
      - Client detail + workspace + signature + server all agree.
    If no rule exists:
      - signature/holds does NOT list NDA/MSA at all.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W2 client detail + W3 workspace surface")
@pytest.mark.asyncio
async def test_four_surfaces_agree(session):
    raise AssertionError("skeleton")
