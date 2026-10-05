# Extraction Conflict Draft Binding

Isolated branch `s21/conflict-draft-invalidation`, baseline `1b9c7b6`. Ownership:
`ExtractionConflicts.tsx`, its existing focused test file and this report only.
Addresses independent extraction QA finding 4; backend findings remain separate.

## Behavior

Each field draft now carries the exact review token its choice and reason were
written against. Incoming GET and successful POST responses retain a draft
only when both its field and exact token remain present. Changed tokens and
removed fields discard that draft. An unchanged sibling token keeps its draft,
including after an explicit reload. A version change resets all drafts even if
a test/damaged source returns the same opaque token in another version.

Rendering and the submit handler both require a matching draft token; stale or
missing drafts cannot POST merely because a new field item is displayed. A
stale 409 does not reconcile anything: its existing choice/reason/error remain
available until explicit review/reload, preserving previous behavior.

## Test Authorship

Four regressions were added before production changes. They cover saving A
while B receives a new candidate/token, rejecting B submission until a fresh
decision/reason; retaining unchanged B; discarding removed B even if its token
later reappears; and preserving unchanged reload drafts but resetting a new
version. The existing three tests and their stale-error assertions are retained.

Implementation proceeded during the serialized backend runtime, without any
worker runtime. After the lead granted the slot, the original component was
temporarily restored through apply_patch in this isolated tree. The unchanged
seven-test suite reproduced two failures (changed sibling token retaining its
decision, unchanged-token reload dropping its draft) and five passes in 17.71s.
Restoring the fix made the same seven tests pass in 6.13s.

Command: `npm exec -- vitest run src/__tests__/v2/ExtractionConflicts.test.tsx --maxWorkers=1 --minWorkers=1`.
Sequential `npm exec -- tsc --noEmit` completed with exit 0. Runtime slot released.
Dependencies were privately APFS-cloned after checking 17 GiB free; no shared
node_modules writes or installation. Unit transport mocks are not backend,
concurrency or staging proof.
