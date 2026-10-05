# Independent Commercial Editor Review

Latest result: the bounded independent rerun below verifies the five fixes
locally. The original failure evidence is retained unchanged for attribution.

Reviewed `5b46289112683384e3bfa1df773c0ab1162473ef` in isolated branch
`s21/qa-commercial-ui`, starting 2 October 2026 at 05:35 UTC, 15-minute budget.
Only this report and `web/src/__tests__/v2/CommercialEditorIndependent.test.tsx`
are owned additions. No production edits or changes to existing tests.

## Evidence

Independent tests: **19 cases, 12 passed, 7 failed**. Combined with the existing
two editor test files: **40 cases, 33 passed, 7 failed**. No skips, xfails or
retry configuration. The seven red assertions remain enabled. The original
21 worker tests still pass; their green result does not cover these findings.
`npm run typecheck` passed. The initial check caught a test-only unsupported
query option; removing that option retained the same exact-name matching and
all failure assertions. No production or financial expectations were changed.
Final exact-file combined run: 7 failed, 33 passed in 63.66 seconds.

Use this worktree's `web` directory and its own installed dependencies:

```sh
npm ci --ignore-scripts --no-audit --no-fund
env DEBUG_PRINT_LIMIT=0 npm test -- --run \
  src/__tests__/v2/CommercialEditorIndependent.test.tsx \
  src/__tests__/v2/CommercialModelEditor.test.tsx \
  src/__tests__/v2/CommercialProfiles.test.tsx \
  --maxWorkers=1 --minWorkers=1 --reporter=dot
npm run typecheck
```

API calls are mocked only at the UI boundary. Literal payloads and monetary
strings are independent expectations, not copied from production calculations.
Neither the real parser/calculator nor HTTP, authentication, storage, browser,
approval or signature providers run in this suite. No financial-accuracy or
full-profile acceptance claim follows from an unchanged payload test.

## Findings

1. **High: pending hybrid model change can target the wrong component.**
   `web/src/pages/v2/sow-workspace/commercial-editor/HybridFields.tsx:20`
   stores the pending choice by array index. Removing that child at `:66`
   leaves the pending index intact; the next child now receives its confirmation
   at `:81`. Confirming at `:92` replaces the sibling's pricing, not the component
   for which the user selected the new model. Reproduction uses a fixed-fee
   child followed by a unit-pricing child, selects Milestone for the first,
   then removes it. The replacement control incorrectly remains on the sibling.
   Test: `does not apply a removed hybrid child's pending model change to its sibling`.

2. **Medium: unsaved preview values become labelled as saved financial data.**
   `web/src/pages/v2/sow-workspace/CommercialModelEditor.tsx:136` clears the
   preview flag on edit without restoring the saved result. The label at `:606`
   then says `Saved calculation; edits not calculated`. Reproduction starts
   with saved revenue `111.11`, previews `999.99`, and edits Workstream again.
   The unsaved result remains displayed with the saved label; no save occurred.
   Test: `never relabels unsaved preview values as a saved calculation after another edit`.

3. **Medium: first calendar-cost assignment cannot be added for fixed/MSP.**
   `web/src/pages/v2/sow-workspace/CommercialModelEditor.tsx:476` hides the
   whole calendar editor unless the profile is calendar staffing, T&M calendar
   mode is enabled, or staffing already exists. Fixed-fee and recurring MSP
   drafts with an empty staffing array therefore have no Add assignment
   control. The equivalent child gate is in `HybridFields.tsx:156` (source
   review only for that child variant). S21-15/17/18 require independent
   resource-calendar costs for fixed fees and coverage/roster costs for MSP.
   Tests: `allows adding the first cost-calendar assignment for fixed_assignment`
   and `allows adding the first cost-calendar assignment for recurring_msp`.

4. **Medium: MSP credits and usage/overage terms cannot be corrected.**
   `web/src/pages/v2/sow-workspace/CommercialModelEditor.tsx:386` exposes only
   proration, included scope and monthly fees. The generic child renderer at
   `commercial-editor/PricingFields.tsx:124` has the same omission. Existing
   adjustments and usage survive round trips but are invisible/uneditable.
   Reproduction seeds credit `41.125001` and overage rate `9.250001`; neither
   has an input. S21-18 explicitly requires included units, overages and credits.
   Tests: `exposes an existing MSP credit value for correction` and
   `exposes an existing MSP usage value for correction`.

5. **Medium: unsupported persisted profile hides the editor without validation.**
   `web/src/pages/v2/sow-workspace/CommercialModelEditor.tsx:211` falls through
   to no editor or explanatory error for an unknown profile. A canonical
   component with unsupported profile and null pricing renders only its heading
   and internal profile string, hiding its evidence as well. The contract
   requires preservation and explicit validation, not an unexplained blank area.
   Test: `explains an unsupported persisted model instead of silently hiding its editor`.

All names above use the file prefix
`src/__tests__/v2/CommercialEditorIndependent.test.tsx` and describe block
`Independent commercial editor boundary checks`.

## Passing Controls and Limits

Seven profile cases preserve exact strings, null costs, evidence, identities,
calendar weekdays/paid holiday, rate versions, milestone accounting references,
T&M estimate versus approved usage and hybrid FX/shared-cost fields while
editing Workstream. Policy binding refreshes without mutating source props.
Finance cannot edit calendar/hybrid controls; verified but unreleased contracts
are read-only. The actual `StaffingGmTab` key remounts correctly when SOW/GM
identity changes, so old draft evidence is not carried to the next source.

S21-15: **missing** as accepted UI behavior; first-assignment failures remain.
S21-17: **missing**; hybrid pending state and preview authority labels fail.
S21-18: **missing**; MSP correction/unsupported-term gaps and full lifecycle
proof remain. T15/all-seven upload, extract, edit, save/reload, approve, sign and
handoff are not closed by these component tests. No new calendar arithmetic,
FX economics, child-floor outcome, backend authorization, visual layout or
stale HTTP response acceptance was performed. Lead fixes and independent
rerun remain required; this worker does not approve its own fixes.

## Independent Fix Rerun

2 October 2026, 05:54-05:56 UTC; bounded 10-minute allocation, finished early.
Reviewed and tested `1815dbe50aade6a7a7ee952882d9da5411269e49`, the lead's
cherry-pick of worker fix `08bceb2`. Diff against integration revision
`5ccabf6bffce787e61d06429978762eb331ce565` is empty for all five corrected
production files. Worktree was clean at entry. No production or test edits
were made during this rerun, and all three test files are unchanged from the
original QA commit `4057138824c239c221df8114357c0e9ab56921d3`.

The exact combined command documented above returned **40 passed, 0 failed,
0 skipped, 0 xfailed**, in **29.84 seconds**. Breakdown: independent 19/19,
existing model editor 9/9, existing profiles 12/12. No retry configuration or
failed-case retry was used. `npm run typecheck` exited 0.

All five findings are **fixed and tested** at the component boundary:

1. Hybrid pending changes use component identity and clear when that component
   is removed, preventing accidental sibling pricing replacement.
2. Saved, preview and stale-preview labels now remain distinct after edits.
3. Fixed/MSP profiles expose the first cost-calendar assignment control at
   both root and child renderers; the original two root assertions pass.
4. Structured MSP adjustment/usage editors preserve typed fields and source
   IDs while allowing credit and overage-rate correction. Both original
   correction assertions and the seven-profile preservation checks pass.
5. Unsupported profiles display an explicit validation alert and their source
   evidence without enabling preview or save.

No residual or new defect was found in this bounded source review and exact
rerun. No new regression test was necessary. Runtime remained this worktree's
own Node dependencies/test process; no API, DB, browser or cloud access.
S21-15, S21-17 and S21-18 remain **missing** as fully accepted requirements:
these five local fixes do not replace the outstanding T13/T15/T16 financial,
real-upload/lifecycle, browser or staging evidence. This rerun supersedes the
earlier outstanding-fix statements only, not its acceptance limitations.
