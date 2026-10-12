# Runbook — DealGate branch → staging deploy (D5, T36)

> S21F-02 safety notice (2 Oct 2026): the historical executable procedure
> below is superseded and MUST NOT be executed. Steps 2/4/9 mutate ECS outside
> Terraform, violating CLAUDE.md rule 12; EventBridge targets actually pin
> revisions, contrary to step 4. Describing the latest family is not worker
> deployment proof. The smoke retry advice was also invalid. See
> docs/s21/session-02.md and operations.md. Prepare a fresh whole-root reviewed
> Terraform plan, preserve required human confirmation, update all real target
> ARNs, and verify matching API/worker/UI/schema revisions before release.
> Preserve this historical text as incident evidence, not operational authority.

**Owner:** W4 · **Executed tonight by:** Lead · **Adopted:** S20 (2026-09-29).

This is the pre-merge deploy path the review calls A6 and directive D5:
one immutable image is built, migrations run backward-compatible against
that image, api + all seven worker task-defs are rolled to it, the SPA
publishes only after the API is live, CloudFront is invalidated, and the
D5 smoke gates run before the product-owner click-through. Only after
that does the branch squash-merge to `main` (CLAUDE.md rule 14).

**CI on `main` is post-merge redeploy only.** This runbook is the
supported way in for a branch. `bash -x` it end-to-end.

---

## 0 · Preconditions

Verified once per session. If any fails, stop.

```bash
# Right directory + right branch
test -d /Users/srikanthparimi/OfficeApp/dealgate-s20-W4
cd /Users/srikanthparimi/OfficeApp/dealgate-s20-W4
git rev-parse --abbrev-ref HEAD                      # expect: integrate/s20 (or the branch under test)
git status --porcelain                               # expect: empty

# AWS credentials landed on this shell
aws sts get-caller-identity --query Account --output text
# expect: 669810405473

# ECR + ECS + S3 constants
export AWS_REGION=us-east-2
export ACCOUNT=669810405473
export ECR_REPO=officeapp-dev-api
export ECR_REGISTRY="${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
export ECS_CLUSTER=officeapp-dev-cluster
export ECS_SERVICE=officeapp-dev-api
export ECS_API_FAMILY=officeapp-dev-api
export ECS_MIGRATE_FAMILY=officeapp-dev-api-migrate     # same image, different command
export CONTAINER_NAME=api
export S3_BUCKET=officeapp-dev-web-669810405473
export CLOUDFRONT_ID=E1XAQZCROIFYG7

# Run-task network (from memory: dealgate-staging-constants)
export SUBNETS='subnet-0629befd5cf1aea47,subnet-0c3daa3fbe1e5a9cd'
export SGS='sg-07b42ed263b796c0f'

# Seven worker task-def families (D5: "all worker task-defs on one image")
export WORKER_FAMILIES=(
  officeapp-dev-alert-scheduler
  officeapp-dev-notification-sender
  officeapp-dev-renewals-scheduler
  officeapp-dev-audit-export
  officeapp-dev-e2e-cleanup
  officeapp-dev-hubspot-intake
  officeapp-dev-hubspot-reconcile
)
```

The exact task-def revisions currently live in staging are recorded in
`docs/reports/s20/deploy.md` (§ "Before-state, N-1 revisions"). Write
them there **before** you kick off step 1, so rollback has a target.

---

## 1 · Build + push the immutable image

Tag = `s20-<git short SHA>`. This is the tag we roll api + every worker
to. Never tag `:latest` for a branch deploy — the smoke's Bedrock guard
and the workers' image invariant break if two revisions share a tag.

```bash
SHORT_SHA=$(git rev-parse --short=8 HEAD)
IMAGE_TAG="s20-${SHORT_SHA}"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"

# Login (idempotent)
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Build from repo root — context bundles worker/ alongside api/app.
# Fargate here is amd64 (see infra-tf/modules/api runtime_platform).
docker buildx build \
  --platform linux/amd64 \
  --file api/Dockerfile \
  --tag "$IMAGE_URI" \
  --push \
  .

# Prove the manifest landed
aws ecr describe-images --repository-name "$ECR_REPO" \
  --image-ids imageTag="$IMAGE_TAG" \
  --query 'imageDetails[0].{tag:imageTags,digest:imageDigest,size:imageSizeInBytes}'

echo "IMAGE_URI=$IMAGE_URI"
# ^ record this in docs/reports/s20/deploy.md as the "candidate image".
```

---

## 2 · Register a new api task-def revision + a matching migrate revision

Fetch the currently-live task-defs, patch the container image, register.
`describe-task-definition` returns fields that `register-task-definition`
rejects — we strip them per the CI job's proven recipe.

```bash
# Helper (bash function) — used for api + every worker below.
fetch_and_patch () {
  local family="$1" outfile="$2" image="$3"
  aws ecs describe-task-definition --task-definition "$family" \
    --query 'taskDefinition' > "$outfile.raw"
  jq --arg image "$image" --arg name "$CONTAINER_NAME" '
    .containerDefinitions |= map(
      if .name == $name then .image = $image else . end
    )
    | del(
        .taskDefinitionArn, .revision, .status,
        .requiresAttributes, .compatibilities,
        .registeredAt, .registeredBy
      )
  ' "$outfile.raw" > "$outfile"
}

fetch_and_patch "$ECS_API_FAMILY" api.json "$IMAGE_URI"
fetch_and_patch "$ECS_MIGRATE_FAMILY" migrate.json "$IMAGE_URI"

API_TD=$(aws ecs register-task-definition --cli-input-json file://api.json \
  --query 'taskDefinition.taskDefinitionArn' --output text)
MIG_TD=$(aws ecs register-task-definition --cli-input-json file://migrate.json \
  --query 'taskDefinition.taskDefinitionArn' --output text)

echo "API_TD=$API_TD"
echo "MIG_TD=$MIG_TD"
# ^ record both in docs/reports/s20/deploy.md.
```

---

## 3 · Run migrations against the new image (backward-compatible only)

**Order matters:** the image is already built (§1), so the alembic run
uses the code that ships with it. The mutable `:bootstrap` tag exists in
task-def revs, but we do not rely on it here — we point at the new
image explicitly via `MIG_TD`. See memory `deploy-order.md` for the
Sprint-10 story of what happens when this order is wrong.

Every migration in this branch is **backward-compatible** per D5:
new columns nullable, new tables only, no `DROP` of populated columns.
An old container reads the new schema safely — that is why we can run
the migration before rolling the service.

```bash
alembic_task_arn=$(aws ecs run-task \
  --cluster "$ECS_CLUSTER" \
  --task-definition "$MIG_TD" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SGS],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' --output text)
echo "alembic_task=$alembic_task_arn"

aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER" --tasks "$alembic_task_arn"

exit_code=$(aws ecs describe-tasks --cluster "$ECS_CLUSTER" \
  --tasks "$alembic_task_arn" \
  --query 'tasks[0].containers[0].exitCode' --output text)
echo "alembic_exit_code=$exit_code"
[ "$exit_code" = "0" ] || { echo "MIGRATION FAILED — stop, see logs"; exit 1; }

# Proof the head advanced. If a migration was a no-op this returns the
# previous head — that's fine, but record the value.
aws logs tail /ecs/officeapp-dev-api --since 10m --follow=false \
  | grep -Ei 'alembic|migrat' | tail -50
```

---

## 4 · Roll API + every worker task-def to the new image

The API service updates first (behind ALB, drains gracefully). The
worker task-defs are scheduled tasks — nothing to `update-service`, but
each family gets a new revision so the next scheduled invocation picks
up the new image.

```bash
# 4a — API service
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --task-definition "$API_TD" \
  --force-new-deployment > /dev/null
aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE"

# 4b — every worker family. Loop, register a new rev pinned to the same
# immutable image, and echo the resulting ARN so the deploy log can show
# component versions for T36.
for family in "${WORKER_FAMILIES[@]}"; do
  fetch_and_patch "$family" "$family.json" "$IMAGE_URI"
  worker_td=$(aws ecs register-task-definition \
    --cli-input-json "file://$family.json" \
    --query 'taskDefinition.taskDefinitionArn' --output text)
  echo "WORKER_TD[$family]=$worker_td"
done
# ^ paste every WORKER_TD line into docs/reports/s20/deploy.md.
```

EventBridge rules already reference the family (not a revision) so the
next scheduled tick invokes the new rev. Confirm:

```bash
aws ecs list-tasks --cluster "$ECS_CLUSTER" --desired-status RUNNING \
  --query 'taskArns' --output text | head
```

---

## 5 · Deploy smoke against the API

The smoke owns its own fixture, cleans up, and gates the whole run.

```bash
S15_BASE_URL="https://app.dealgateapp.com" scripts/deploy-smoke.sh
```

Green = safe to publish the SPA. Red = **stop**; do not sync S3.

If extraction fails schema validation, retain the failure and investigate.
Do not retry unchanged code until green or relabel the failure as a flake.

---

## 6 · Build + publish the SPA

Same immutable checkout as the API build (`SHORT_SHA` above). The Vite
build reads Cognito env from repo secrets on CI. For a manual staging build,
use the checked-in host-agnostic `.env.production`; do not override its
Cognito values from an interactive shell. In particular, a hosted domain
without `https://` becomes a relative URL and causes an expanding redirect
path/CloudFront 414, while a redirect URI of `/` does not match Cognito's
registered `/auth/callback` URL.

```bash
(
  cd web
  npm ci
  env -u VITE_COGNITO_DOMAIN \
      -u VITE_COGNITO_CLIENT_ID \
      -u VITE_COGNITO_REDIRECT_URI \
      -u VITE_COGNITO_LOGOUT_URI \
      npm run build
)

aws s3 sync web/dist/ "s3://${S3_BUCKET}" --delete
```

After invalidation, use a fresh browser context with no stored tokens. Opening
`https://app.dealgateapp.com/` must reach the Cognito login URL on
`https://officeapp-dev-405473.auth.us-east-2.amazoncognito.com`, with
`redirect_uri=https://app.dealgateapp.com/auth/callback`, then a real login must
return to `/command`. Treat a relative Cognito path, HTTP 414 or
`redirect_mismatch` as a failed deployment.

---

## 7 · Invalidate CloudFront

```bash
inv_id=$(aws cloudfront create-invalidation \
  --distribution-id "$CLOUDFRONT_ID" \
  --paths '/*' \
  --query 'Invalidation.Id' --output text)
echo "invalidation=$inv_id"
aws cloudfront wait invalidation-completed \
  --distribution-id "$CLOUDFRONT_ID" --id "$inv_id"
```

---

## 8 · Post-deploy gates (T36)

Before the product-owner click-through, prove every gate from the D5
contract:

```bash
# a) API is on the new revision + image
aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
  --query 'services[0].taskDefinition'
aws ecs describe-task-definition --task-definition "$API_TD" \
  --query 'taskDefinition.containerDefinitions[0].image'
# ^ expect: ends with :s20-<SHORT_SHA>

# b) Every worker family also points at the new image
for family in "${WORKER_FAMILIES[@]}"; do
  latest=$(aws ecs describe-task-definition --task-definition "$family" \
    --query 'taskDefinition.containerDefinitions[0].image' --output text)
  echo "$family -> $latest"
done
# ^ every line must end with the same :s20-<SHORT_SHA>. Record in deploy.md.

# c) SPA object hash changed
aws s3api list-objects-v2 --bucket "$S3_BUCKET" --prefix "index.html" \
  --query 'Contents[0].{key:Key,mtime:LastModified,etag:ETag}'

# d) The smoke gate is already green from §5. If it wasn't, you're not here.
```

Only then hand off the URL for the ≤12-step click-through
(directive §8 "Morning deliverable").

---

## 9 · Rollback (proven tonight)

Pointing the api service back at a previous task-def revision is a
2-minute operation. Backward-compatible migrations don't need a schema
revert — an old container reads the new schema safely. Rollback only
touches the schema when the migration was destructive; ours were not.

```bash
# Prior revision recorded in docs/reports/s20/deploy.md (§ "Before-state, N-1").
# Example: api service was on rev 50 before; rev 51 is the new one we just
# rolled to; rollback = point back at rev 50.
PREV_REV=50
NEW_REV=51

# 9a — roll api back to N-1
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --task-definition "${ECS_API_FAMILY}:${PREV_REV}" \
  --force-new-deployment > /dev/null
aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE"

# 9b — smoke against the rolled-back API to prove it's healthy
S15_BASE_URL="https://app.dealgateapp.com" scripts/deploy-smoke.sh

# 9c — roll api forward to N to prove the round-trip works
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --task-definition "${ECS_API_FAMILY}:${NEW_REV}" \
  --force-new-deployment > /dev/null
aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE"
```

Worker families rollback the same way — `aws ecs register-task-definition`
never deletes prior revs, so `officeapp-dev-hubspot-intake:${PREV_REV}` is
still there and can be re-selected on the next EventBridge invocation via
the target's task-definition field (Terraform-only; do not edit in the
console). If a worker rev needs to be pinned back immediately, apply the
scheduler module with `hubspot_intake_task_def_revision=${PREV_REV}` and
Terraform will update the EventBridge target.

**Schema rollback (only if the migration was destructive):** every W-owned
alembic revision includes a `downgrade()`. Run:

```bash
aws ecs run-task \
  --cluster "$ECS_CLUSTER" \
  --task-definition "$ECS_MIGRATE_FAMILY:${PREV_REV}" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SGS],assignPublicIp=DISABLED}" \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","alembic","downgrade","-1"]}]}'
```

Backward-compatible migrations (this deploy) do not need this step.

---

## 10 · Log evidence

Everything above lands as one entry in `docs/reports/s20/deploy.md`:

- Candidate image URI + digest.
- Before-state task-def revisions for the api service and every worker
  family (N-1 targets).
- After-state task-def revisions (N).
- Alembic run task ARN, exit code, log tail.
- Smoke run tag + green status line.
- SPA build hash (last S3 sync summary).
- CloudFront invalidation ID.
- Rollback proof: timestamps + service task-def ARNs across the
  rev 50 → rev 51 round-trip.
- Gate-by-gate `T36` result.

No line is optional. If a step's proof is missing, the deploy is not
"done" — it is "unverified", which under contracts §1 is not a state.
