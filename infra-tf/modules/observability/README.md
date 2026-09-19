# modules/observability

Audit + intrusion detection + alarm layer. Wired into the stack in S7.

## Resources provisioned

- `aws_s3_bucket.cloudtrail` — private, versioned, Object-Lock-enabled
  (COMPLIANCE, 7y default), SSE-KMS.
- `aws_s3_bucket_versioning.cloudtrail`
- `aws_s3_bucket_server_side_encryption_configuration.cloudtrail`
- `aws_s3_bucket_public_access_block.cloudtrail`
- `aws_s3_bucket_object_lock_configuration.cloudtrail`
- `aws_s3_bucket_policy.cloudtrail`
- `aws_cloudtrail.audit` — multi-region, log file validation ON, KMS
  encrypted, global service events ON.
- `aws_guardduty_detector.this` — S3 logs enabled, Kubernetes + EBS malware
  scan explicitly OFF to keep cost predictable.
- `aws_sns_topic.alerts` — KMS-encrypted, receives every alarm.
- `aws_sns_topic_subscription.alerts_email` — email subscription; recipient
  must confirm.
- `aws_cloudwatch_metric_alarm.rds_cpu` — > 80% for 15 minutes.
- `aws_cloudwatch_metric_alarm.rds_free_storage` — < 10% of allocated.
- `aws_cloudwatch_metric_alarm.api_task_failures` — RunningTaskCount < 1
  for 3 minutes.

## Cost (us-east-2, dev-sized workload)

- **CloudTrail**: management events are free (one trail per account).
  Data events are NOT enabled here; if you turn them on for the sows
  bucket, budget ~$0.10 per 100k events.
- **CloudTrail S3 storage**: log volume is small (< 100 MB / month on a
  quiet dev account). Storage cost ~pennies. Object Lock retention of 7
  years means those pennies compound — plan on ~$0.10 – $1 / month long
  term.
- **GuardDuty**: variable — driven by CloudTrail events scanned + S3
  requests. Dev typically $5 – $15 / month.
- **SNS**: $0.50 / 1M publishes; free tier covers dev alarm traffic.
- **CloudWatch alarms**: $0.10 / alarm / month → **$0.30** for the three.

**Rough total for dev: ~$10 – $20 / month**, dominated by GuardDuty.

## Migration caveats

### CloudTrail bucket cannot be flipped to Object Lock after creation

Same S3 rule as the sows bucket in `modules/storage`: `object_lock_enabled
= true` is a create-time attribute. Terraform will replace the bucket if
you flip it on an existing one, which loses every log file. If you are
adopting this module against a pre-existing CloudTrail bucket, either:

- Accept the replacement (CloudTrail logs are recreated forward from the
  apply moment; historical logs are gone unless you copied them out).
- Do a manual migration: rename the old bucket in the CLI, `terraform
  apply` to create the new one, `aws s3 sync` old → new.

### COMPLIANCE-mode retention is irreversible

A COMPLIANCE-mode retention lock **cannot be shortened or removed** by
any principal — including the AWS account root. If you set it to 7 years
by mistake, every object gets a 7-year retention. Double-check
`cloudtrail_retention_years` before the first apply.

### Email subscription requires manual confirmation

`aws_sns_topic_subscription` for email starts as `PendingConfirmation`.
The recipient must click the AWS-hosted confirmation link within 3 days,
or the subscription is dropped. Terraform state will show the ARN as
`pending confirmation` until this happens; that is expected and not a
drift.

### GuardDuty detector already exists

There can only be **one detector per region per account**. If GuardDuty
was enabled by hand or by another module, `terraform apply` will fail
with `BadRequestException: Detector already exists`. Import it first:

```
terraform import module.observability.aws_guardduty_detector.this <detector-id>
```

Find the id with `aws guardduty list-detectors`.

## Wiring

```hcl
module "observability" {
  source                    = "./modules/observability"
  name_prefix               = local.name_prefix
  region                    = var.region
  account_id                = data.aws_caller_identity.current.account_id
  kms_key_arn               = module.kms.key_arn
  rds_instance_id           = "${local.name_prefix}-db"
  rds_allocated_storage_gb  = 20
  ecs_cluster_name          = module.api.cluster_name
  ecs_service_name          = module.api.service_name
  # alert_email defaults to srikantp@smartek21.com
}
```
