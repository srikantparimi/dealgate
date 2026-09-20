# Directive: there are two staffing models in the code. Delete one. (5th report)

From: Kanna Parimi, product owner. 20 September 2026. This supersedes progress claims against `GM_Correctness.md` — the screenshots below prove those fixes were not made where it counts. Stop the line: nothing ships until the proof protocol at the bottom passes.

## What the screenshots prove

Same SOW (Peppermill, fixed price $50,000, extracted at 100% confidence):

- **Staffing & rates page** (`/sows/{id}/staffing`): I entered **2 × SME, Senior, US, 80h and 160h, cost $120/hr**. Saved. GM strip still shows `Blended — · US — · India —`.
- **Confirm SOW page** (`/sows/new?opportunityId=…`): shows a different team entirely — **Architect Principal / Engineer Senior / Engineer Mid**, rate 0.0000, 160h each, allocation **1.0000%**, provenance `manual`. Revenue **0.00**. GM `Unavailable`. Blockers demand `Staffing[0..2].Hourly Cost` for those three phantom rows.
- **Signatories** blocker says "extracted value missing", Jump-to-field lands on a row with **no input control**.

## Root cause — say it plainly and fix it structurally

There are **two staffing stores**. The Staffing & rates page writes one record; the Confirm page renders a template-generated auto-plan (the hardcoded Architect+2-Engineers default that `GM_Correctness §3` ordered removed) and validation reads the auto-plan. Everything I entered is ignored. On top of that, the confirm-page GM reads revenue 0 instead of the extracted $50,000, and allocation stores 100% as `1.0000%`.

This is not four bugs. It is one architecture violation plus fallout. Fix the architecture:

1. **One staffing record per SOW version.** One table, one API resource (`/sows/{id}/staffing`), one React Query key. The Staffing & rates page and the Confirm page's "Staffing & GM" section must be the **same component** reading the same query. Delete the second model and the code that builds it. If you cannot name the file you deleted, the fix didn't happen.
2. **Auto-plan seeds only an empty record, once.** The moment a human edits or saves staffing, `staffing.source = human` and no template, extractor or re-run may ever overwrite or append to it. Assert this in a test: save 2 lines, re-open confirm, exactly those 2 lines render, provenance `manual`, byte-identical to what was saved.
3. **Kill the phantom roles for good.** Remove the template role list entirely (grep for `Architect`/`Engineer` seeds in the studio code). Validation iterates the real record: with my 2 lines costed at $120, there are **zero** Hourly Cost blockers.
4. **Fixed price revenue = extracted price.** The GM panel on both pages calls the one engine with revenue $50,000 from the SOW record — never 0, never derived from bill rates (bill rate is optional display on fixed price, as already directed). With my inputs the correct output is: cost $28,800 (80×120 + 160×120), GM **42.4%**, US floor passes by 7.4 pts. If the two pages can disagree, they are not calling the same engine — they must call the same endpoint and render its response, no client-side math.
5. **Units.** Allocation/utilization is a percentage: store 100 as 100.00% (or 1.0 internally, rendered ×100 — pick one and add a unit test). `1.0000%` on screen for a full-time line is a defect.
6. **A "needs you" field is an input, not a label.** Signatories renders the searchable dropdown (internal signatories from People & access, client contacts with inline add) directly in the blocker row and in the Scope & terms row. "Jump to field" must land on a focusable control. If a blocker points at something that cannot be edited on that page, the blocker is the bug.
7. **The GM strip on the staffing page** shows the engine result live after every save — with hours and cost present on a fixed-price SOW it can never legitimately show `—`.

## Proof protocol — no completion claim without all of it

Run this yourself in the browser on staging and paste the screenshots in your report:

1. Upload the Peppermill fixture → confirm page shows price $50,000, type fixed price.
2. Open Staffing, enter exactly: SME/Senior/US/80h/$120 and SME/Senior/US/160h/$120. Save.
3. Staffing page GM strip shows US 42.4%, passes. Screenshot.
4. Return to Confirm: the same 2 SME lines (no Architect, no Engineers), revenue $50,000, GM 42.4%, no Hourly Cost blockers. Screenshot.
5. Signatories: pick an internal signatory from the dropdown, add a client contact inline. Blocker clears. Screenshot.
6. Submit for approval succeeds; approvers resolve; no CEO gate (42.4% > 35%). Screenshot.
7. Change line 2 to $220/hr → GM drops to 10.4%, CEO gate appears. Screenshot. (This is the earlier directive's case; both must hold in the same session.)
8. CI: the byte-identity staffing test, the units test, and the existing goldens all green; the `grep` gate for template role seeds added and clean.

Report format: the 8 screenshots, the test IDs, and the list of files deleted. Nothing else. If any step cannot pass, say which and why before writing more code.
