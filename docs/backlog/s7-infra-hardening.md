# S7 — Infra hardening: KMS keys, S3 Object Lock, CloudTrail, GuardDuty

## User story
As a security-aware engineering org, this is production. The blueprint §11
+ §12 call for KMS keys (not just SSE-AES256), Object Lock on the
signed-SOW prefix, CloudTrail, and GuardDuty. Ship the Terraform.

## Acceptance
- New Terraform module `infra-tf/modules/kms/`:
  - Customer-managed KMS key `officeapp-dev-data` for all S3 buckets + RDS + Secrets Manager. Key rotation ON.
  - Alias `alias/officeapp-dev-data`.
  - Grants for the ECS task role (kms:GenerateDataKey, kms:Decrypt) and for S3 service.
- Update `infra-tf/modules/storage/` (web, agreements, sows, audit-exports, signed-sows):
  - Switch SSE from `AES256` to `aws:kms` referencing the new key.
  - Signed-SOW prefix `signed/*` gets **Object Lock in GOVERNANCE mode, 3-year retention**.
- Update `infra-tf/modules/data/`:
  - RDS uses `storage_encrypted = true` with the new KMS key.
- New Terraform module `infra-tf/modules/observability/`:
  - CloudTrail multi-region trail `officeapp-dev-audit` writing to a KMS-encrypted bucket with Object Lock (COMPLIANCE, 7-year).
  - GuardDuty detector.
  - CloudWatch alarms: RDS CPU > 80%, RDS free storage < 10%, ECS task failure rate > 0.
- Update `infra-tf/main.tf` to wire the new modules.
- `terraform validate` + `terraform fmt` clean. DO NOT apply.

## Data touched
- No app-code changes. Pure infra.
- Existing S3 buckets need a lifecycle policy update or replace-on-encryption-change — call out in the module README which resources will do in-place vs replace.

## Roles
- Infra-only story; no app routes.

## Notes
- Blueprint §11 (Terraform IaC).
- Blueprint §12 (encryption at rest with KMS; Object Lock on signed SOW).
- The apply is a separate step — plan needs Finance review because KMS keys
  cost ~$1/month each and CloudTrail data events aren't cheap. Documented
  in the module README.
