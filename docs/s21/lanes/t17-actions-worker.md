# T17 Workspace Actions Worker

Branch s21/t17-workspace-actions, base0a82da7479a76146498e957f41536c7cf485ef08,
isolated dealgate-s21-actual-coverage tree. Prior8d9f0ab branch preserved.
Owned SignatureTab, HandoffTab, new SignedSowActions, SowWorkspace callback
plumbing, focused WorkspaceExecutionActions test and this report only.

Replaced handlerless Send-for-signature control with explicit attested file
upload and independent verification. Uses lead-owned uploadSignedSowFile helper
(multipart server-mediated actual storage/hash); no browser S3 proxy or CORS
change. Preserves owner/SystemAdmin writes, current package/SOW-version checks,
all returned verification/signatory status and errors. File/attestation survive
failure for deliberate retry. Package/status/source-keyed child lifetime prevents
late old-route mutations from refreshing a new workspace.

Handoff now loads actual gate and DeliveryAcceptance records. Only Delivery or
SystemAdmin can confirm staffing/billing/PO explicitly; only owner/SystemAdmin
can release and only with server gate ok. Shows server reasons and fetch failures,
allows explicit reload, and links actual distribution detail. Released timestamp
no longer fabricates Notified/Acknowledged/Configured/renewal-created claims.
No agreement gate introduced. Parent route-safe refresh passed into both tabs.

## Verification

Tests authored before implementation while lead held runtime. No initial
pre-implementation execution claimed. Private node_modules APFS clone93161:
an early launch39569 before copy completed failed to resolve @vitest/utils,
collected no tests. Waited for clone completion, no shared generated writes.

First focused run32039:9 passed/4 failed due shared accessible name between
Executed document region and file input. Renamed region only; kept exact input
label and all substantive assertions. Corrected run49212: **13 passed**,15.65s.

```sh
# In this worktree's web directory
./node_modules/.bin/vitest run src/__tests__/v2/WorkspaceExecutionActions.test.tsx
```

Cases cover attestation/upload/verify, error-preserving retry, unauthorized and
superseded package controls, old-route upload completion, truthful released status,
explicit acceptance and gate-driven release, blocked/unsigned/declined/expired
states, role split, gate failure/reload and late old-package gate response.
Only unit boundary mocks; no connected/storage/provider/browser completion claim.

Typecheck deferred to lead integration with its new client helper (not present
on worker base). Runtime released after focused result. Lead owns backend
multipart bounds/hash/storage tests, typed integration, full connected browser
and all eight remaining T17 conditions. No deployment/DB/provider work here.
