# infra-tf/ — Terraform for DealGate on AWS

This is the active IaC for the DealGate deployment.
See ADR 0001 (Amendment 2026-09-17) for the switch from CDK to Terraform.
The old `infra/` CDK placeholder stays as-is until the first Terraform apply
lands and the team is happy with it.

## Layout

```
infra-tf/
  versions.tf          providers.tf     backend.tf
  variables.tf         locals.tf        main.tf         outputs.tf
  dev.tfvars.example
  modules/
    network/       VPC, 2 public + 2 private subnets, IGW, single NAT (dev cost)
    ecr/           officeapp-${env}-api repo with a 20-image lifecycle
    secrets/       Secrets Manager: db-master-password, db-url, jwt-signing-key
    data/          RDS Postgres 16 (db.t4g.micro, single AZ, private) + PG param group
    api/           ECS Fargate service, ALB (public HTTP), CloudWatch logs, IAM
    web/           Private S3 bucket + CloudFront (OAC, SPA fallback, security headers)
    auth/          Cognito user pool + hosted UI + PKCE app client
    github_oidc/   OIDC provider (opt-in) + deploy role scoped to the repo
```

## Prereqs

- Terraform >= 1.6.
- AWS CLI configured with profile `lm-arbiter-poc` targeting account
  `669810405473` in `us-east-2`. All commands assume
  `export AWS_PROFILE=lm-arbiter-poc`.
- The IAM principal you use locally needs administrator-ish permissions
  (VPC, ECS, RDS, IAM, Cognito, CloudFront, S3, Secrets Manager, ECR).

## First-time bootstrap

```sh
cd infra-tf
cp dev.tfvars.example dev.tfvars        # dev.tfvars is git-ignored
export AWS_PROFILE=lm-arbiter-poc

# If the account has never used GitHub OIDC before, set
# create_github_oidc_provider=true in dev.tfvars for the first apply, then
# flip it back to false.

terraform init
terraform plan  -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

**Intentional first-run failure.** The ECS service is created with
`image_tag = "bootstrap"`, which does not yet exist in ECR. Apply will
finish, but the service will keep failing to pull the image until the first
GitHub Actions run pushes `<ecr-uri>:bootstrap`. That is expected — the point
of the bootstrap apply is to create ECR + the OIDC role so CI *can* push.

The `aws_ecs_service.api` lifecycle ignores `task_definition` and
`desired_count`, so subsequent CI deploys that register new task defs will
not fight `terraform apply` from a laptop.

## Remote state (optional, recommended before staging)

`backend.tf` ships commented out so a clean clone can
`terraform init -backend=false` and validate. After the first apply, follow
the header comment in `backend.tf` to create the state bucket + lock table,
uncomment the backend block, and run `terraform init -migrate-state`.

## Environments

| Env     | Root path                     | Prefix               | Notes                                              |
| ------- | ----------------------------- | -------------------- | -------------------------------------------------- |
| dev     | `infra-tf/`                   | `officeapp-dev-*`    | This directory. Original bootstrap root.           |
| staging | `infra-tf/env/staging/`       | `officeapp-staging-*`| Per-env root; re-uses `../../modules/*`. See its README. |
| prod    | TBD                           | `officeapp-prod-*`   | Deferred pending custom domain choice and a possible multi-account split (see ADR TODO). |

The per-env root pattern (`env/<name>/main.tf` referencing `../../modules/*`)
won the coin flip over Terraform workspaces because separate state keys and
`.tfvars` files are easier to reason about when only two of us are on the
account. Dev stayed at the top of `infra-tf/` so its state file, `dev.tfvars`,
and CI never had to move.

## Teardown

```sh
terraform destroy -var-file=dev.tfvars
```

Destroy will fail if anyone dropped objects into the S3 web bucket (empty it
first) or if `deletion_protection` was flipped on for RDS. Both are off by
default in dev.

## Rough monthly cost (dev, us-east-2, always-on)

| Item                                          | Est. USD / mo |
| --------------------------------------------- | ------------: |
| NAT Gateway (1x, hourly + data)               |         ~$33  |
| ALB (application, minimal traffic)            |         ~$17  |
| RDS db.t4g.micro + 20 GB gp3 + 7d backups     |         ~$16  |
| Fargate 0.25 vCPU / 512 MB, 1 task 24x7       |          ~$9  |
| ECR storage (a handful of images)             |          ~$1  |
| Secrets Manager (3 secrets)                   |          ~$1  |
| CloudFront + S3 (very low traffic)            |          ~$1  |
| CloudWatch Logs (14d retention, low volume)   |          ~$1  |
| Cognito (< 50k MAUs free tier)                |           $0  |
| **Total**                                     |    **~$80**  |

Estimates exclude data-transfer spikes and any Bedrock / Textract usage,
which land in later ADRs and their own stacks.
