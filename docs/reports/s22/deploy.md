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

## Local full-stack rehearsal (same image contents, local Postgres)

Recorded below as phase 2 progresses.
