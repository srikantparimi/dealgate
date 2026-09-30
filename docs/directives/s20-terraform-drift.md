# Directive S20: Terraform drift — local-state sweep + accumulated adoption

From: Kanna Parimi, product owner. Filed 29 Sep 2026 alongside the S19
slice 1 merge; not this slice, not the next one. Owner picks it up when
the pipeline story is closed.

## Motivation

S14a exposed 61 drifted AWS resources from months of hand-applies never
round-tripped into terraform state. S14a.1 moved state into S3 and
started adopting drift via `terraform import`. That work stopped
mid-flight; the state that lives at
`s3://officeapp-tfstate-669810405473/dealgate/staging/terraform.tfstate`
still misses substantial coverage. A `terraform plan -refresh=false`
after S19 slice 1's I1 reconcile shows:

```
Plan: 38 to add, 9 to change, 6 to destroy.
```

Adds cluster:
- `module.observability.*` (11 resources — CloudTrail + GuardDuty + SNS +
  alarms). Never adopted; the resources exist in AWS.
- `module.storage.aws_s3_bucket.{sows,agreements}` + their
  PAB/versioning/lifecycle/SSE/object-lock siblings.
- `module.kms.aws_kms_alias.data`.
- `module.api.aws_iam_role_policy.{task_cognito_read,task_kms,task_execution_kms}`.
- `module.schedulers.aws_ecs_task_definition.e2e_cleanup` + its event
  rule/target/policy.
- `aws_route53_record.app_alias_{a,aaaa}` at root.

Changes cluster:
- `module.api.aws_iam_role_policy.sow_and_bedrock` — in-place update.
- Four scheduler task-defs at rev 34 (`alert_scheduler`, `audit_export`,
  `notification_sender`, `renewals_scheduler`) plus the api task-def
  itself — every one wants "must be replaced" because container_definitions
  drifted (image tag + env). The api replacement now lands cleanly (S19
  I3 relaxed the `ALLOW_DEV_SEED_ENDPOINT` gate); the schedulers still
  drop CI-set env vars if the plan applies as-is.

Compounding this, three known **operator-laptop artefacts** must not
resurface:
1. `infra-tf/terraform.tfstate*` local files never deleted per the
   S14a.1 ADR post-migration step. S19 renamed them to `.stale.bak`
   on Kanna's laptop; every other operator laptop still needs the
   sweep. `scripts/tf-init.sh` refuses `init` when the files are
   present, but only if operators use the wrapper.
2. Scripted `yes` answers to interactive terraform prompts (CLAUDE.md
   rule 15) — the mechanical fix is in the codebase; the cultural fix
   is a runbook operators actually read.
3. `dev.tfvars` image_tag currently pinned to a branch build; every
   operator laptop uses a different tag by default. This is fine as
   long as CI is authoritative for what runs, but confusing when
   plan-diffs surface.

## Scope

**In scope:**
- Sweep local `terraform.tfstate*` files off every operator laptop
  (Kanna already done; script + PR-checklist prompt for anyone else).
- Adopt the 38 drifted resources into TF state using
  `terraform import` in small, reversible batches — one module per
  batch (observability, storage, kms alias, api-role policies,
  scheduler task-defs, root DNS aliases).
- For each batch: `import` → `plan` → confirm zero diff → the next
  batch. **No `apply` until every batch's plan converges to zero
  changes.** This is exactly the S14a.1 rule.
- Update the four scheduler task-defs' TF rendering to include the
  env vars CI adds (`SES_FROM_ADDRESS`, `TEAMS_WEBHOOK_URL`, etc.) so
  the replacement diff is actually zero, not just "must be replaced".
- Once every module reads zero, run one final `apply` on the whole
  root as a canary and screenshot the "No changes" result.
- Standard slice report + click-through, no user-facing surface.

**Out of scope:**
- Any new AWS resource. This is adoption, not creation.
- Any code change to the modules themselves that isn't required by
  the import (e.g., renaming a resource, refactoring the module
  layout). If TF's rendering diverges from AWS's actual state, the
  fix is on the TF-code side, but no cross-module refactoring.
- Prod. Staging drift is the corpus.

## Principles (from the S14a.1 rules — copied here so this directive stands alone)

- Import in batches, plan after each. A batch is one module or one
  cohesive group (all of module.storage's buckets + their PAB +
  versioning + lifecycle count as one batch).
- No `apply` until the batch's plan is zero. If the plan is not zero,
  either the resource wasn't imported cleanly, or the TF code needs
  to catch up to AWS reality.
- Every import command lands in the slice progress file, with the
  resource address, the AWS id, and the resulting plan diff summary.
  Recovery via S3 object-version is well-trodden but expensive to
  the operator's morale.
- `scripts/tf-init.sh` is the only supported `init` entry point.
  The wrapper is CLAUDE.md rule 15; the directive assumes it.

## Batches (draft — the slice owner refines when they pick this up)

1. **Local-state sweep.** `find` on every operator laptop, rename to
   `.stale.bak`. Two-line change to
   `docs/directives/onboarding.md` telling new operators to run
   `scripts/tf-init.sh` (never raw `terraform init`).
2. **Storage buckets.** `module.storage.aws_s3_bucket.sows` +
   `module.storage.aws_s3_bucket.agreements` + their PAB / versioning
   / lifecycle / SSE / object-lock configs. 14 resources. Import ids
   are the bucket names (`officeapp-dev-sows-669810405473`,
   `officeapp-dev-agreements-669810405473`) and the sub-resource
   pattern per aws provider docs.
3. **KMS alias.** `module.kms.aws_kms_alias.data` — single resource.
4. **Observability.** `module.observability.*` — 11 resources. Batch
   as one because they're interlocked (CloudTrail bucket + policy +
   PAB + object-lock all reference each other).
5. **API role policies.** `task_cognito_read`, `task_kms`,
   `task_execution_kms`. Three resources; imports are
   `role-name:policy-name`.
6. **Scheduler task-defs.** Four `must be replaced` task-defs. First,
   extend TF's container_definitions to include every env var CI has
   been carrying (`SES_FROM_ADDRESS` etc.). Then plan → should read
   zero. Then the same for the e2e_cleanup task-def which is a fresh
   create, not a replace.
7. **DNS aliases.** `aws_route53_record.app_alias_a` +
   `app_alias_aaaa` at root scope.
8. **Root canary apply.** Whole-root `plan` → zero. Whole-root `apply`
   → `Resources: 0 added, 0 changed, 0 destroyed`. Screenshot for the
   slice report.

## Definition of done

- `terraform plan -refresh=false` from a clean laptop reads
  `No changes. Your infrastructure matches the configuration.` on a
  fresh `scripts/tf-init.sh` + `terraform plan`.
- Slice progress file lists every import command with its resulting
  diff.
- No AWS resource was created or destroyed during the slice — the
  final canary apply is the proof.
- Every operator laptop is confirmed free of
  `infra-tf/terraform.tfstate*` (except `.stale.bak`).

## Not in this directive

- The eventual prod terraform root — split when we cut prod, not
  before.
- Any change to CI's `aws ecs describe-task-definition ...
  register-task-definition` flow — that's the accepted rule-12 carve-
  out. If the scheduler task-defs still show "must be replaced" after
  batch 6, extend the module, don't touch CI.
- The still-missing DLQ alarms + queue-depth metrics on the S19 SQS
  queues — file separately if we want them.
