# -----------------------------------------------------------------------------
# S7: Customer-managed KMS key that encrypts every stateful resource in this
# stack — S3 (agreements, sows, web), RDS, Secrets Manager. One key per env
# keeps blast radius small and lets us rotate independently.
#
# Key policy shape (deliberately different from the AWS-managed default):
#   1. Account root has full admin — required so IAM policies (Terraform,
#      break-glass admins) can actually manage the key.
#   2. Any principal in this account can call GenerateDataKey / Decrypt /
#      Encrypt / DescribeKey when the request comes *via* one of the trusted
#      AWS services (S3, RDS, Secrets Manager) in this region. That is the
#      standard "delegate through the service" pattern — the ECS task role's
#      IAM policy (attached in modules/api) grants the kms:* actions; this
#      key policy then permits them at the resource side, scoped by
#      kms:ViaService. Putting the task-role principal directly in this
#      policy would create a kms -> api -> secrets -> kms module cycle.
#   3. CloudFront service principal, scoped by AWS:SourceAccount, so the SPA
#      distribution can decrypt SSE-KMS objects in the web bucket via OAC.
#
# Key rotation is ON (annual). Alias is stable — resources reference the alias
# ARN via the module output, so a key replacement is a matter of pointing the
# alias at a new key id.
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "key" {
  # 1. Full admin for the account root.
  statement {
    sid       = "EnableIAMUserPermissions"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.account_id}:root"]
    }
  }

  # 2. Delegate to IAM: anyone in this account whose IAM policy allows the
  # action can use this key, but only when the call is proxied through the
  # named AWS service in this region.
  statement {
    sid    = "AllowUseViaAWSServices"
    effect = "Allow"

    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:CallerAccount"
      values   = [var.account_id]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values = [
        "s3.${var.region}.amazonaws.com",
        "secretsmanager.${var.region}.amazonaws.com",
        "rds.${var.region}.amazonaws.com",
      ]
    }
  }

  # 3. CloudFront service principal — required so the SPA distribution can
  # decrypt SSE-KMS objects in the web bucket via OAC. Scoped to the account
  # via AWS:SourceAccount so a CF distribution outside this account cannot
  # ride the grant. The per-distribution ARN condition would create a
  # kms<->web module cycle (kms needs the distribution ARN; web needs the
  # key ARN); account-scoping is the pragmatic compromise for a single-tenant
  # account.
  statement {
    sid    = "AllowCloudFrontOACDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
    ]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_kms_key" "data" {
  description              = "Customer-managed key for ${var.name_prefix} S3 + RDS + Secrets Manager encryption at rest."
  key_usage                = "ENCRYPT_DECRYPT"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  enable_key_rotation      = true
  deletion_window_in_days  = var.deletion_window_in_days

  policy = data.aws_iam_policy_document.key.json

  tags = {
    Name = "${var.name_prefix}-data"
  }
}

resource "aws_kms_alias" "data" {
  name          = "alias/${var.name_prefix}-data"
  target_key_id = aws_kms_key.data.key_id
}
