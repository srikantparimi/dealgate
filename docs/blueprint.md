# DealGate Governance Blueprint (policy)

The source of record for this file is `SmarTek21 Deal & Delivery Governance
Platform — Build Guide.docx` in the parent directory. Convert that document
(or its successor) into this markdown file before Sprint 1 starts, verbatim
except for formatting. Do not paraphrase policy.

Rules to encode in code (mirror of the Build Guide §2, do not diverge):

- US work: 35% GM floor, tested on the US component alone.
- India work: 50% GM floor, tested on the India component alone.
- Mixed onshore/offshore: each component tested on its own; blended shown for information.
- Any floor missed → CEO exception with generated brief; release stays locked.
- A missing NDA or MSA never blocks a SOW, an approval or signature. It is a warning and a flag only: a net-new client past
  stage 1 without an NDA or MSA is flagged in the Pipeline, the Command Center and the client panel. Coverage is recorded per
  client (the client's own copy, a standard copy, or a mark). S17 removed the signature gate; S24-AG1 confirmed warn-only
  (`docs/questions.md`, S24-AG1).
- Any post-approval change to scope, price, cost, staffing or allocation voids approvals.
- Missing cost → GM sheet is "incomplete". Never treat missing as zero.
- AI estimate labeled "Indicative estimate, requires Delivery and Finance validation".

Formulas:

- `GM = (revenue − delivery_cost) / revenue`
- `min_price = delivery_cost / (1 − floor)`

Store money as `Decimal` / `NUMERIC(14,2)`. Compare unrounded. Round only for display.
