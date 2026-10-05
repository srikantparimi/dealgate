# S21 Core Staging Terraform Plan

Generated 2026-10-03 08:23 UTC from `dd253dcbcf51d71e6beed18ed8f2212a8aae43e0`
configuration (committed immediately afterward without code changes), workspace
`default`, AWS account `669810405473`, region `us-east-2`, candidate image
`s21-036ae9a3` (`sha256:cd7a573cc7ba5180291be1bef47b0877dc38c57a8c36633399d0f6c59bbee4ce`).
The raw unsaved plan is local at `/tmp/s21-candidate-036ae9a3-plan-final.log`.

## Result

`8 to import, 25 to add, 19 to change, 7 to destroy`.

- All seven destroys are replaced ECS task-definition revisions. No bucket,
  database, service, secret, queue, file or application record is destroyed.
- The API service changes in place from revision 70 to the Terraform-owned
  candidate task definition with 100% minimum healthy capacity.
- A candidate-image migration task and Terraform release gate run Alembic before
  the service update. A failed migration stops the apply while revision 70 stays
  bound. The dependency edge was verified with `terraform graph -type=plan`.
- Six scheduled worker task definitions and their exact EventBridge targets move
  to the candidate image. Two new persisted workers (`forecast_plans` and
  `deletion_cleanup`) are created and enabled at one-minute cadence.
- Existing SOW/agreement buckets and six property resources are declaratively
  adopted. Public blocks are unchanged; default encryption moves to the existing
  customer-managed KMS key; agreement versioning is enabled; current objects are
  never expired; noncurrent versions expire after 365 days.
- The existing web bucket's default encryption moves to the same KMS key. Its key
  policy already grants account-scoped CloudFront OAC decrypt.
- API KMS/Cognito permissions, exact sender-domain policy, scheduler run-task
  policies, stable KMS alias and an RDS parameter apply-method normalization are
  included. `rds.force_ssl` remains value `1`; no reboot/value change is planned.

## Deliberately Excluded

- Irreversible CloudTrail Object Lock, GuardDuty, SNS and alarms bundle.
- Real-person production approver SES identities and verification emails.
- Continuous HubSpot consumer and its alarms; legacy scheduled intake remains.
- Trusted fixture-cleanup schedule.

Flags are false by default for these independent operational changes. They remain
open requirements and are not represented as completed by this staging candidate.

## Verification

- `terraform -chdir=infra-tf validate`: passed.
- Scheduler configuration tests: 2 passed, 0 failed.
- `bash -n` and ShellCheck for `scripts/run-ecs-migration.sh`: passed.
- Whole-root refreshed plan: completed with the counts above.
- An optional mock-module release-binding assertion was abandoned after two
  attempts: first the fixture omitted required variables; then the planned task
  definition ARN was unknown. No assertion was weakened or marked passed. The
  real refreshed plan and graph provide the binding/order evidence instead.

## Required Human Decision

Confirm `USD` as the organization reporting currency and approve this exact
whole-root change set. Apply remains interactive; no saved plan, auto-approve,
targeted apply or scripted answer is permitted. At the prompt, any count or
resource difference from this record requires stopping and re-reviewing.
