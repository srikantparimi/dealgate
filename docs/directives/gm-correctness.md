# Directive: GM correctness and stop re-asking for provided data

From: Kanna Parimi, product owner. 19 September 2026. This is the fourth report of the same class of defect. Treat this as a stop-the-line order: no new features until every item below passes.

## The failing case, worked by hand

Fixed-price SOW, $50,000, both resources in the US:

| Resource | Hours | Cost rate | Cost |
| --- | --- | --- | --- |
| SME 1 | 80 | $120/hr | $9,600 |
| SME 2 | 160 | $220/hr | $35,200 |
| **Total delivery cost** | | | **$44,800** |

- Revenue = $50,000 (the fixed price; nothing else, ever, for a fixed-price SOW)
- GM = (50,000 − 44,800) / 50,000 = **10.4%**
- US floor 35% → **fails by 24.6 points**; minimum price at floor = 44,800 / 0.65 = **$68,923.08**
- Correct system behavior: GM sheet complete, red floor test, routes to CEO exception. No question to the user.

If the app shows anything other than 10.4% for this input, the GM engine is wrong. Commit this exact case as `tests/gm/fixed_price_simple.test` **before** touching any code, watch it fail, then fix until it passes. That is the required order of work.

## Root causes you must fix, not patch

**1. One GM engine, pure, table-tested.**
There must be exactly one function that computes GM: inputs (engagement type, revenue terms, resource lines, geography split) → outputs (revenue, cost, GM per geography, combined, floor results, minimum price). Pure, deterministic, Decimal, no I/O, no UI math anywhere. If any screen computes its own numbers today, delete that code and call the engine. Build a table-driven test file with at least these cases and hand-computed expected values:

- The $50k case above.
- Fixed price, mixed: $90k US / $55k India, $65k / $30k cost → 27.78% / 45.45% / 34.48%, both fail (from the blueprint).
- Staff aug: hours × bill rate revenue vs hours × cost rate.
- Managed service: monthly fee × term.
- T&M with a cap.
- Assessment, US-only, exactly at 35.000% → passes at full precision.
- India-only at 49.999% → fails (no rounding before the test).
- Zero or missing revenue → `incomplete`, never a percentage.

**2. Fixed price means the price is fixed.**
For `fixed_price`, revenue = the extracted contract price. The engine must never derive revenue from bill rates, and never ask for bill rates at all — bill rate is not a required field on a fixed-price staffing line. Cost side only: hours × cost rate. Requiring `Staffing[0].Hourly Cost` when the staffing sheet already provided it means the form state and the derived model are two different objects. There must be **one** staffing model in state, populated by extraction, edited in the grid, read by the engine and by validation. Validation asks for a field only when it is absent from that one model.

**3. The template proposes, the SOW decides.**
The user had 2 SMEs; the app demanded 3 engineers. That means the fixed-price template has hardcoded minimum roles overriding extracted staffing. Remove every hardcoded role list and minimum count. Template defaults apply only when the SOW yields no staffing at all, and they arrive as editable pre-filled rows marked `defaulted`, never as validation errors. Deleting a defaulted row is always allowed. Role names are labels, not schema: 2 SMEs is a complete team if the user says so.

**4. Signatories are people, not free text and not a blank.**
Signatory fields are a searchable dropdown from the user/contact list: internal signatories from the authorized-signatory list in Settings → People & access; client signatories from that client's contacts, with an inline "add contact" (name, title, email) that saves to the client record. Extracted signatory names from the SOW pre-select their matches.

## Regression protocol (why this is the 4th time)

Every bug fix from now on lands as: (1) failing test reproducing the report, committed first; (2) the fix; (3) the test stays in CI forever. Before telling the product owner anything works, run the walkthrough yourself in the browser on staging: upload the $50k fixture, confirm zero unexpected required fields, confirm 10.4%, confirm the CEO route appears, screenshot each step and attach them to the report. A report without the screenshots and the passing test IDs is not a completion report.

Rules recap that this work must satisfy: money is Decimal end to end; floors compared at full precision; missing cost → `incomplete`, never zero, never a made-up question; every field has provenance and pre-filled is the default state.
