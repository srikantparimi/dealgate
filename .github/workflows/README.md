# CI / Deploy pipelines

Two workflows live here:

- `ci.yml` — lint, typecheck, tests. Runs on every PR and push to `main`.
- `deploy.yml` — builds the API image, runs migrations, rolls the ECS
  service, and publishes the web bundle to S3/CloudFront. Runs only on push
  to `main` (or manually via `workflow_dispatch`).

## Required repository secrets

Add these under **Settings → Secrets and variables → Actions** before the
first deploy. All are consumed by `.github/workflows/deploy.yml`.

| Secret name                  | What it is                                                                 | Set by |
| ---------------------------- | -------------------------------------------------------------------------- | ------ |
| `AWS_ROLE_ARN`               | IAM role assumed via GitHub OIDC. Needs ECR push, ECS deploy, S3 write, CloudFront invalidate. | Infra (Agent G) |
| `CLOUDFRONT_ID`              | CloudFront distribution ID that fronts the web S3 bucket.                  | Infra (Agent G) |
| `ECS_PRIVATE_SUBNETS`        | Comma-separated private subnet IDs (no quotes, no spaces) for the migration one-off task. | Infra (Agent G) |
| `ECS_TASK_SECURITY_GROUPS`   | Comma-separated security group IDs for the migration one-off task. Must reach the RDS instance. | Infra (Agent G) |
| `VITE_COGNITO_DOMAIN`        | Cognito hosted-UI domain, e.g. `https://officeapp-dev.auth.us-east-2.amazoncognito.com`. | Infra (Agent G) |
| `VITE_COGNITO_CLIENT_ID`     | Cognito app client ID (the SPA client).                                    | Infra (Agent G) |
| `VITE_COGNITO_REDIRECT_URI`  | Full HTTPS URL to `/auth/callback`, e.g. `https://dev.officeapp.example.com/auth/callback`. | Infra (Agent G) |
| `VITE_COGNITO_LOGOUT_URI`    | Where Cognito bounces the browser after sign-out, e.g. `https://dev.officeapp.example.com/`. | Infra (Agent G) |

`AWS_REGION`, `ECR_REPO`, `ECS_CLUSTER`, `ECS_SERVICE`, `S3_BUCKET`, and the
task family names are set as workflow `env:` in `deploy.yml`; change them
there if the Terraform stack renames anything.

## OIDC trust prerequisites

The role in `AWS_ROLE_ARN` must trust `token.actions.githubusercontent.com`
and be scoped to this repository (owning org + `dealgate` repo) — see the
Terraform `github-oidc` module.
