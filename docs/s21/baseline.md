# S21 Baseline

Inspected 2026-10-01 23:38-23:57 UTC. This is evidence, not a completion claim.

## Source Provenance

- Integration: `feat/s21-forecast` in `/Users/srikanthparimi/OfficeApp/dealgate-s21-forecast`.
- Explicit base: `321b365393171837ccfe364def2b13ae5a72c06d`.
- Local main, origin/main, actual remote main and `s20-release` resolve to that SHA (`git ls-remote origin refs/heads/main refs/tags/s20-release`).
- Retained `integrate/s20`: `33c38a09c1ae0f58bdf61814cbd18f2a6126ba98`. `git diff --stat <base> <integrate/s20>` is empty: no unmerged tree delta to copy.
- S20 was already squash-merged. The downloaded handoff's `8b5100c`/rev-67/not-merged snapshot is stale; its original is preserved unchanged.
- No ancestor or repository AGENTS.md found. Read CLAUDE.md, blueprint/build-guide, S15 integrity, S17 document/deletion, S19 pipeline, S20 scoreboard/tests/decisions/release and deploy-smoke/runbook.

## Preserved Checkouts

| Checkout | Branch / head | Dirty state at inspection |
| --- | --- | --- |
| dealgate | main / 321b365 | Six modified docs/reports/s19-1 PNGs: clients-view, expanded-client, opportunities-view, stage-strip, summary-bar, sync-banner |
| dealgate-s20-W1 | s20/W1 / d56265f | api/app/services/hubspot_intake.py; worker/hubspot_intake.py |
| dealgate-s20-W2 | s20/W2 / 8d94ef4 | App.tsx, api/client.ts, v2/Pipeline.tsx; untracked reconciliation/URL tests, v2 client/deal pages and node_modules |
| dealgate-s20-W3 | s20/W3 / 9dd3f35 | Clean |
| dealgate-s20-W4 | feat/s20-w4 / 1f05090 | Untracked api/.venv and web/node_modules |
| dealgate-s20-W5 | s20/W5 / 423eeb0 | Clean |
| dealgate-s20-W6 | s20/W6 / 4f0363f | Clean |
| dealgate-s20-W7 | feat/s20-w7 / 8b42c81 | Clean |

None is edited, reset, removed or used as mutable runtime state by S21.

## Runtime Evidence

- AWS authenticated account `669810405473`, region `us-east-2`.
- Site: https://app.dealgateapp.com. Cluster `officeapp-dev-cluster`; API service `officeapp-dev-api`.
- Read-only describe-services: ACTIVE, desired/running 1/1, pending 0, rollout COMPLETED; task definition `officeapp-dev-api:70`.
- Running task `2454dc792dd64a8e92ecad6edf468dc7`: image `669810405473.dkr.ecr.us-east-2.amazonaws.com/officeapp-dev-api:s20-27e2edec`, digest `sha256:d1d19897a16f7400d2f92153b9d0f27b3ee627e11838fa159d4f110fa13ad10b`.
- Task started 2026-10-01 23:09:07 UTC; ECS container health UNKNOWN, not asserted healthy from that field. Service stability and HTTP smoke are distinct evidence.
- list-services returns API only: no deployed continuous ECS consumer service observed.
- Immutable UI/worker/schema alignment is NOT yet proved. Reported migration head `20260930_0047_w6_watch` is historical until independently checked.
- `gh run list` failed with authentication required. Git remote reads and AWS reads work. No blind deploy restart or main remerge attempted.
- **Final main-image smoke is not verified.** Current running tag names the pre-merge S20 image; no main-SHA manifest or completed background poll was found in committed reports.

## Executed Baseline Check

Command: `bash scripts/deploy-smoke.sh`, from this worktree, check-only (no deployment), against the site above. Run `smoke 20261001T234918Z`; exit 1. [Complete sanitized log](evidence/baseline/check-only-smoke.log).

Upload and client selection completed; confirmation `extract_status=manual_required`, expected `complete`. No retry used to overwrite this failure. Cleanup deleted this run's client `cd451fdb-42fe-4fee-9120-bb5b57871964`. Existing gate reported zero test-tagged clients and zero test approvers on active real SOWs. Gate limitations: first-page-only lists, name-based provenance and error-to-zero fallback; this is not complete S21-07/CO-09 containment evidence. Lead must replace those weaknesses and inspect actual cycle history separately.

At the initial baseline, full pytest had not run. Subsequent local execution and its failures are recorded in implementation-log.md. Full scoped browser projects, actual worker/storage journey and representative backup/restore rehearsal remain unexecuted. Historical isolated passes/retries do not close S20 failures.

## Worker and Frontend Read-Only Manifest

Observed 2026-10-02 00:26:11 UTC. All six EventBridge rules are enabled; this proves configuration, not successful processing. The alert-scheduler, audit-export, notification-sender and renewals-scheduler target their respective task-definition revision 5 using image `officeapp-dev-api:s14a.3b-workers-creds-fix`. HubSpot intake and reconcile target their respective revision 3 using image `officeapp-dev-api:s19-1-fbee5b8`. These are not aligned with API revision 70 or verified main `321b365`.

Frontend S3 index last-modified 2026-10-01 22:57:21 UTC, ETag c7d3d18767ab72da478cbba3b215242a, SHA-256 `8ced45cd4111b684ab6a3988329ce54390368d0bdfffabb629018361b870f066`. Hash alone does not attribute frontend source SHA. Deployed database schema remains independently unobserved.

Local lead-only Postgres (`dealgate-s21-lead-db`, loopback 55421, database s21_lead) successfully migrated an empty database through all baseline revisions to `20260930_0047_w6_watch`; PostgreSQL audit immutability and migration parity checks passed 4/4. No S21 migration yet and no representative backup/restore evidence claimed.

## Hashes

| Artifact | SHA-256 |
| --- | --- |
| web/package-lock.json | 05061bfa72d7a0534481776a52c8b008062b38f7c8a9a11a3267f5bf276dbf4f |
| tests/e2e/package-lock.json | c776011bd7630f2e5b518e859a9779f8f95937bb40d804dbfa562cb3e2a52fd8 |
| infra-tf/bootstrap/.terraform.lock.hcl | 79cf84eced1c340866bbf2fc657200864bbece80b73a547e3e3d5b2613f6e679 |
| Source DOCX | 2cafe8b3a1e8eba2b6a5fbe442fd1467b8af3093d0c9d297b44a55be96f622d6 |
| Source HTML | b1ecf60f2920d8cac88c3c1a1f5779e4c656d2dba89256ddfdd9d6bb62c0ef6b |
| Source S20 handoff | 8065764136fb1cc237074cec6b0f8db07bafba29127150be57fef360510805ff |

API has no committed dependency lockfile: reproducibility risk, do not invent a hash. Each lane uses its own venv and dependency capture.
