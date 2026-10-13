# S22 · staging deploy record (phase 2)

## Candidate

| Item | Value |
| --- | --- |
| Branch / commit | `feat/s22` @ `520f5174` (docs(s22): phase 1 CODE COMPLETE) — later test-only commits do not change the image |
| Image | `669810405473.dkr.ecr.us-east-2.amazonaws.com/officeapp-dev-api:s22-520f5174` |
| Digest | `sha256:5d35069925329ca4fe1480eee6f123c97c98bb5dd34adee3d1e026ac0a6e941f` · 104,941,709 bytes · linux/amd64 · built from repo root with `api/Dockerfile` (bundles `worker/`) |
| SPA | `web/dist` built from the same commit with the checked-in `.env.production` (Cognito vars unset in the shell) |
| Migration | `20261012_0065_portfolio_forecast` (new tables only, backward-compatible; seeds the calendar) |

## Terraform plan (whole root, reviewed, saved)

Inputs are exactly the inputs of the last two sanctioned plans (`/tmp/s22-main-47114a7d.plan.json`, `/tmp/s22-managed-c9ed169.plan.json`) with only `image_tag` changed:
`env=dev region=us-east-2 image_tag=s22-520f5174 production_approver_identities_enabled=true s21_jobs_enabled=true reporting_timezone=America/Los_Angeles reporting_currency=USD allowed_account_ids=["669810405473"]` and defaults for the rest (`hubspot_continuous_enabled=false`, `operational_hardening_enabled=false`, `trusted_cleanup_enabled=false`).

```
terraform -chdir=infra-tf plan -input=false -lock-timeout=60s \
  -var image_tag=s22-520f5174 -var production_approver_identities_enabled=true \
  -var s21_jobs_enabled=true -var reporting_timezone=America/Los_Angeles \
  -var reporting_currency=USD -var 'allowed_account_ids=["669810405473"]' \
  -out=/tmp/s22-520f5174.tfplan
```

| Artefact | SHA-256 |
| --- | --- |
| `/tmp/s22-520f5174.tfplan` | `c9ffd82001d56a3401659ce1e24efcf61ec8aee6e41cca19979a454b72b339eb` |
| `/tmp/s22-520f5174.plan.txt` | `a2787b31b08f04cda1397590226497be4deae487d462e32d6e169e66c64a21b3` |
| `/tmp/s22-520f5174.plan.json` | `01445622cfa4d2cd98b3d4e0bbb65934a80f17e6287b921ed18c6df39aa192c1` |

**Plan: 14 to add, 13 to change, 11 to destroy** — the previous sanctioned shape (11 / 13 / 11) plus the three new portfolio-scheduler resources. Every action, from `plan.txt`:

- replaced (image only): `module.api.aws_ecs_task_definition.api`, `.migrate`, `module.api.terraform_data.api_migration`, and the eight scheduled-worker task definitions (`alert_scheduler`, `notification_sender`, `renewals_scheduler`, `audit_export`, `hubspot_intake`, `hubspot_reconcile`, `s21_job["forecast_plans"]`, `s21_job["deletion_cleanup"]`);
- updated in place: `module.api.aws_ecs_service.api` (new revision), eight EventBridge targets, four `events_runtask*` / `events_s21_jobs` IAM policies (new task-def ARNs);
- **created**: `module.schedulers.aws_ecs_task_definition.portfolio_scheduler`, `aws_cloudwatch_event_rule.portfolio_scheduler` (`cron(0 6 * * ? *)`), `aws_cloudwatch_event_target.portfolio_scheduler`;
- zero RDS, S3, Cognito, SES, secrets, KMS, network, security-group, CloudFront, DNS, production-approver or business-data changes.

## Required human action (rule 15 · D5 as amended by S21F-02)

Approve only the saved plan identified above. Exact apply command:

```
cd /Users/srikanthparimi/OfficeApp/dealgate-s22 && env AWS_PROFILE=lm-arbiter-poc AWS_REGION=us-east-2 \
  terraform -chdir=infra-tf apply /tmp/s22-520f5174.tfplan
```

After the apply: migration task exit 0 (alembic head `20261012_0065_portfolio_forecast`), API service stable on the digest above, publish `web/dist` (index no-cache, assets immutable) + CloudFront invalidation, `scripts/deploy-smoke.sh`, then the S22 specs on staging:

```
cd tests/e2e && E2E_BASE_URL=https://app.dealgateapp.com npx playwright test specs/s22/s22-p1-contract.spec.ts specs/s22/s22-p2-owner-path.spec.ts
AWS_PROFILE=lm-arbiter-poc AWS_REGION=us-east-2 scripts/check-test-data-clean.sh
```

## Apply and roll (2026-10-12, Kanna approved the saved plan in chat: "ok approved run")

| Step | Result |
| --- | --- |
| `terraform -chdir=infra-tf apply /tmp/s22-520f5174.tfplan` (checksum verified first) | exit 0 · **Apply complete! Resources: 14 added, 13 changed, 11 destroyed** — exactly the plan |
| Migration (Terraform-owned `run-ecs-migration.sh`, task `0f1d0d3c29a74dcd816c6ea5f86a9455` on `officeapp-dev-api-migrate:35`) | succeeded, exit 0 (1 m 12 s) |
| API service | task-def `officeapp-dev-api:97`, `services-stable`, 1/1 running, single PRIMARY deployment; running task `74622525…4d5b` image `s22-520f5174`, digest `sha256:5d35069925329ca4fe1480eee6f123c97c98bb5dd34adee3d1e026ac0a6e941f` |
| New routes on staging | `/api/portfolio/forecast`, `/api/settings/forecast`, `/api/engagements`, `/api/resources`, `/api/portfolio/clients` (was `/api/clients/forecast-options`, shadowed — bug #6) → 401 unauthenticated (present, auth-gated); `/api/healthz` ok |
| Worker families on the image | alert-scheduler 49, notification-sender 49, renewals-scheduler 49, **portfolio-scheduler 1 (new)**, audit-export 49, hubspot-intake 48, hubspot-reconcile 48, forecast-plans 26, deletion-cleanup 26, api-migrate 35 — all `s22-520f5174` |
| Portfolio scheduler rule | `officeapp-dev-portfolio-scheduler` ENABLED, `cron(0 6 * * ? *)`, target `officeapp-dev-portfolio-scheduler:1` |
| Deploy smoke | `smoke 20261012T175338Z` GREEN (upload, extraction, confirmation, cleanup); `[gate] clean · 0 test-tagged clients + 0 e2e approvers` |
| SPA | `web/dist` from `8f644b2` synced: assets `public, max-age=31536000, immutable`, `index.html` `no-cache, must-revalidate`; CloudFront invalidation `I2LAB8BDPUPE4A1WAETC5F00F6` COMPLETED; served `index.html` → `assets/index-5R06pivF.js` (immutable, contains the Portfolio forecast navigation) |

Leak gate + nightly sweep now recognise the `S22 e2e ` tag (b108465; the worker half ships with the next image).

## Round 1 staging result and the leak it exposed

Both S22 specs passed on staging against `s22-520f5174` (`2 passed (55.8s)`), `scripts/check-test-data-clean.sh` read clean — but a token-based count found 2 engagements and 10 tagged people left behind: the e2e bot is a test identity under the S21 runtime isolation and could not delete a client it had created through the new `POST /clients` (bug #4). Staging was cleaned through the app's deletion service (one-off task `b2aeab40279e4238b4a8410e9502c2c5` on `officeapp-dev-api-migrate:35`, exit 0, audited as the bot; both deletion jobs `done`) and `DELETE /resources` × 10; the extended gate now reads `0 test-tagged clients + 0 e2e approvers + 0 tagged people + 0 tagged engagements`.

## Round 2 candidate (bugs #4 #5 #6)

| Item | Value |
| --- | --- |
| Commit | `feat/s22` @ `6259cda5` |
| Image | `officeapp-dev-api:s22-6259cda5` · digest `sha256:226582e71a86c67db607c848804dd11e8eaa1f687822e1a84b0a49e701863bfd` · 104,952,223 bytes · linux/amd64 |
| SPA | `web/dist` from `6259cda5` → `assets/index-Lv6YxA3F.js` (client options now read `/api/portfolio/clients`) |
| Migration | none new (head stays `20261012_0065_portfolio_forecast`; the migration task re-runs idempotently) |
| Plan | `/tmp/s22-6259cda5.tfplan` — **12 to add, 14 to change, 12 to destroy**: the twelve replacements are the image-only task definitions (api, migrate, the migration trigger, and all nine scheduled workers incl. `portfolio_scheduler`); the fourteen updates are the API service, nine EventBridge targets and four RunTask policies; zero creates; every container image moves `s22-520f5174` → `s22-6259cda5`; no other resource changes. Same inputs as round 1. |
| Checksums | tfplan `42514b9c40b5a6a248a98fd7c0d0044c77c990e3c17f444d3baddc4b6cd15ca6` · plan.txt `16ffbc37a6f62fbe27af6f2ab8678d255ed186a2e097404f7a2901a0299d5be6` · plan.json `1f1be3261844a35ea19700f16a90773bc0b8ff502d0c419237bae57b66303cf4` |
| Local proof | both specs pass through the fixture path (P2-6 now covers Setup & costs and the Portfolio page); web vitest 89 files / 551 tests; S22 + fixture-access pytest 38 passed |

Required human action: approve the round-2 plan. Exact apply command:

```
cd /Users/srikanthparimi/OfficeApp/dealgate-s22 && env AWS_PROFILE=lm-arbiter-poc AWS_REGION=us-east-2 terraform -chdir=infra-tf apply /tmp/s22-6259cda5.tfplan
```

## Round 2 apply and roll (2026-10-12, Kanna: "go ahead")

| Step | Result |
| --- | --- |
| `terraform -chdir=infra-tf apply /tmp/s22-6259cda5.tfplan` (checksum verified first) | exit 0 · **Apply complete! Resources: 12 added, 14 changed, 12 destroyed** — exactly the plan |
| Migration task `5e1c79be2c08400cb8cc44e18ac5f2e7` on `officeapp-dev-api-migrate:36` | succeeded, exit 0 (1 m 42 s); head unchanged `20261012_0065_portfolio_forecast` |
| API service | `officeapp-dev-api:98`, `services-stable`, 1/1, single PRIMARY; running task `b7f2605b…cc8c` on `s22-6259cda5`, digest `sha256:226582e71a86c67db607c848804dd11e8eaa1f687822e1a84b0a49e701863bfd` |
| Worker families | alert-scheduler 50, notification-sender 50, renewals-scheduler 50, portfolio-scheduler 2, audit-export 50, hubspot-intake 49, hubspot-reconcile 49, forecast-plans 27, deletion-cleanup 27, api-migrate 36 — all `s22-6259cda5` |
| Deploy smoke | `smoke 20261012T184432Z` GREEN; `[gate] clean · 0 test-tagged clients + 0 e2e approvers on real SOWs + 0 tagged people + 0 tagged engagements` |
| SPA | `assets/index-Lv6YxA3F.js` synced (immutable) + `index.html` (no-cache); CloudFront invalidation `I5IFA4Y8YXXMFZ4BDPMOST5VW7` COMPLETED; served bundle contains the `/portfolio/clients` call |

## Main image (post-merge, 2026-10-12, Kanna: "approved" → "apply")

| Step | Result |
| --- | --- |
| Merge | `feat/s22` @ c137ad7 squashed → `origin/main` = `576205c` (release worktree `dealgate-s22-release`, branch `release/s22-portfolio`); tree identical to the accepted staging build |
| Image | `officeapp-dev-api:s22main-576205c9` · digest `sha256:09e5078f8f932efbdf4b3e9c8d8f4cbc43d160892889e334955eff23576fb3a4` · 101,638,150 bytes · linux/amd64 (same code as `s22-6259cda5`; builds are not byte-reproducible) |
| Plan | `/tmp/s22main-576205c9.tfplan` SHA-256 `95ec582c1f760851b786d244594f2dadd5166f84e2de9dfb926ab9c16a32d01a` (plan.txt `d484e629…2478`, plan.json `deb3db21…dc74`) — 12 to add / 14 to change / 12 to destroy, image-only, same inputs |
| Apply | exit 0 · **Apply complete! Resources: 12 added, 14 changed, 12 destroyed** |
| Migration task | `007291ffcf804f85b168e36f5d92b6eb` on `officeapp-dev-api-migrate:37` succeeded (no-op at head `20261012_0065_portfolio_forecast`) |
| API service | `officeapp-dev-api:99`, `services-stable`, 1/1 PRIMARY; running task `8e301569…e412` on the digest above |
| Worker families | alert-scheduler 51, notification-sender 51, renewals-scheduler 51, portfolio-scheduler 3, audit-export 51, hubspot-intake 50, hubspot-reconcile 50, forecast-plans 28, deletion-cleanup 28, api-migrate 37 — all `s22main-576205c9` |
| SPA | built from `576205c` → the identical `assets/index-Lv6YxA3F.js`; synced with cache headers; CloudFront invalidation `ICXZAHO2Q8Q8QW3IJTKH1OL2VO` COMPLETED |
| Smoke | `smoke 20261012T201815Z` GREEN; gate clean |
| S22 specs on the main image | `2 passed (1.2m)`; gate clean after: 0 clients / 0 approvers / 0 people / 0 engagements |

Staging now runs the main image. Still owner-unverified: P2-4 from-deal pre-fill on a real Closed-Won deal; the first real nightly portfolio tick (06:00 UTC).

## S22-P4 candidate (2026-10-12, session S22-2)

Working rule for this round (Kanna): plan for Kanna to apply only if infrastructure changes; an image-only roll is applied by the session.

| Item | Value |
| --- | --- |
| Branch / commit | `feat/s22-p4` @ `68ff809d` (off `origin/main` 5124907) |
| Image | `officeapp-dev-api:s22p4-68ff809d` · digest `sha256:c846036816cf494da55985028a82fdf2a99c907bd46f7462bc73c6dd907cadea` · 104,456,505 bytes · linux/amd64 |
| SPA | `web/dist` → `assets/index-CwMcUryo.js` |
| Migration | none new (head `20261012_0065_portfolio_forecast`; migration task re-runs idempotently) |
| Plan | `/tmp/s22p4-68ff809d.tfplan` — **12 to add, 14 to change, 12 to destroy**, image-only: 11 `aws_ecs_task_definition` + the `terraform_data` migration trigger replaced; `aws_ecs_service` + 9 `aws_cloudwatch_event_target` + 4 `aws_iam_role_policy` updated; no creates or deletes of any other type; every image → `s22p4-68ff809d`; same inputs as every previous plan |
| Checksums | tfplan `d072a200682a39484e3f969d1d457629241b691f9f9ce2c2dfab0c927f129c2c` · plan.txt `d22cb523b563eac908bf2595cd38a2f453c338abe032512642c667d981ae7fa0` · plan.json `d357e77411fe145aece2733bf008b966b53d68aa4358f89a8781d5195d366a4c` |
| Local proof | 22 forecast tests; S22 pytest incl. 4 workbook-import tests; web vitest 89 files / 556 tests; Playwright `s22-p4-upload` (2), `s22-p1-contract`, `s22-p2-owner-path` all pass on the local stack, teardown clean |

## S22-P4 apply and roll (2026-10-12, image-only, applied by the session per the round's rule)

| Step | Result |
| --- | --- |
| `terraform -chdir=infra-tf apply /tmp/s22p4-68ff809d.tfplan` (checksum verified first) | exit 0 · **Apply complete! Resources: 12 added, 14 changed, 12 destroyed** — exactly the plan |
| Migration task `ec522dd7478646dea4c5fa9e8e458c78` on `officeapp-dev-api-migrate:38` | succeeded (no-op at head `20261012_0065_portfolio_forecast`) |
| API service | `officeapp-dev-api:100`, `services-stable`, 1/1 PRIMARY; running task `2b9c1636…6758` on `s22p4-68ff809d`, digest `sha256:c846036816cf494da55985028a82fdf2a99c907bd46f7462bc73c6dd907cadea`; `POST /api/engagements/import-workbook` → 401 unauthenticated (present) |
| Worker families | alert-scheduler 52, notification-sender 52, renewals-scheduler 52, portfolio-scheduler 4, audit-export 52, hubspot-intake 51, hubspot-reconcile 51, forecast-plans 29, deletion-cleanup 29, api-migrate 38 — all `s22p4-68ff809d` |
| Smoke | `smoke 20261012T224136Z` GREEN; gate clean |
| SPA | `assets/index-CwMcUryo.js` synced (immutable) + `index.html` (no-cache); CloudFront invalidation `I9X52BCW2B0D0RAKPWRWEPC643` COMPLETED; served bundle contains the import-workbook call |
| S22 specs on staging | `s22-p4-upload` (2) + `s22-p1-contract` + `s22-p2-owner-path`: `4 passed (1.6m)`; owner path re-run with the P4-3 label assertions: passed; gate clean after every run: 0 clients / 0 approvers / 0 people / 0 engagements |

## S22-P5 candidate (2026-10-12/13, session S22-3)

| Item | Value |
| --- | --- |
| Branch / commit | `feat/s22-p5` @ `d0270a48` (off `origin/main` dfc3f8b) |
| Image | `officeapp-dev-api:s22p5-d0270a48` · digest `sha256:9b2a594cb66f70aebbb3d5124224861583ed4a591556e1c055151585507c94ca` · 105,125,243 bytes · linux/amd64 |
| SPA | `web/dist` → `assets/index-Cv_2NWJ5.js` |
| Migration | **new**: `20261012_0066_bu_actuals` (engagement business_unit/sales_owner/delivery_owner/closed, allocation rate_basis/person, allocation_actual); reversible; parity 3 passed on Postgres; applied by the Terraform-owned migration task |
| Plan | `/tmp/s22p5-d0270a48.tfplan` — **12 to add, 14 to change, 12 to destroy**, image-only: 11 `aws_ecs_task_definition` + the `terraform_data` migration trigger replaced; `aws_ecs_service` + 9 `aws_cloudwatch_event_target` + 4 `aws_iam_role_policy` updated; nothing of any other type; every image → `s22p5-d0270a48`; same inputs as every previous plan; planned from the initialised p4 worktree whose `infra-tf` is byte-identical to this branch's |
| Checksums | tfplan `b558b29b8a43b9bdc7b19d6fd4081e7159e9966987b4abd66c992758fb52b9b6` · plan.txt `13f49b42…fa0b60` · plan.json `361ba7ed…ef7de4` |
| Local proof | api/tests/forecast 33; test_s22_p5_business_units 9; test_s22_portfolio_forecast 21; vitest 91 files / 574; tsc clean; Playwright s22-p5-forecast-model (3) + s22-p4-upload (2) + s22-p1-contract + s22-p2-owner-path on the local stack (Postgres at 0066) all pass |

## S22-P5 apply and roll (2026-10-13, image-only plan with the Terraform-owned migration, applied by the session)

| Step | Result |
| --- | --- |
| `terraform -chdir=infra-tf apply /tmp/s22p5-d0270a48.tfplan` (checksum re-verified first) | exit 0 · **Apply complete! Resources: 12 added, 14 changed, 12 destroyed** — exactly the plan |
| Migration task `40ddd4bb265740fc84bad1d1091ba1da` on `officeapp-dev-api-migrate:40` | succeeded — staging head now `20261012_0066_bu_actuals` |
| API service | `officeapp-dev-api:102`, `services-stable`, 1/1 PRIMARY; running task on `s22p5-d0270a48`, digest `sha256:9b2a594cb66f70aebbb3d5124224861583ed4a591556e1c055151585507c94ca`; `POST /api/engagements/import-forecast-model` → 401 unauthenticated (present) |
| Worker families | alert-scheduler 54, notification-sender 54, renewals-scheduler 54, portfolio-scheduler 6, audit-export 54, hubspot-intake 53, hubspot-reconcile 53, forecast-plans 31, deletion-cleanup 31, api-migrate 40 — all `s22p5-d0270a48` |
| SPA | `assets/index-Cv_2NWJ5.js` synced (immutable) + `index.html` (no-cache); CloudFront invalidation `IAGR8YTKDNV49X6L7J9I4W6OHL` COMPLETED; served bundle contains the import-forecast-model call |
| Smoke | `smoke 20261013T005136Z` GREEN; gate clean (0 clients / 0 approvers / 0 people / 0 engagements) |
| S22 specs on staging | `s22-p5-forecast-model` (3) + `s22-p4-upload` (2) + `s22-p1-contract` + `s22-p2-owner-path`: `7 passed (1.8m)`; gate clean after: 0 clients / 0 approvers / 0 people / 0 engagements; calendar restored by teardown |

## S22-P4 main image (post-merge, 2026-10-12, Kanna: "approved")

| Step | Result |
| --- | --- |
| Merge | `feat/s22-p4` @ 7e11726 squashed → `origin/main` = `ef50ef9` (release worktree `dealgate-s22-release`, branch `release/s22-p4`); squash tree `c03c5dc7…` identical to the accepted staging build |
| Image | `officeapp-dev-api:s22p4main-ef50ef9f` · digest `sha256:83ebf055a86f4b95d2eebab5784039546db896ecb95bcb6662f0b582914de0cd` · 101,649,730 bytes · linux/amd64 (same code as `s22p4-68ff809d`; builds are not byte-reproducible) |
| Plan | `/tmp/s22p4main-ef50ef9f.tfplan` SHA-256 `301b332f406bc731b666633d7a79e30531a8de14da9c76ffe3cf36a65779f81b` (plan.txt `cb2f5d54…44ea`, plan.json `61bdb3d0…03f8`) — 12 to add / 14 to change / 12 to destroy, image-only (11 task definitions + migration trigger replaced; service, 9 event targets, 4 role policies updated; every image → the new tag), same inputs; applied by the session under this round's image-only rule |
| Apply | exit 0 · **Apply complete! Resources: 12 added, 14 changed, 12 destroyed** |
| Migration task | `0af8dae2da5f41d993a19e7540cc07a3` on `officeapp-dev-api-migrate:39` succeeded (no-op at head `20261012_0065_portfolio_forecast`) |
| API service | `officeapp-dev-api:101`, `services-stable`, 1/1 PRIMARY; running task `2afff925…8006` on the digest above |
| Worker families | alert-scheduler 53, notification-sender 53, renewals-scheduler 53, portfolio-scheduler 5, audit-export 53, hubspot-intake 52, hubspot-reconcile 52, forecast-plans 30, deletion-cleanup 30, api-migrate 39 — all `s22p4main-ef50ef9f` |
| SPA | built from `ef50ef9` → the identical `assets/index-CwMcUryo.js`; synced with cache headers + `index.html` no-cache; CloudFront invalidation `I9J9UV21RVOVK14JAMJ8O1Z97G` COMPLETED; served bundle confirmed |
| Smoke | `smoke 20261012T234505Z` GREEN; gate clean (0 clients / 0 approvers / 0 people / 0 engagements) |
| S22 specs on the main image | `s22-p4-upload` (2) + `s22-p1-contract` + `s22-p2-owner-path`: `4 passed (1.5m)`; gate clean after: 0 clients / 0 approvers / 0 people / 0 engagements |

Staging now runs the main image with S22-P4. Still owner-unverified: P2-4 from-deal pre-fill on a real Closed-Won deal; the first real nightly portfolio tick (06:00 UTC).

## Local full-stack rehearsal (same API code as the image, local Postgres)

Stack: pgvector/pg16 container (`dealgate_e2e`, `alembic upgrade head` → `20261012_0065_portfolio_forecast`, seeds present), uvicorn `DEALGATE_ENV=local` with every role granted, Vite dev server same-origin through its `/api` proxy, `VITE_TEST_GROUPS` identity (bug #3).

| Spec | Result |
| --- | --- |
| `specs/s22/s22-p1-contract.spec.ts` | passed (4.7 s) — Client A golden equals the goldens to the cent; teardown left 0 tagged rows |
| `specs/s22/s22-p2-owner-path.spec.ts` | passed (36–38 s) — new engagement → five people → leaves → re-hire → gap month blank → burden +10 pts moves the cost; breadcrumb names client + engagement; calendar restored to 0.36 afterwards |

Bugs found and fixed during the rehearsal: `docs/bugs/s22.md` #1 (breadcrumb UUID, 28b6c3f), #2 (unnamed Forecast tables), #3 (role-less local identity). The API image needs no rebuild: `git diff --stat 520f5174..HEAD -- api worker` is empty. The SPA was rebuilt from the final HEAD (`8f644b2`) for publishing.

Not yet done, blocked on the apply approval above: migration on staging, API roll, SPA publish, CloudFront invalidation, `scripts/deploy-smoke.sh`, the two specs on staging, `scripts/check-test-data-clean.sh`, product-owner click-through.
