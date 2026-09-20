# DealGate: the SOW is the input. Everything else is derived.

Put this in `docs/` and link it from `CLAUDE.md`. It overrides any story, spec section or prototype screen that asks a person to type something the SOW already says.

## The rule

A user uploads a SOW. The system reads it, decides what kind of engagement it is, picks the client's rate card, builds the staffing plan, calculates the GM sheet, runs the margin tests, works out who has to approve, sets the renewal and notice dates, and presents one confirmation screen. The human confirms or corrects. The human never fills a blank form.

If a screen asks for a value the SOW contains, or that the system can look up or calculate, that screen is a defect. Target: a standard SOW goes from upload to "submitted for approval" in under ten minutes of human time, most of it reading.

## What "derived from the SOW" means, step by step

| Step | Input | How it is derived | Human action |
| --- | --- | --- | --- |
| 1. Extract | SOW file (PDF/Word) | Model extracts every commercial field with a page reference: client legal entity, title, term dates, notice period, price, currency, billing basis, payment terms, deliverables, milestones, resources and rates if listed, coverage hours if listed, acceptance, signatories | Confirms only fields flagged low-confidence or missing. Everything else is pre-confirmed. |
| 2. Classify engagement type | Extracted fields | Rules first, model second. Monthly fee + service hours/SLA → Managed service. Named roles with hourly/daily rates and hours → Staff augmentation (one role = Single resource). Fixed fee + deliverables/milestones → Fixed price. "Assessment", 2–6 week term, workshops → Assessment. "Time and materials" / not-to-exceed → T&M. Placement fee → Permanent placement. | None if confidence ≥ 0.85. Otherwise one click between the top two candidates. |
| 3. Resolve rate card | Client legal entity + engagement type | **Rate cards are per client, not company-wide.** Each client has a versioned, effective-dated bill-rate card (usually the MSA rate schedule). Resolution order: client card → SOW-stated rates override for revenue → client segment default → company default. Any fallback is shown as a warning on the package, never silent. Cost rates are separate: HR cost bands by role, seniority and location, never from the client. | Finance maintains client cards; the system asks once when a new client has none and remembers it. |
| 4. Build staffing plan | Type + extracted fields + rate cards | Staff aug: straight from the SOW resource table. Managed service: coverage hours ÷ FTE capacity per shift → headcount by role, deterministic. Fixed price and assessment: deliverables → roles and hours proposed from the capability catalog and the closest approved past SOWs, with the source SOWs cited. T&M: rate card × forecast utilization. | Delivery lead reviews the proposed grid and edits lines. Editing is the review; there is no separate "enter delivery model" step. |
| 5. Calculate GM | Staffing plan + cost bands + payment terms | Revenue schedule from milestones or billing basis. Cost from lines × cost bands × hours. Geography split from resource locations, automatically. For a mixed fixed-fee SOW the default allocation is cost-weighted effort; Finance can override with a recorded basis. US, India and combined GM, minimum price, shortfall. All decimal, all server-side. | None. Finance overrides allocation only if the default is wrong. |
| 6. Route approvals | Client + type + margin result | Approvers resolved from the function-owner table and the client's account team. Delivery and HR first, then Finance and Legal. CEO gate added automatically when any floor fails, with the CEO brief pre-drafted from steps 1–5. Due dates from SLA. | Account owner writes the business rationale when a CEO gate opens. That is the one paragraph a human must write. |
| 7. Schedule lifecycle | Term and notice dates | Renewal review at expiry − 2 calendar months, weekly nudges, notice-deadline task, 30/14-day escalations, immediate review for short SOWs. | None. |
| 8. Confirm and submit | All of the above | One screen: the derived package, with every field labeled `extracted` (page ref), `looked up` (source), `calculated`, or `needs you`. Only `needs you` fields block submit. | Reads, fixes what is wrong, submits. |

## Data the system needs once, then reuses

- Client rate cards (import from MSA rate schedules; the extractor can read them from the MSA the same way it reads a SOW).
- HR cost bands by role, seniority and location.
- Function-owner table: who approves for Delivery, HR, Finance, Legal per business unit; CEO and delegates.
- Capability catalog and past approved SOW models for estimation.
- Margin policy and cost definition (Finance).

When any of these is missing for a new SOW, the system asks for that one item inline, saves it to the master data, and never asks again for that client.

## Design rules for every story

1. **Every field has a provenance.** `extracted` (with page reference), `looked_up` (with source record), `calculated` (with formula version), `defaulted` (with the default's source), or `manual`. `manual` requires a justification in the story file for why it cannot be derived.
2. **Pre-filled is the default state.** Forms open populated. An empty field is a gap the system is reporting, not a task it is assigning.
3. **Confirmation, not entry.** Screens list what the system decided and why, with a "change" affordance per field. No wizard step may be blank on open.
4. **Editing is the review.** Delivery reviewing the staffing grid, Finance reviewing allocation, Legal reviewing entities all happen by editing the derived record, not by filling a parallel form.
5. **Client rate card, HR cost band, company policy: three different tables.** Never merge them. Bill rates vary by client; cost rates vary by location; floors are company policy.
6. **Confidence is visible.** Extraction and classification carry confidence scores; below threshold means "ask", above means "pre-confirm". Thresholds live in configuration, not code.
7. **Fallbacks are loud.** Company-default rate card, model-estimated hours, default allocation: each shows as a warning chip on the package and in the approver's summary.
8. **The adviser and the SOW pipeline share one estimation service.** Marketing's early estimate and the fixed-price staffing proposal use the same catalog and the same past-SOW retrieval, so numbers agree.

## Acceptance tests (add to `tests/e2e/`)

For each of the six sample SOWs in `fixtures/`:

- Upload → engagement type is selected automatically and correctly; no type dropdown is shown when confidence ≥ 0.85.
- The client's rate card is applied; a client with no card triggers exactly one inline request and the fallback warning.
- Staffing grid is populated without any manual line entry for staff aug and managed service; for fixed price and assessment, a proposed grid appears with cited source SOWs.
- GM sheet, geography tests, minimum price and shortfall are computed with zero manual numeric entry.
- Approvers are assigned automatically; the CEO gate appears for the below-floor fixture and does not appear for the others.
- Renewal, notice and escalation tasks exist with the correct dates.
- The confirmation screen shows every field's provenance; the count of `needs you` fields is ≤ 3 for a well-formed SOW.
- A human can go from upload to submitted in under ten minutes, measured in the browser test.

## What this changes in the existing documents

- Spec §13 "New SOW studio, five steps": the five steps remain as the *structure of the confirmation screen*, not as five blank forms. Steps 1–4 open fully populated.
- Spec §18 "Rate cards": tabs become Client cards / Cost bands / Policy. Client cards are keyed by legal entity with effective dates.
- Build guide §6.3–6.4 and §8: the Delivery Model Builder opens pre-filled from the SOW-derived plan; it is a review surface.
- `CLAUDE.md` rule 10: "Every field has a provenance; `manual` needs a written justification. A blank form on open is a defect."
