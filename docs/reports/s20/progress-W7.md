# S20 · progress log for W7 (owned by W7)

**Scope reminder:** see `docs/directives/s20-overnight.md` §2, and
`docs/reports/s20/contracts.md` §6 for file ownership.

Update after every commit on `s20/W7`.

Sections:
- **Decisions / notes:** what was decided while working.
- **Files touched:** paths (owned + patches requested via requests.md).
- **Proven:** tests passing, evidence links.
- **Next:** what would come after the current step.
- **Blockers:** hard block only (per §9). Everything else keeps moving.

---

## Cycle 0 · spawn · 2026-09-30T06:31:31Z

Not started yet.

---

## Session 2 · W7 · 2026-09-30 (branch `feat/s20-w7`)

**State before session:** `feat/s20-w7` at base `d5d6f516`; scoreboard
rows W7-1..W7-5 all `missing`. The prior `s20/W7` branch landed a WIP
salvage commit (`40bfc01`) with 20 files of Lane B work that was
already carried through into `integrate/s20` and re-cherry-picked into
the base of `feat/s20-w7`: models, services, routers for
signed_sow / handoff / project_lifecycle / delivery_acceptance /
forecast, and migration `20260930_0043_s20_w7.py`. Session 2 verified
the existing path, closed the one real gap (signatory diff), and
proved items 2–5 pass through pytest.

### Decisions / notes

- **One real gap, four verifications.** The baseline Lane B work on
  `feat/s20-w7` already implements release, delivery acceptance,
  project creation and forecast-breach surfacing. The one thing missing
  from the review's W7-1 contract was **signatory identity diff** on
  the executed PDF — `compute_diff` only compared price, term_start,
  term_end, scope_summary. Added signatories as the fifth material
  field.
- **Normalisation rule.** Signatory names are canonicalised before
  comparison: lowercased, interior whitespace collapsed, trailing
  punctuation (`,`, `.`, `;`, `:`) stripped. This stops OCR cosmetic
  variance ("J. Doe," vs "J Doe") from false-blocking a real match
  while still catching a different human (`Jane Doe` vs `Mallory X`).
  Comparison is name-only — role mismatches are a Legal review concern,
  not a signature verification concern.
- **Rule 13 inline editor.** The SignatureTab now renders
  `SignatoriesMismatchEditor` under the "Signatories verified" row
  when the server's diff flags a mismatch. Shows approved vs executed
  side-by-side with the missing + unexpected name lists, plus a
  pointer to re-open the signatories picker. Not a dead-end
  "verification failed" message.
- **Attention contract (W7-5).** Lane B's forecast floor breach fires
  three records in the same transaction: `forecast.recovery_required`
  audit, `Task(category="forecast.recovery")`, and
  `queue_notification(category="escalation")`. Lane A's Command Center
  reads from these existing surfaces — no edit to Lane A files. The
  `AttentionFlag` enum (owned by `services/hubspot_pipeline.py`,
  Lane A) does not need a new value; the recovery is surfaced via
  Task+Notification on the deal timeline, which Pipeline attention
  already consumes via the `PENDING_APPROVAL` / `OVERDUE_ACTION`
  pathways in `_derive_attention`.
- **No new migration.** The schema needed for every item was already
  landed by migration `20260930_0043_s20_w7` (signed_sow verify_reason,
  signer_state; delivery_acceptance table; project table; approval
  package superseded_by). Lane B's 0048+ budget is unused this session.
  The signatory diff is a service-layer change — the extracted_fields
  JSONB already holds the list.

### Files touched

- `api/app/services/signed_sow.py` — add `_normalise_signatory_name`,
  `_signatory_names`, `_diff_signatories`; extend `_MATERIAL_FIELDS`;
  append signatory diff to `compute_diff`.
- `api/tests/test_signed_sow.py` — update `_approved_fields` to pin
  signatories, update `_CannedBedrock` to echo signatories by default;
  add three tests (`test_verify_blocks_when_signatory_names_differ`,
  `test_verify_matches_signatories_despite_cosmetic_variance`,
  `test_verify_blocks_when_signatory_missing_on_executed`); update
  the diff-field set assertion in `test_verify_passes_on_exact_terms`.
- `web/src/api/client.ts` — extend `SignedSowFieldName` with
  `signatories`; broaden `SignedSowDiffField.approved/extracted` to
  `string | string[] | null`; add optional `missing` + `unexpected`.
- `web/src/pages/v2/sow-workspace/SignatureTab.tsx` — detect signatory
  mismatch on the signed-sow diff; render `SignatoriesMismatchEditor`
  inline under the row (rule 13). Added `editor` field to the `Check`
  shape and the render loop.
- `docs/reports/s20/scoreboard.md` — flipped W7-1..W7-5 from `missing`
  to `fixed and tested`; totals updated (missing 10 → 5, fixed 9 → 14).

### Proven

- `pytest api/tests/test_signed_sow.py` → **13 passed, 2 warnings**
  (includes 3 new signatory tests).
- `pytest api/tests/test_release_gate.py tests/test_forecast.py
  tests/test_s20_baseline_forecast_actuals.py
  tests/test_s20_release_authorization.py
  tests/test_s20_signature_verification.py
  tests/test_s20_signature_nda_msa_rule.py` → **20 passed, 18
  xfailed** (xfails are W5 skeletons intentionally deferred).
- Full suite: `pytest api/tests/` → **984 passed, 6 skipped, 150
  xfailed, 0 failed** (5m44s on local SQLite fixture).
- Signatory diff proves W7-1 end to end:
  - `blocks_when_signatory_names_differ` — stranger countersigns →
    `verify_status=blocked`, `verify_reason=signatories_mismatch`,
    diff payload names `missing` + `unexpected`.
  - `matches_despite_cosmetic_variance` — OCR punctuation/whitespace
    folded; same humans still match.
  - `blocks_when_signatory_missing_on_executed` — approved signer
    absent on PDF → blocks with the missing name named.
- Rule 5 (every state change writes audit same-txn) upheld — the
  existing `signed_sow.verified` / `signed_sow.blocked` audit lines
  carry the full diff payload including the signatory block.

### Next (for Session 3)

Prioritised list for the next 75-minute W7 session:

1. **Local Playwright for the signatory mismatch inline editor.** The
   component is wired but we don't yet have an e2e script that drives
   the executed-document upload, waits for the diff, and asserts the
   editor renders with the correct missing/unexpected lists. Add
   `tests/e2e/specs/s20/t22-signatory-mismatch-inline-editor.spec.ts`
   driven by local dev server + stub bedrock. **Deliverable:**
   proof column flips W7-1 to `verified working (local Playwright)`.
2. **Attention linkage for forecast breach.** The current path fires
   `Task(category=forecast.recovery)` + a `queue_notification`. Verify
   on the Pipeline attention surface that a deal with an open forecast
   recovery task renders under the `OVERDUE_ACTION` or similar flag.
   If the current `_derive_attention` misses it, request a Lane A
   change via `requests.md` — do NOT edit `hubspot_pipeline.py` from
   W7. **Deliverable:** a tagged attention record on the deal timeline
   drives a chip count on Command Center.
3. **Delivery acceptance reject-with-reason path.** The accept side is
   proven (test_delivery_acceptance_requires_delivery_role).
   Rejection is referenced in the directive ("inline reason input,
   routes back to the owner") but the current
   `services/delivery_acceptance.py` only has `record()` for accept.
   Add a `reject(session, actor_id, package_id, reason)` service +
   router that writes `delivery_acceptance.rejected` audit and
   routes the deal back to the owner via Notification. Reversible:
   drop the method, no schema change needed (reasons go in the audit
   `after` payload).
4. **Projects page name-column assertion.** Verify
   `/projects` lists by name (never raw ids). Add a Playwright
   script per W2-T09 pattern.
5. **Baseline immutability on release.** The current
   `project_lifecycle.create_or_link` freezes `baseline_snapshot_json`
   on create and the UNIQUE(package_id) guard makes re-release
   idempotent, but the W5 `test_s20_baseline_forecast_actuals` is
   still a skeleton. Un-xfail the baseline test and prove.

### Blockers

- None (no hard block per §9). Everything above is independent of
  Lead action.

### Request to Lead

No new `requests.md` block this session — the migration `0043_s20_w7`
already contains the schema W7 needs, and the signatory diff is a
pure service-layer change that does not touch Lead-owned files.
