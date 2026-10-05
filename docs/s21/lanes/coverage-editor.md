# Staffing Coverage Editor

Isolated branch `s21/coverage-editor`, baseline `d21eb08`. Owned new
`web/src/api/people-coverage.ts`, `web/src/components/CoverageEditor.tsx`, focused
tests and this report. Existing component-directory convention is retained.
No shared client/types, parent page, backend, migrations or deployment changes.

## Integration Contract

Named export `CoverageEditor({ plan, available, onSaved })`, where plan and
available use existing `DemandSource`, and `onSaved` may return a Promise.
Delivery/SystemAdmin write; other demand-read roles inspect current/history.
Unsupported roles are rejected before requesting coverage.

Actual GET/POST `/people/demand/coverage` helpers use the final committed HTTP
contract. Initial props supply source facts. Explicit reload also GETs
`/people/demand` to refresh both publication versions alongside mapping CAS,
preserving typed mappings/reason after conflict. Current mappings are loaded
across pages; immutable history has independent page and revision selection.
History selection never changes the current expected mapping version.

Only published project-kind sources from the plan's account appear as options.
New rows prefill a matching source line and confirmed date intersection. First
slot positions are one-based on screen and zero-based on the wire. Count stays
blank until explicitly confirmed: conversion count cannot be derived from a
financial fraction or inferred from two unrelated staffing totals. This is
the written justification for manual mapping inputs. Multiple rows express
nonconsecutive slots and partial dates; saved nonconsecutive arrays are split
into faithful consecutive runs for editing, not silently filled in.

Slots, counts and dates remain explicit cost-free inputs; server capability,
continuity, trusted-scope and concurrency checks remain authoritative. Existing
source facts and role labels are reused, never naked UUID names. Missing former
line keys remain Unavailable previous line. Versioned clear sends an empty
mapping array with current CAS and a written reason, never a deletion request.
Unchanged retry payloads preserve request keys. Late history responses from an
old project are ignored. All labels use explicit separated `htmlFor`/`useId`
bindings. Forms/tables are responsive and unframed.

## Verification

Nine substantive tests were authored first, then implementation while the
serialized backend runtime was occupied. No pre-implementation red execution
is claimed. Cases cover current source prefill, one-based/zero-based conversion,
nonconsecutive arrays, current CAS versus selected historical version, source
and mapping conflict reload, explicit clear, read-only HR, unsupported-role
guard and a late previous-project history response.

The first focused run passed all nine cases. Strengthening the conflict oracle
to rerender with new object copies of old props then reproduced a real defect:
freshly reloaded publication CAS was overwritten by referential prop changes.
The named targeted run failed that case (eight others not selected). The source
basis effect now keys on immutable source-version identity instead. Typecheck
also caught an incomplete denied-role fixture; it now supplies the full
`MeResponse` shape without changing any assertions. Final full focused run:
**9 passed in 21.03s**, no skipped test declarations or retries. Final
`tsc --noEmit` and staged diff whitespace checks passed. Runtime slot released;
all processes finished.

Only a private APFS clone of integration node_modules is used; no shared
symlink, install, server or browser runtime. Transport mocks are unit isolation,
not acceptance. Commands:

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-coverage-editor/web
npm exec -- vitest run src/__tests__/v2/CoverageEditor.test.tsx --maxWorkers=1 --minWorkers=1
npm exec -- tsc --noEmit
```

Parent ResourceDemand wiring, backend/schema, real application browser proof,
responsive screenshots and staging remain integration-lead work. This component
does not establish FC-05/07 or conversion acceptance completion.
