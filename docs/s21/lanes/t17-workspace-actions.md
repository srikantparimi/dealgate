# T17 Workspace Actions And Ownership

## Current Verification

Lead multipart endpoint/client wrapper: focused session62512 passed10 tests;
artifact `../evidence/baseline/t17-signed-file.xml`. Canonical invited owner,
SHA256 of received bytes, explicit attestation, MIME/empty/size/role/stale
rejection, storage502 with no execution row, and owner transfer during body read
are covered. Real PostgreSQL lock-wait/fixture-expiry races and real S3 browser
upload remain unverified. Worker UI aa2e2b6 passed13 component tests; integrated
typecheck and browser not yet run. No T17 closure.

History:97197 seven404 failures (missing endpoint);22481 sixpass/onefail exposed
build_key does not validate MIME, fixed explicit pre-storage allowlist;
20607 ninepass before ownership-race test;62512 tenpass after authority refresh.

## Contract

Existing API contracts, not new signature/business policy. Lead found two
connected-workflow defects: SignatureTab has a Send button without a handler;
HandoffTab infers notifications, acceptance, billing and renewal from released_at.

Worker owns only SignatureTab.tsx, HandoffTab.tsx, a new local SignedSowActions.tsx
if needed, SowWorkspace.tsx callback plumbing, and focused new tests/report.
Lead owns fixture/runtime/browser and integrations. Separate branch/worktree,
one heavy test at a time. No worker deployment/provider/DB operations.

Read-only AWS47499 confirms no bucketCORS; Terraform storage comments explicitly
choose server-mediated uploads. Lead therefore owns a new bounded multipart
signed-sow/{package_id}/file route and additive api/client.ts helper
uploadSignedSowFile(packageId,file,hasSignatureEvidence):Promise<SignedSowUpload>.
Follow existing /sows/upload architecture, real S3 server PUT and SHA256 of received
bytes; no CORS change/browser proxy/fake upload success. Worker uses this helper
then existing verify API. Validate owner, fixture scope, ready/current approvals,
MIME, empty/oversize and signature evidence before storage writes. Identity sync
releases audit locks before package lock. Existing presigned contract remains.
Require explicit signature-evidence attestation; expose rejected/unsigned/
mismatched/declined/expired status honestly. Do not invent an e-sign Send API.
Exact approved package and source version remain visible and immutable; existing
owner/SystemAdmin writer rules and server gates remain authoritative.

Handoff uses getHandoffGate/getDeliveryAcceptance/recordDeliveryAcceptance and
releaseSignedSow. Delivery/SystemAdmin acceptance checks are explicit booleans,
not defaults inferred from release. Distinguish accepted, verified, released and
actual notification outcomes. Link real handoff detail for distribution receipts;
do not say Notified/Configured/Acknowledged based only on release. Use existing
backend release gate and reasons; no new NDA/MSA gate. Preserve role and stale
package checks. Reload parent workspace after mutations with route-safe callback;
late old-route responses cannot update current state.

Tests first: demonstrate missing actions/false acknowledgement; actual API wrapper
requests, stored hash/headers, role-denied visibility, failure/retry, superseded
package, missing approval/signature/acceptance gates and route-change safety.
Unit transport stubs are boundary tests only; lead's real browser/storage/provider
journey is required before T17 closure. No scenario/parent completion inferred.
