# S7 — Staging Terraform environment

## User story
As the team, we need a staging env before touching prod. Add a second
Terraform workspace / env directory that provisions the same modules
under the prefix `officeapp-staging-*` in the same AWS account.

## Acceptance
- `infra-tf/env/staging/` directory with:
  - `main.tf` re-using the modules from `../..`
  - `staging.tfvars.example` (env=staging, image_tag=bootstrap, github_repo=...)
  - Separate backend key so state doesn't collide with dev.
- All resources named `officeapp-staging-*` (via `local.name_prefix`).
- Same shape as dev (single NAT + t4g.micro RDS) — cost adds ~$80/mo.
- `terraform init` + `terraform validate` + `terraform fmt` clean.
- DO NOT `terraform apply` — leave that as the integrator's step.
- README notes the manual steps: run `terraform apply`, push image with
  `staging` tag, create Cognito user, share URL.

## Notes
- Prod env is deferred until custom domain choice is made (staging can
  use CloudFront default domain like dev).
- Reuses the same account (669810405473) — production separation is a
  later ADR (multi-account AWS Organization).
