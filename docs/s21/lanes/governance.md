# Commercial Editor Increment

Owner: `s21/governance`, isolated worktree `dealgate-s21-governance`.
Lead retains integration, backend, migrations, runtime and deployment ownership.

Partial S21-17/18 and S21F:T15: fixed-assignment and recurring-MSP editors use
the existing commercial preview/version APIs. Other profiles display persisted
monthly schedules recursively and cannot be overwritten by this editor.
Existing MSP usage/adjustments, staffing and evidence survive edits unchanged.
Restricted readers do not fall through to legacy resource editing.

Manual fields are necessary only when confirmed SOW evidence does not define
the workstream, calendar timezone, allocation basis/weights, currency minor
unit or cost model. These stay blank/unconfirmed rather than inventing hours,
costs or currencies. Billing basis does not stand in for billing cadence.
Source term/price/currency values prefill only from
confirmed extraction with valid input representation. Existing canonical
inputs prefill exactly. A written change reason accompanies every save.

Tests authored before implementation: initial run failed collection because
the new API/editor modules did not exist. Unit API responses are test doubles,
not acceptance evidence. Own `npm ci` installed 304 packages; no shared runtime
or staging resources were modified. Real browser verification belongs to lead.

Local verification: `npx vitest run
src/__tests__/v2/CommercialModelEditor.test.tsx
src/__tests__/v2/SowWorkspace.test.tsx` passed 14 tests (8 new, 6 existing),
zero skips/retries. `npx tsc --noEmit` and `git diff --check` passed. The suite
covers optimistic saves, exact string amounts, source retention, stale-save
preservation, role-disabled inputs, read-only hybrid, unknown cost handling,
MSP usage preservation, confirmed prefill and redacted commercial tab behavior.

Remaining scope: editors for calendar staffing/T&M/milestone/unit/hybrid,
MSP usage/adjustment editing, every-profile upload/approve/sign/handoff journeys,
dated amendment activation, visual/browser and staging verification. This
increment does not close T15 or any full release requirement.
