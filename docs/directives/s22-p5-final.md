# S22-P5 final — one build, audited (2026-10-12)

The product owner asked for one last build and no more. Before writing this, the whole trail was re-audited against the real model — every assumption in the importer checked with code, not by reading. Four things would have shipped wrong; they are fixed here with tests, alongside the streaming read from P5d. This replaces `s22-p5d-streaming.md`.

## What was found, and what changed in the importer (`forecast_model_import.py`, replaced; do-not-modify)

1. **Re-import would have collapsed placeholder seats.** Costco carries eleven `TBC` rows on SOW #12 and Fontainebleau two rows for one name. The idempotency key named in P5 — (client, assignment_key, person, segment) — would have merged eleven seats into one on the second import and silently dropped ten people's forecast. Every row now has a `row_key`: the name, plus ` #n` when the name repeats on the engagement. `to_engine` sets `Allocation.id = "{assignment_key}:{row_key}:{segment}"`, and that string is the identity a re-import matches on. Extensions carry their base row's key. Zero collisions on the real model (417 allocations, 417 distinct ids).
2. **Actual hours were wrong for 1,606 of 2,705 actual months.** The sheet's leave columns say "hours" and hold days (SoundHound), hold days under an hours header (Costco September), and Costco's Days column is the calendar, not what was billed. Where the sheet has an hourly rate and a billed amount, actual hours are now billed ÷ rate — the invoice is the truth. On the real model, hours × rate equals billed on 2,705 of 2,705 such months. Billing-loss revenue was never affected (it comes from the billed cell); the Actual hours line was.
3. **Extensions billed one day twice.** An extension with no typed start began on the previous segment's end date; nine typed extensions also start on the day the original ends, and one (Fremont, Dhira Vaidya) ten days before. Now: a blank start is the day after; a typed overlap means the newer contract wins from its start and the original gives way the day before — no typed date is changed, and the ten-day case is noted in the report. Zero overlaps left.
4. **Assumptions the report did not state.** New section "Assumed, because the workbook does not say": every person imports as W-2 (the model has no W-2/1099 column; for US people that is 36% burden, a contractor is 5%); Offshore → India - Pune, Onsite → US; cost per hour unknown; USD throughout; actual hours from the invoice.
5. **Streaming read** (from P5d): dry run 4.8 s → 1.3 s locally, report byte-identical before that change; expect ~6 s on staging instead of ~25 s.

Re-audit after the fixes, on the real model: identity collisions 0 · hours×rate = billed 2,705/2,705 · overlapping extensions 0 · blockers 7 (unchanged) · dashboard clients 44 · as-of 2026-09 · forecast months within 5% of the sheet's own plan 37/89, up from 31/89 — the rest are the beyond-SOW rows and the inconsistent Costco rows the report already lists. `python -m pytest api/tests/forecast -q` → **45 passed**.

## Your items

1. Importer and tests from this pack in place; 45 passed first. The synthetic fixture changed (Zeta Unlisted has two `TBC` rows and an invoice that is not units-minus-leave; Gamma Health-VMS has Person G3 and G4 with extension cases). Specs that count Gamma or Zeta rows need the new counts; the "complete copy" for the owner path is still the fixture minus Zeta Unlisted.
2. **Migration**: `allocation.import_key` (text, nullable), unique per engagement where not null. The import writes `to_engine`'s `Allocation.id` into it and matches on it when re-importing. The old (client, assignment_key, person, segment) match goes away. Contract carries `import_key` (readOnly) on Allocation and the corrected idempotency sentence.
3. Pytest: import the fixture twice → Zeta has four allocations both times, `TBC #1` and `TBC #2` both present, nothing duplicated, nothing collapsed; Gamma Person G4's first segment ends 2026-03-30.
4. Re-time the staging dry run on the real master and record it in bug-log row 8.
5. Nothing else. No screen changes; the prototype is v5 as committed.

Report items 1–5 by number in the five states with proof. No budget; anti-stuck; heartbeat. Rides on `feat/s22-p5`; no merge until the product owner's click. After this build the only thing left is the product owner's sheet edits and the Load button.
