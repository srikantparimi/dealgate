# infra-tf/env/staging/ — DealGate staging environment

Second Terraform root, parallel to the dev root at `infra-tf/`. Both stacks
live in the SAME AWS account (`669810405473`, `us-east-2`) and share the
account-wide GitHub OIDC provider; every resource is prefixed
`officeapp-staging-*` so nothing collides with dev.

Sizes mirror dev (single NAT, `db.t4g.micro`, one 0.25 vCPU Fargate task) —
staging exists so a human can click through a release before it reaches
prod, not to be a load test. Approximate additional cost ≈ **$80–100/mo**.

## Layout choice

We kept the dev root at `infra-tf/` (untouched) and added this parallel
`env/staging/` root instead of moving dev under `env/dev/`. Rationale:

- Zero-diff for dev (state file, `dev.tfvars`, CI, muscle memory all
  unchanged).
- Symmetry gap is small — `infra-tf/README.md` documents both locations.
- Follows the "per-env root" pattern already suggested in the top-level
  `infra-tf/main.tf` header comment.

Later, when prod arrives, we can either add `env/prod/` alongside or
migrate dev under `env/dev/` in a dedicated PR.

## First-time bootstrap

```sh
cd infra-tf/env/staging
cp staging.tfvars.example staging.tfvars     # git-ignore matches infra-tf/*.tfvars
export AWS_PROFILE=lm-arbiter-poc

terraform init
terraform plan  -var-file=staging.tfvars
terraform apply -var-file=staging.tfvars
```

`create_github_oidc_provider` defaults to `false` because the dev apply
already created the account-wide provider. Leave it false unless the
account has genuinely never had it (rare).

**Intentional first-run failure** (same as dev). The ECS service is
created with `image_tag = "bootstrap"`, which doesn't exist in the new
staging ECR repo. Apply completes, service stays in "cannot pull" until
CI pushes `<staging-ecr-uri>:bootstrap` (or `:staging`).

## Follow-up steps after first apply

1. Push an API image to the staging ECR repo with the `staging` tag:

   ```sh
   TAG=staging
   ECR=$(terraform output -raw api_ecr_uri)
   aws ecr get-login-password --region us-east-2 \
     | docker login --username AWS --password-stdin "${ECR%/*}"
   docker buildx build --platform linux/arm64 -t "$ECR:$TAG" ./api --push
   ```

   (Or trigger the deploy workflow with `environment=staging` once it's
   wired up.)

2. Invite a Cognito user in the new pool:

   ```sh
   POOL_ID=$(terraform output -raw cognito_user_pool_id)
   aws cognito-idp admin-create-user \
     --user-pool-id "$POOL_ID" \
     --username you@smartek21.com \
     --user-attributes Name=email,Value=you@smartek21.com Name=email_verified,Value=true
   ```

3. Share the staging URLs (both are `terraform output`):
   - SPA: `https://$(terraform output -raw cloudfront_domain)`
   - API: `http://$(terraform output -raw alb_dns)`
   - Hosted UI: `terraform output -raw cognito_hosted_ui_url`

## Remote state

See `backend.tf`. Ships commented so `terraform init -backend=false`
validates on a fresh clone. When ready, uncomment; the bucket + lock
table are shared with dev, only the state `key` differs
(`dealgate/staging/terraform.tfstate`).

## What to change between dev and staging

Almost nothing today — sizes and defaults are the same. If cost matters:

- Drop RDS backup retention below 7d (edit `modules/data`, gate on env)
  once staging has real data to lose.
- Consider `single_nat_gateway = true` variants only if the network
  module grows a knob; currently both envs already run one NAT.
- Reduce CloudWatch log retention from 14 → 7 days for the staging log
  groups if noise becomes expensive.

## Teardown

```sh
terraform destroy -var-file=staging.tfvars
```

Same caveats as dev: empty the SPA S3 bucket first if anyone uploaded
objects, and confirm RDS `deletion_protection` is off (it is by default).
