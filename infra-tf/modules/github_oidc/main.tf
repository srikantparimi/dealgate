data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

# Look up the OIDC provider if it already exists. `try` swallows the "not
# found" error so we can gate creation on the boolean variable.
data "aws_iam_openid_connect_provider" "existing" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.existing[0].arn
}

data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      # Allow any branch/tag/PR/environment inside the named repo. Tighten to
      # `repo:${var.github_repo}:ref:refs/heads/main` for prod.
      values = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.name_prefix}-gha-deploy"
  description          = "GitHub Actions deploy role for ${var.github_repo} -> ${var.name_prefix}"
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  max_session_duration = 3600
}

# ECR push
data "aws_iam_policy_document" "ecr" {
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:ListImages",
    ]
    resources = [var.ecr_repository_arn]
  }
}

# ECS deploy + one-off run-task
data "aws_iam_policy_document" "ecs" {
  statement {
    effect = "Allow"
    actions = [
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeTasks",
      "ecs:ListTasks",
      "ecs:RegisterTaskDefinition",
      "ecs:UpdateService",
      "ecs:RunTask",
      "ecs:StopTask",
    ]
    resources = ["*"] # ECS APIs are broadly *-scoped; gated below by iam:PassRole
  }

  statement {
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [
      var.task_execution_role_arn,
      var.task_role_arn,
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# S3 SPA sync
data "aws_iam_policy_document" "s3" {
  statement {
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [var.web_bucket_arn]
  }
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:GetObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.web_bucket_arn}/*"]
  }
}

# CloudFront invalidation
data "aws_iam_policy_document" "cloudfront" {
  statement {
    effect = "Allow"
    actions = [
      "cloudfront:CreateInvalidation",
      "cloudfront:GetInvalidation",
      "cloudfront:ListInvalidations",
    ]
    resources = [var.cloudfront_distribution_arn]
  }
}

resource "aws_iam_role_policy" "ecr" {
  name   = "${var.name_prefix}-gha-ecr"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.ecr.json
}

resource "aws_iam_role_policy" "ecs" {
  name   = "${var.name_prefix}-gha-ecs"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.ecs.json
}

resource "aws_iam_role_policy" "s3" {
  name   = "${var.name_prefix}-gha-s3"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.s3.json
}

resource "aws_iam_role_policy" "cloudfront" {
  name   = "${var.name_prefix}-gha-cloudfront"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.cloudfront.json
}
