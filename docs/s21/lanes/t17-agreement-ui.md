# T17 Shared Agreement Presence And Versions

Worker branch `s21/t17-agreement-ui`, base `ecca40a`, isolated worktree
`/Users/srikanthparimi/OfficeApp/dealgate-s21-agreement-ui`.

UI-only ownership: shared ClientAgreementPresence, ClientDetail, DealDetail,
DocumentsTab, AgreementsRegister, agreements API block and focused new tests.
Lead owns immutable version storage, authorization, migration and lifecycle.

Shared client-scoped indicators show NDA/MSA document counts as "on file", not
signed or legally cleared. A failed request never becomes "not on file".
Multiple files per kind remain separate. Upload/view links preserve client and
kind. Route changes remount scoped content and discard stale responses. Legal
and SystemAdmin receive mutation controls; read-only actors retain visibility.
Register history identifies revision, filename, uploader and upload date, and
downloads the selected immutable revision. Replacement uses expected_version;
conflicts preserve the selected file and require explicit reload before adopting
the new latest version. No agreement readiness or signature gate was added.

Deletion uses the backend's durable 202 receipt. The register distinguishes
active-record removal from pending/failed/completed file cleanup, retains a job
link, and provides explicit status refresh and authorized retry. Confirmation
includes every version; it does not promise immediate physical file removal.
The one shared subject_type union line was additionally authorized by lead;
lead separately owns the agreement label on the existing deletion job page.

## Verification

Tests authored before implementation; execution held until lead granted slot.
Private APFS node_modules clone completed; no install or shared generated writes.
First focused run: 7 passed / 1 failed (test clicked disabled Save before history
resolved). Added an explicit enabled-control assertion before clicking. Second
run: 8 passed in 11.93s; initial typecheck passed. With durable cleanup added,
9 passed in 6.65s. The subsequent typecheck found the new test-only cleanup
fixture omitted mandatory response fields; those fields were supplied faithfully.
Final typecheck completed with exit 0. No active worker processes remain.

Commands in own `web` directory:

```sh
./node_modules/.bin/vitest run src/__tests__/v2/ClientAgreementPresence.test.tsx src/__tests__/v2/AgreementVersions.test.tsx
./node_modules/.bin/tsc --noEmit
```

Unit transport stubs are component tests only, not real API/provider acceptance.
Lead owns connected four-surface upload/replace/download/role proof and staging.

## Read-only Register Follow-up

Read-only review found Marketing can read agreement endpoints but cannot read
the client directory. The register previously required both requests to succeed.
The follow-up fetches client choices and an off-page selected client only for
Legal/SystemAdmin upload controls. A new Marketing case asserts visible document,
history and download controls without any client-directory request or mutation
controls. Authored before implementation; once the slot was granted, the focused
AgreementVersions suite passed all 6 cases in 10.23s. No broad UI suite was run.
Follow-up TypeScript check passed with exit 0.
