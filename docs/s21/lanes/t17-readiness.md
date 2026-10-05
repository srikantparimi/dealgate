# T17 Readiness Explanations

Branch `s21/t17-readiness-explanations`, baseline
`f74df880e8b1a718e0544accb8f9e1d32730d77c`, isolated worktree
`/Users/srikanthparimi/OfficeApp/dealgate-s21-agreement-ui`.

Ownership: `web/src/pages/v2/sow-workspace/readiness.ts`, existing focused
`web/src/__tests__/v2/ApprovalReadiness.test.ts`, this report. No shell, backend,
shared types or other worker files edited.

Added tests first for named scope/GM responsibility, concrete missing model
inputs, review feedback with assignment, pending signature verification, literal
server verification blockers, foreign-package signature rejection, acceptance
unavailability after release, and actual acceptance/gate-driven handoff guidance.
Labels distinguish absent response data from known incomplete data. NDA/MSA
remains a nonblocking uploader note; no additional business gate was introduced.

Names use existing owner/assignment fields only, falling back to an explicit
role plus unavailable-name label. Delivery acceptance DTO has only accepted_by
UUID, not an actor display name: readiness labels the responsible Delivery role,
never presents a UUID as a person's name or infers a particular accepter.

## Required Integration

Lead owns `dataLoader.ts` wiring to existing endpoints for the current package:

- `handoffGate?: HandoffGate | null` from `getHandoffGate(packageId)`.
- `deliveryAcceptance?: DeliveryAcceptance | null` from
  `getDeliveryAcceptance(packageId)`.

Leave unavailable/failed calls undefined; reset on package change. Null acceptance
with a successfully loaded gate indicates no recorded acceptance. Non-null
acceptance is accepted only if its package_id matches the selected package.
Released state alone never manufactures acceptance, notifications or billing.

## Verification

Focused run28000 passed all19 cases after run35449 exposed one null signed-upload
dereference (18 passed, 1 failed) and the optional access was corrected. Commands
run in the isolated `web` directory:

```sh
./node_modules/.bin/vitest run src/__tests__/v2/ApprovalReadiness.test.ts
./node_modules/.bin/tsc --noEmit
```

Initial TypeScript run71184 identified an inherited unsupported `exact` option in
AgreementVersions.test.tsx from base5c1f97f; lead fixed that independently in
integration commit a5b2d9f and it is carried here as0f26d3c. Final TypeScript
run95736 exited0. No runtime, provider, database or browser operation performed by this task.
The original T17 browser assertion of all gate/owner/reason/action labels remains
lead-owned; this implementation is not independent staging proof.
