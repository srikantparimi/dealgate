# Directive S15: the confirm/staffing page works end to end, or nothing else matters

From: Kanna Parimi, product owner. Commit as `docs/directives/s15-confirm-page-integrity.md`. This is the top priority — ahead of the s14b merge. Evidence: opportunity 4aab5ea6-f788-43f8-a2de-c759cfde1004 on staging, four screenshots in `docs/reports/s15/input/`. Two days have gone into this page; this directive consolidates every open defect so it is fixed once, together, and proven with my exact document.

## The root cause, stated plainly

Extraction returned ZERO fields for this document, and the UI presented that single pipeline failure as fifteen separate per-field problems ("Not on the SOW" × 9, price $0, GM Unavailable × 6, seven blockers). First task, before any UI work: pull the extraction job record for this SOW, find out why it produced nothing (scanned PDF needing the OCR path? job error swallowed? unsupported layout?), fix that cause, and write it in the report. The Peppermill docx extracts at 100% — this document is the second data point the extractor has ever faced, and it failed silently. Silent is the defect.

## D1 — Extraction honesty

- If the extract job failed or returned no fields: one banner at the top of Confirm — "We couldn't read this document (reason). Retry extraction, or fill the fields below manually." Fields then carry provenance `manual`, not the lie "Not on the SOW".
- "Not on the SOW" is only ever shown when extraction SUCCEEDED and the field is genuinely absent from a parsed document.
- A failed extract job must never let the flow continue as if it ran. Job status is part of the SOW record and visible on the page.

## D2 — Every blocker is an editor (universal, this time)

The signatories fix was made as a one-off; the pattern was the requirement. Every "What's still needed" row renders its input INLINE in the row: text field for Scope Summary, money field for Price, date pickers for Term start/end, the two-candidate chooser for Engagement Type ("fixed_price / tm" as two buttons), list editor for Deliverables. "Jump to field" must land focus in a real control. Enforce structurally: a blocker registry maps every field key → its editor component, and a unit test fails the build if any blocker key has no editor. A blocker that cannot be resolved on the page it appears on is itself the bug — this is now a CLAUDE.md rule (add it as rule 13).

## D3 — Missing price is one problem, not seven

On a fixed-price SOW with no price: one prominent callout on Staffing & GM — "Set the contract price to calculate margin" with the money input right there. The GM summary shows a single "Waiting on contract price" state. Never render "$0" for an unset price (that violates the never-assume-zero rule in display, not just calculation), and never render six separate "Unavailable of price" rows. The moment price is entered, the engine computes and the panel fills — no save-then-navigate loop.

## D4 — Staffing page layout and inputs

- Fix the broken layout: the "Add role" button currently overlaps the helper text; the grid columns misalign with their headers at 1440px. Whatever CSS caused it, add the fix and a Playwright screenshot of this page at 1440 and 1280 to the proof so misalignment is looked at, not assumed.
- Dates: default Start/End from the SOW term when known; when term is unknown, the date inputs still work and the helper says why they're empty. The helper text about incomplete rows must be readable, not under a button.
- Input formatting everywhere: money inputs show $ formatted values (never 800.000000000 — the raw-decimal ban applies to inputs, not just display), utilization is an integer %, hours are integers.

## D5 — Direct costs polish

- The three identical Travel/$800 rows suggest either accidental repeat-adds or a save that gave no feedback. Save must be idempotent, show a saved confirmation, and duplicate identical rows added within one session prompt "same as the row above — add anyway?".
- "Reimbursable?" becomes an explicit Yes/No toggle with the one-line consequence ("Yes = client pays it back; stays out of margin").

## D6 — Delete the noise

Kanna's read of "What's still needed" as "a waste section blocking the next stage" is what happens when blockers are dead text. After D2 it becomes the fast path: the section retitles to "Finish these to submit", each row is an editor, and completing the last one flips the header CTA to Submit for approval (s14b behavior — build the CTA state here so the s14b merge slots into it rather than fighting it).

## Definition of done — my journey, my document

Using the EXACT document from opportunity 4aab5ea6 (fetch it from the SOW record's S3 key), on staging, screenshots at every step in `docs/reports/s15/`:

1. Re-upload it → either extraction now reads it (say what was fixed), or the honest banner appears with the reason and Retry.
2. Every blocker row has an inline editor; I can set price, dates, scope summary, and pick the engagement type without leaving the page.
3. Entering the price makes GM compute immediately from the already-saved staffing (2 SME × $120); floor test renders with the formatted panel.
4. No "$0" price, no raw decimals anywhere including inputs, no overlapping controls at 1440/1280 (screenshots attached).
5. Header CTA flips to "Submit for approval" when the last blocker clears.
6. Total time from upload to submit-enabled, performed by you in the browser: under 10 minutes. State the measured time.
7. Existing suites green; the blocker-registry test in CI.

Report `docs/reports/s15.md` standard format. Nothing else — no other slice, no refactors beyond these defects — until this is closed.
