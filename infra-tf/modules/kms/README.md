# modules/kms

Customer-managed KMS key that encrypts every stateful resource in the DealGate stack.

## Resources provisioned

- `aws_kms_key.data` — symmetric CMK, rotation ON (annual).
- `aws_kms_alias.data` — stable alias `alias/officeapp-<env>-data`.

## Key policy

1. **Account root — full admin.** Standard AWS default; required so IAM
   policies (Terraform, break-glass admins) can manage the key.
2. **Delegated service usage** via `kms:ViaService` for
   `s3.<region>.amazonaws.com`, `secretsmanager.<region>.amazonaws.com`,
   `rds.<region>.amazonaws.com`. Any principal in the account whose IAM
   policy allows the KMS action can use the key, but only when the request
   comes through one of those services. New S3 buckets / secrets in this
   account inherit access automatically.
3. **Direct ECS-task-role grant** for `kms:GenerateDataKey`, `kms:Decrypt`,
   `kms:DescribeKey`. That is what the API task needs to PUT/GET encrypted
   S3 objects and read the DB URL / JWT secrets on start.

## Cost

- ~**$1.00 / key / month** (us-east-2).
- KMS API requests: $0.03 per 10,000 (Encrypt/Decrypt/GenerateDataKey).
  Every S3 PUT/GET touches the key once; Secrets Manager caches for ~5m.
  A dev workload ($< a few hundred k requests/month) is another $0.01 – $1.

Rough budget for dev: **~$1 – $2 / month** total.

## Migration caveats

### Existing S3 buckets (agreements, sows, web)

Switching an existing bucket from `AES256` to `aws:kms` is a
**bucket-property update** — the bucket resource is not replaced. Existing
objects **keep** their old encryption (AES-256 at rest); new PUTs use the
CMK. This is safe and non-destructive; no data migration required.

If you want existing objects re-encrypted under the CMK, run a batch
`aws s3 cp s3://bucket/prefix s3://bucket/prefix --sse aws:kms --sse-kms-key-id <arn> --recursive`
after the apply.

### Existing RDS instance

**RDS does not support changing the encryption key of an existing instance
in place.** If the instance was created with `storage_encrypted = true`
against the *default* AWS-managed key (or with a different CMK), moving
onto this CMK requires:

1. `aws rds create-db-snapshot --db-instance-identifier officeapp-dev-db --db-snapshot-identifier officeapp-dev-preS7`
2. `aws rds copy-db-snapshot --source-db-snapshot-identifier officeapp-dev-preS7 --target-db-snapshot-identifier officeapp-dev-preS7-kms --kms-key-id <new-cmk-arn>`
3. `aws rds restore-db-instance-from-db-snapshot --db-instance-identifier officeapp-dev-db-new --db-snapshot-identifier officeapp-dev-preS7-kms --db-subnet-group-name officeapp-dev-db-subnets --vpc-security-group-ids <sg-id>` (mirror the original instance's class, storage, parameter group).
4. Swap the DNS / secret to point at the new endpoint (or delete the old
   instance and rename the new one to the original identifier during a
   maintenance window).
5. Run `terraform import` on the new instance if you want state to line up,
   or run `terraform apply` with the KMS wiring on a **fresh account**
   (staging / prod) where this dance is not needed.

For dev, the simplest path is: schedule a short maintenance window, take
the snapshot, drop the instance, `terraform apply` with the KMS wiring
(clean create), restore from the copied snapshot. Alembic then re-runs
from empty; app data in dev is throwaway.

### Secrets Manager

Existing secrets support `kms_key_id` updates in place. First read after
the switch decrypts against the new key. No re-write of secret material
needed.

## Wiring

```hcl
module "kms" {
  source            = "./modules/kms"
  name_prefix       = local.name_prefix
  region            = var.region
  account_id        = data.aws_caller_identity.current.account_id
  ecs_task_role_arn = module.api.task_role_arn
}
```

Consumers pass `kms_key_arn = module.kms.key_arn` and reference the alias
where possible so the underlying key id can rotate.
