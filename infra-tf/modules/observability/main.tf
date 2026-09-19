# -----------------------------------------------------------------------------
# S7: CloudTrail + GuardDuty + CloudWatch alarms. This is the "we can tell
# something is on fire before Finance calls us" layer.
#
# Cost note (dev):
#   - CloudTrail: management events are free. This module does NOT enable
#     data events (S3 object-level, Lambda invoke) — those are $0.10 per
#     100k events and can run hot fast. Enable them per-bucket via a
#     `event_selector` if/when we need per-object audit for signed SOWs.
#   - GuardDuty: pay-per-CloudTrail-event scanned + per-GB of VPC flow
#     logs. This module enables S3-logs only (cheap); Kubernetes and EBS
#     malware scan are turned off explicitly to keep the bill flat. Rough:
#     $5 – $15 / month for a small account.
#   - SNS: $0.50 / 1M requests, plus per-alarm email delivery (essentially
#     free at this volume).
#
# The CloudTrail bucket has Object Lock in COMPLIANCE mode with 7-year
# retention — auditor default. COMPLIANCE (unlike GOVERNANCE) cannot be
# overridden by any principal, including root. Do not turn this on in a
# throwaway sandbox account by accident.
# -----------------------------------------------------------------------------

# ----- CloudTrail bucket ----------------------------------------------------

resource "aws_s3_bucket" "cloudtrail" {
  bucket        = "${var.name_prefix}-cloudtrail-${var.account_id}"
  force_destroy = false

  # COMPLIANCE-mode Object Lock requires this flag at create time. See caveat
  # in modules/storage/main.tf — flipping this on an existing bucket forces
  # a destroy+recreate, which loses every object.
  object_lock_enabled = true

  tags = {
    Name    = "${var.name_prefix}-cloudtrail"
    Purpose = "CloudTrail multi-region audit log with 7-year WORM retention"
  }
}

resource "aws_s3_bucket_versioning" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.cloudtrail_retention_years * 365
    }
  }

  depends_on = [aws_s3_bucket_versioning.cloudtrail]
}

# CloudTrail writes as the service principal; the bucket policy must grant it.
data "aws_iam_policy_document" "cloudtrail_bucket" {
  statement {
    sid    = "AWSCloudTrailAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail.arn]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = ["arn:aws:cloudtrail:${var.region}:${var.account_id}:trail/${var.name_prefix}-audit"]
    }
  }

  statement {
    sid    = "AWSCloudTrailWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${var.account_id}/*"]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = ["arn:aws:cloudtrail:${var.region}:${var.account_id}:trail/${var.name_prefix}-audit"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id
  policy = data.aws_iam_policy_document.cloudtrail_bucket.json
}

# ----- CloudTrail trail -----------------------------------------------------

resource "aws_cloudtrail" "audit" {
  name           = "${var.name_prefix}-audit"
  s3_bucket_name = aws_s3_bucket.cloudtrail.id

  # Multi-region so a create-in-us-west-2 escapes doesn't slip past us.
  is_multi_region_trail = true

  # Include IAM / STS / global service events (only meaningful when
  # multi_region + this flag are both on).
  include_global_service_events = true

  # Prevent tampering — CloudTrail signs its log files and publishes a
  # digest bundle you can verify with `aws cloudtrail validate-logs`.
  enable_log_file_validation = true

  # Encrypt the log files themselves under the CMK.
  kms_key_id = var.kms_key_arn

  tags = {
    Name = "${var.name_prefix}-audit"
  }

  depends_on = [aws_s3_bucket_policy.cloudtrail]
}

# ----- GuardDuty ------------------------------------------------------------

resource "aws_guardduty_detector" "this" {
  enable = true

  # Keep the enabled data-source set small for cost. Kubernetes audit logs
  # and EBS malware scanning are the two big spend drivers; disabled here.
  datasources {
    s3_logs {
      enable = true
    }
    kubernetes {
      audit_logs {
        enable = false
      }
    }
    malware_protection {
      scan_ec2_instance_with_findings {
        ebs_volumes {
          enable = false
        }
      }
    }
  }

  tags = {
    Name = "${var.name_prefix}-guardduty"
  }
}

# ----- SNS alerts topic -----------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name              = "${var.name_prefix}-alerts"
  kms_master_key_id = var.kms_key_arn

  tags = {
    Name = "${var.name_prefix}-alerts"
  }
}

# NOTE: email subscriptions require the recipient to click a confirmation
# link. Until they do, `aws_sns_topic_subscription.pending_confirmation`
# will read `true` in the state. That is expected.
resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ----- CloudWatch alarms ----------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.name_prefix}-rds-cpu"
  alarm_description   = "RDS ${var.rds_instance_id} CPU sustained > 80% for 15 minutes. Likely a hot query or a runaway migration."
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 10% of allocated_storage in bytes. FreeStorageSpace is emitted in bytes.
locals {
  rds_free_storage_threshold_bytes = var.rds_allocated_storage_gb * 1024 * 1024 * 1024 * 0.1
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  alarm_name          = "${var.name_prefix}-rds-free-storage"
  alarm_description   = "RDS ${var.rds_instance_id} free storage < 10% of allocated. Grow the volume or archive."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  threshold           = local.rds_free_storage_threshold_bytes
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# ECS RunningTaskCount dips below desired_count → task is failing to stay up.
# We track this via the (undocumented but stable) `DesiredTaskCount` +
# `RunningTaskCount` pair via metric math would be nicer, but the simplest
# thing that works out of the box is to alarm on `RunningTaskCount = 0`.
resource "aws_cloudwatch_metric_alarm" "api_task_failures" {
  alarm_name          = "${var.name_prefix}-api-task-failures"
  alarm_description   = "ECS API service ${var.ecs_service_name} has zero running tasks. Fargate is failing to keep the service up."
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
