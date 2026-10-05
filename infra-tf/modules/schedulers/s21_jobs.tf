variable "tenant_id" {
  type        = string
  description = "Explicit application tenant, shared with the API. Defaults to this single-tenant stack name."
  default     = ""
}

variable "s21_jobs_enabled" {
  type        = bool
  description = "Activate Forecast and deletion cleanup only in a reviewed whole-root release plan."
  default     = false
}

locals {
  s21_jobs = {
    forecast_plans   = "Recalculate persisted tenant-scoped Forecast plans."
    deletion_cleanup = "Remove exact owned SOW object versions from durable cleanup jobs."
  }
  s21_sow_bucket        = "${var.name_prefix}-sows-${data.aws_caller_identity.current.account_id}"
  s21_agreements_bucket = "${var.name_prefix}-agreements-${data.aws_caller_identity.current.account_id}"
}

resource "aws_iam_role" "s21_worker" {
  for_each           = local.s21_jobs
  name               = "${var.name_prefix}-${replace(each.key, "_", "-")}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "s21_cleanup_s3" {
  statement {
    actions   = ["s3:ListBucketVersions"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${local.s21_sow_bucket}", "arn:${data.aws_partition.current.partition}:s3:::${local.s21_agreements_bucket}"]
  }
  statement {
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${local.s21_sow_bucket}/*", "arn:${data.aws_partition.current.partition}:s3:::${local.s21_agreements_bucket}/*"]
  }
}

resource "aws_iam_role_policy" "s21_cleanup_s3" {
  name   = "${var.name_prefix}-deletion-owned-object-versions"
  role   = aws_iam_role.s21_worker["deletion_cleanup"].id
  policy = data.aws_iam_policy_document.s21_cleanup_s3.json
}

resource "aws_ecs_task_definition" "s21_job" {
  for_each                 = local.s21_jobs
  family                   = "${var.name_prefix}-${replace(each.key, "_", "-")}"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = aws_iam_role.s21_worker[each.key].arn
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name      = each.key
    image     = "${var.ecr_repository_url}:${var.image_tag}"
    essential = true
    command   = ["python", "-m", "worker.${each.key}"]
    environment = concat(local.base_env, [
      { name = "SOW_BUCKET", value = local.s21_sow_bucket },
      { name = "AGREEMENTS_BUCKET", value = local.s21_agreements_bucket },
    ])
    secrets = [{ name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = each.key
      }
    }
  }])
}

data "aws_iam_policy_document" "events_s21_jobs" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = [for definition in aws_ecs_task_definition.s21_job : definition.arn]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.ecs_cluster_arn]
    }
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = concat([var.task_execution_role_arn], [for role in aws_iam_role.s21_worker : role.arn])
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "events_s21_jobs" {
  name   = "${var.name_prefix}-events-s21-jobs"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events_s21_jobs.json
}

resource "aws_cloudwatch_event_rule" "s21_job" {
  for_each            = local.s21_jobs
  name                = "${var.name_prefix}-${replace(each.key, "_", "-")}"
  description         = each.value
  schedule_expression = "rate(1 minute)"
  state               = var.s21_jobs_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "s21_job" {
  for_each  = local.s21_jobs
  rule      = aws_cloudwatch_event_rule.s21_job[each.key].name
  target_id = each.key
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn
  ecs_target {
    task_definition_arn = aws_ecs_task_definition.s21_job[each.key].arn
    launch_type         = "FARGATE"
    task_count          = 1
    platform_version    = "LATEST"
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = var.task_security_group_ids
      assign_public_ip = false
    }
  }
}
