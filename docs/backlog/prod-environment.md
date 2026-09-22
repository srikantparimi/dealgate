# Backlog: DealGate production environment

Filed from S14a state-reconciliation (`docs/directives/s14a.1-state-reconciliation.md`
§5) — Kanna 22 September 2026. Not a story to *build* prod; a story
to *think through* prod so the next slice starts from a plan.

## Why this exists (not the code)

DealGate has been running on a single AWS account, a single ECS
cluster, a single Cognito user pool, and a single CloudFront
distribution branded "dev" but functioning as the live staging /
demo env. Every reference to "prod" in the codebase today is
either aspirational or a guard clause (`if env == "prod": raise`).
The `production_cannot_opt_in` tftest in
`infra-tf/modules/api/tests/dev_seed.tftest.hcl` is the current
prod guard — it enforces that even if someone opts a prod env into
the S13a dev-seed endpoint, the module refuses to emit the env
var. That guard should stay in place until a prod env exists.

## Assumptions this backlog challenges

- **One AWS account is enough for prod.** Probably not. Blast
  radius (a bad IAM change in dev takes prod down), audit
  separation (SOC2 wants prod isolated), and compliance
  (multi-tenant customer data can't sit in a dev account) all
  push toward a separate account. Pick per-region or per-env.
- **CloudFront distribution can be reused.** No — SPA + API need
  a separate distribution per env (custom domain, ACM cert, WAF).
- **Cognito user pool can be reused.** No — prod users need their
  own pool, their own MFA policy, their own recovery flows.
- **HubSpot app can be shared.** No — prod HubSpot deals + prod
  DealGate write-back needs a prod HubSpot private app (rate
  limits, secrets rotation, audit trail).
- **RDS can be a single instance.** No — prod needs Multi-AZ,
  automated backups > 7 days, encryption at rest with a prod-only
  KMS key, PITR enabled.

## What prod would need (draft — not a spec)

### Account + identity

- Dedicated AWS account, e.g. `officeapp-prod-<accountid>`,
  linked to the same AWS Organizations root as the current dev
  account. Cross-account IAM only for the CI/CD role.
- Prod deploy role assumable only from a protected GitHub
  Actions environment with reviewer approvals.
- No console access via humans for infra changes (CLAUDE.md rule 12).

### Networking

- Own VPC, own NAT (probably two for AZ redundancy), own ALB.
- No route back to dev subnets. No shared security groups.

### Data

- RDS Multi-AZ, minimum `db.r6g.large`, PITR on, 35-day retention.
- Separate KMS key (`officeapp-prod-data`), NOT the dev key.
- Encryption at rest AND in flight (force `rds.force_ssl=1`).
- Migrations run via a gated one-off ECS task with a change-approval
  ticket recorded in the PR.

### Auth

- Prod Cognito user pool, prod client, prod OAuth callback allowlist.
- Prod OAuth secret rotation via Secrets Manager.
- MFA required for all human users (SMS + TOTP fallback).
- The dev-seed endpoint (`api/app/routers/dev_seed.py`) MUST NOT
  be mountable — verified by the existing `production_cannot_opt_in`
  tftest AND by `ALLOW_DEV_SEED_ENDPOINT` env var absent from the
  prod task-def (module already enforces both).

### Frontend + CDN

- Prod CloudFront distribution with prod ACM cert (custom domain
  TBD — likely `app.dealgate.smartek21.com` or similar).
- Prod S3 web bucket, prod invalidations.
- Prod WAF rules (rate limits, geo blocks TBD, OWASP top-10
  managed rule group).

### Integrations

- Prod HubSpot private app with its own client_id + secret in a
  prod-only secret.
- Prod Bedrock model access approval (if we're using Anthropic
  models via Bedrock in prod).
- Prod SES verified sender identity for notification emails
  (currently no-op in dev).

### Observability

- CloudTrail on prod account, delivered to a dedicated audit S3
  bucket with object-lock.
- GuardDuty enabled.
- CloudWatch alarms: RDS CPU, RDS free storage, API 5xx rate,
  API latency p99, task failures. SNS topic with real on-call
  email addresses.
- Log retention 90 days minimum.

### CI/CD

- Prod deploys via a separate GitHub Actions workflow that runs
  ONLY on tagged releases (`v*`), requires a code-owner reviewer
  approval, and prompts for manual confirmation in the workflow.
- Prod deploys are fast-forward-only from `main`; no
  cherry-picks, no direct pushes.
- Prod Terraform state in a prod-account S3 bucket, prod-account
  lock table.

## Acceptance tests (Given/When/Then, once we build it)

```
Given a prod env exists at officeapp-prod-<accountid>
When someone tries to `terraform apply` with dev-seed enabled
Then apply fails at plan-time (production_cannot_opt_in tftest
     already passing today enforces module-level guard)

Given a prod HubSpot event fires
When the prod DealGate webhook receives it
Then the write-back uses prod HubSpot credentials, not dev

Given a prod SOW is uploaded
When a Delivery user tries to approve
Then the S12 signatories flow + S13a delete gate + S13b GM panel
     all render exactly as they do on staging

Given a prod incident triggers a CloudWatch alarm
When on-call receives the SNS page
Then the correlation_id in the alarm links to CloudTrail + application logs
```

## Files this backlog will eventually touch (estimate)

- `infra-tf/env/prod/` (new root)
- `infra-tf/modules/*` (parametrise anywhere still baking in "dev")
- `.github/workflows/deploy-prod.yml` (new)
- `docs/adr/00XX-two-account-topology.md` (new)
- `docs/runbooks/prod-oncall.md` (new)

## Non-goals (as of Sep 2026)

- Not building prod today.
- Not designing the multi-tenant architecture (that's a separate
  design story — DealGate is single-tenant per account until
  further notice).
- Not procuring the domain / cert — that lives with Task #26
  ("Blocked: custom domain + ACM cert — needs domain choice").
