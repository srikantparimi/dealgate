# infra/ — AWS CDK (TypeScript)

Sprint 0 leaves this folder as a placeholder. Sprint 1 lands the first stack:

- `NetworkStack` — VPC with public + private subnets, single NAT for dev.
- `DataStack` — RDS PostgreSQL (Multi-AZ off in dev), pgvector extension,
  Secrets Manager for the connection string.
- `AppStack` — ECS Fargate service (api), ALB, CloudFront distribution and
  S3 bucket for `web/dist`.
- `IngestStack` — API Gateway + Lambda for HubSpot webhook verification,
  SQS queue with DLQ.
- `PipelineStack` — GitHub OIDC role + CodeDeploy blue/green for the api.

Environments live in `bin/dealgate.ts` with one CDK app per env (dev, staging,
prod). Deployments run from GitHub Actions with OIDC — no long-lived AWS keys
in the repo.

See ADR 0001.
