# ADR 0001 — Architecture: modular monolith on AWS

Date: 2026-09-17
Status: Accepted (Sprint 0)

## Context

Internal app for tens of users, holding contract terms and compensation-derived
cost. Approval workflow spanning days. Three narrow AI jobs (adviser, SOW
extraction, CEO brief).

## Decision

- **Frontend**: React + TypeScript on S3 + CloudFront.
- **API**: Python FastAPI on ECS Fargate behind an ALB.
- **Auth**: Amazon Cognito federated to the corporate IdP; SSO groups map to roles.
- **Database**: RDS PostgreSQL, Multi-AZ in prod, `pgvector` extension.
- **Workflow**: state machine persisted in Postgres + SQS + EventBridge Scheduler.
- **Documents**: S3 with versioning, SSE-KMS, Object Lock on the signed-SOW prefix.
- **AI**: Amazon Bedrock (Claude) for adviser / SOW extraction / CEO brief;
  Textract for scanned PDFs.
- **Web research**: search API (Tavily or Brave) called from a tool Lambda with
  outbound allowlist.
- **HubSpot ingress**: API Gateway + Lambda validates HubSpot v3 signature, drops
  the event on SQS; worker re-reads the deal from the HubSpot API.
- **Notifications**: SES for email; Teams or Slack incoming webhooks; transactional
  outbox table.
- **Secrets, logs**: Secrets Manager, KMS, CloudWatch, CloudTrail, GuardDuty.
- **IaC and CI/CD**: AWS CDK (TypeScript), GitHub Actions with OIDC into AWS.

## Consequences

- One shared DB across API + worker keeps the state machine easy to audit and
  replay; the tradeoff is that scaling out means read replicas rather than
  service extraction.
- Bedrock keeps client data inside our AWS account; models never train on our content.
- HubSpot write-back is limited to three read-only deal properties (governance
  status, approved GM %, DealGate link) to avoid sync loops.
- Not Step Functions: the DB state machine is simpler to test and replay for an
  approval flow measured in days, not seconds.
- Not microservices: for tens of users, service boundaries would add failure
  modes without adding value.

## Open

- Search API choice (Tavily vs Brave) — verify pricing and data-residency in
  Sprint 0, then amend this ADR.

## Amendment 2026-09-17

Switched IaC tool from AWS CDK (TypeScript) to Terraform. Rationale:

- The team already runs Terraform elsewhere, so we keep a single-language
  toolchain rather than adding a TypeScript build path just for infra.
- Terraform needs less new-account bootstrap than CDK (no `cdk bootstrap`
  stack, no CDK-managed asset buckets) which matters for a fresh sub-account
  like `669810405473` where we want the smallest possible footprint.

The active code lives in `infra-tf/`. The old `infra/` CDK placeholder stays
until the first Terraform apply has run in dev and staging; the module map
above (Network / Data / App / Ingest / Pipeline) still describes the target
shape, only the implementation tool changed.
