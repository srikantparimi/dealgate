# T17 Agreement Scope And Presence

## Current Evidence

2026-10-03, integration610cc9f. Independent QA found missing DG05 implementation:
no replacement/version lineage, no shared Client/Deal/SOW presence marks, and
role-only agreement endpoints without authoritative fixture isolation. Upload/view
and upload/delete audits exist; actual approvals/release with zero agreements passed
49137 on6ad2171. That does not prove four-surface presence/replacement semantics.
Do not upload fixture agreement files before scope guards pass focused tests.

Lead owns agreements.py, new agreement fixture-access tests and subsequent version/
presence integration. Governance separately owns clients.py and new client-scope
tests; no overlap. Single heavy test slot. No migration or provider operation started.

Focused access test history:10717 failed setup using wrong dev-seed environment
name; corrected to ALLOW_DEV_SEED_ENDPOINT.87860 failed setup because local auth
reads DEALGATE_TEST_GROUPS, not seeded row groups; corrected actor-specific local
header environment. Neither failure is evidence of the production scope defect.
61019 is the correctly configured regression: failed because the test administrator
received both ordinary and issued-fixture documents. Scope guard repair authored;
not yet verified. Governance currently holds the single heavy test slot.

## Required Repair

Preserve real-business role permissions. Resolve canonical persisted identity and
apply existing account_scope/user_allowed to list, upload, download and delete;
deny before signing URLs or writing storage. Lists must not reveal fixture names.
Replacement needs immutable lineage/version, stale-version rejection and same-
transaction audit. Preserve legacy multiple documents rather than collapsing them.
One client-scoped UI presence component across four surfaces must call presence
"on file", not "signed" or legal clearance. Client ownership survives SOW deletion.
No approval/signature gate is introduced. Full DG05 remains partial.

## Replacement Contract Under Independent Review

Keep existing Agreement IDs and multiple independent files per kind. Add a separate
immutable AgreementFileVersion row for each stored revision, with unique
(agreement_id,version_no), file key/name/size, SHA256, uploader and timestamp.
Current Agreement metadata/version remains the compatible latest pointer.
Migration0063 will backfill legacy rows as v1; unknown legacy SHA256 stays null,
never fabricated. No migration authored/applied yet. New uploads store measured hashes.

POST /agreements/{id}/replace takes file and expected_version. Lock Client then
Agreement; scope/role/stale checks before storage, recheck after body reading.
Append version/current-pointer update/audit in one DB transaction. Return409 for a
stale expected version, preserve previous bytes and all prior versions. GET history
and version download use the same account authorization, not public file keys.

Lifecycle integration is mandatory: parent client deletion gathers all version keys;
direct agreement deletion handles every revision; storage reference guard includes
revision keys; trusted fixture cleanup checks every historical uploader, not just
latest metadata. SOW deletion does not remove this client-owned history. Post-PUT
registration failure/orphan recovery must remain explicit rather than false success.
Lead owns migration/model/API/lifecycle; separate UI worker only after contract fixed.
Independent QA accepted this design, with mandatory direct-delete durable cleanup
through existing DeletionJob processing (no storage deletion before DB commit),
Client -> Agreement locks for every mutation, historical-uploader fixture checks,
positive/unique version constraints and downgrade refusal after replacements.
Existing root-based Pipeline counts must not change. Client audit visibility needs
agreement IDs; coordinate with the client-scope worker before editing that router.

## Migration Release Boundary

0063 is NOT rolling-writer compatible. Its history FK makes old root-only deletes
fail after their precommit S3 deletion. Quiesce/drain every old agreement writer
before applying0063, then resume only version-aware code; never run an old image
against0063. Local8211 must be stopped before migration. Staging requires an exact
coordinated release and existing infrastructure approvals, not an ad hoc deployment.
QA also found parent client deletion could retain an identity audit lock while
waiting for Client, deadlocking a replacement's audit. Lead added the existing
identity-commit-before-business-lock pattern to that endpoint; PG race proof pending.

## Separate Current Isolation Failure

Read-only browser17523 at610cc9f passed owner route/count/eight-tab/reload/Back and
header geometry assertions, then failed: normal non-test SystemAdmin receives
fixture11ceb7d9-1693-49e8-9ab1-596a5d6e5941 from GET /clients?size=200.
Trace/screenshot: ../evidence/baseline/t17-route-isolation-failure-17523/.
Worker repairs client boundaries; no broad browser rerun until focused checks pass.
