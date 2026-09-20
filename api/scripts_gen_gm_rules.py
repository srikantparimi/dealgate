"""Generate docs/gm-rules.md from the engine's own rule table.

Written as a script rather than prose so the page Finance signs off on and
the code that runs are the same statement. If a rule changes and this is not
regenerated, CI fails — see `tests/test_gm_rules_doc.py`.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.gm.engine import ENGINE_RULES  # noqa: E402
from app.gm.policy import INDIA_FLOOR, US_FLOOR  # noqa: E402

HEADER = f"""# How the gross margin is calculated

Generated from `api/app/gm/engine.py` — do not edit by hand. Run
`python api/scripts_gen_gm_rules.py` after changing a rule.

This page exists so Finance can read what the engine does and confirm it. The
table below is the same data the engine reads at run time; there is no second
description of the rules that could drift from the code.

## The floors

| Geography | Floor |
| --- | --- |
| US | {US_FLOOR * 100:.0f}% |
| India | {INDIA_FLOOR * 100:.0f}% |

Each geography is tested against its own floor, independently. The combined
figure is shown for information and is never the thing that passes or fails —
a healthy US component must not carry a failing India one over the line.

Floors are compared **unrounded**. 35.000% passes; 34.9999% does not. Rounding
to two places first would make both read "35.00%" and erase the distinction.

## What the engine will not do

- It will not present a number alongside a missing input. A missing cost rate
  makes the result **incomplete** and names the line; it is never read as zero
  cost, which would inflate the margin and pass a floor the engagement fails.
- It will not report a percentage when revenue is zero, negative or absent.
  That is an **exception** state: `0.0%` reads as a real and very bad margin,
  and "there is nothing to divide by" is a different statement.
- It will not guess at an engagement type it has no rule for.
- It will not ask a question. Where a field is absent it says which field, on
  which line. Deciding what to do about that belongs to the screen.

## Rules by engagement type
"""

FOOTER = """
## Cross-cutting rules

- **Geography.** Every cost line carries a location. Fixed-fee revenue is
  split by the recorded allocation where Finance has set one, otherwise by
  cost-weighted effort. A line with no location makes the result incomplete
  and is named.
- **FX.** A non-USD SOW is converted at the rate and date Finance published,
  stored on the GM version. Never a live rate at render time — that would
  make the same SOW show a different margin tomorrow.
- **Discounts and credits.** Deducted from revenue before any floor test.
  Testing the list price passes the engagement on money we never charged.
- **Pass-through expenses.** Held outside the margin at zero, and shown
  separately.
- **Subcontractors.** Their invoiced cost is delivery cost, at the location
  where the work is performed.
- **Contingency.** Applied to cost where a percentage is set.
- **Amendments and change orders.** A new package on the same SOW. The engine
  reports the amended whole *and* the delta, because a whole that still looks
  acceptable can hide an addition priced well below the floor. Prior
  approvals stay historical.
- **Hybrid SOWs.** Each component runs under its own rule and is tested
  against its own floor. Forcing one template over a document containing a
  fixed build and a monthly service produces a number that describes neither.

## Verification

Every rule above is covered by a golden fixture in `fixtures/sows/`, each with
an expected-results file computed by hand and verified independently before
the engine existed. The universal invariants — exact Decimal arithmetic,
US/India reconciliation, determinism, scale-invariance of the margin, and
non-mutation of inputs — are asserted as property tests over generated inputs
across every type in the table.
"""


def render() -> str:
    parts = [HEADER]
    for key in sorted(ENGINE_RULES):
        rule = ENGINE_RULES[key]
        parts.append(
            f"""
### {rule.label}

`{rule.engagement_type}`

| | |
| --- | --- |
| **Revenue** | {rule.revenue_rule} |
| **Cost** | {rule.cost_rule} |
| **Never** | {rule.never_do} |
"""
        )
    parts.append(FOOTER)
    return "".join(parts)


if __name__ == "__main__":
    target = pathlib.Path(__file__).resolve().parents[1] / "docs" / "gm-rules.md"
    target.write_text(render())
    print(f"wrote {target} ({len(render().splitlines())} lines)")
