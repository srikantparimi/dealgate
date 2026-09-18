# -----------------------------------------------------------------------------
# S2-E3 Wave 2: alert scheduler + notification sender scheduled tasks.
#
# Two thin workers share the API image (same ECR repo, different `command`
# override at task launch time):
#
#   - worker.alert_scheduler        — runs one tick per invocation, produced
#                                     by an EventBridge scheduled rule every
#                                     5 minutes.
#   - worker.notification_sender    — drains the outbox; also invoked on a
#                                     5-minute schedule so a stalled row
#                                     ships within one window.
#
# Both tasks run on the API's ECS cluster to avoid a second Fargate
# footprint. The task role grants exactly two runtime perms: SES SendEmail
# and CloudWatch log writes. Secrets (POSTGRES_URL) are injected via the
# execution role, same as the API service.
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  scheduler_family = "${var.name_prefix}-alert-scheduler"
  sender_family    = "${var.name_prefix}-notification-sender"
  base_env = [
    { name = "DEALGATE_ENV", value = var.env },
    { name = "AWS_REGION", value = var.region },
    { name = "COGNITO_REGION", value = var.region },
    { name = "COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id },
    { name = "COGNITO_CLIENT_ID", value = var.cognito_client_id },
    { name = "SES_FROM_ADDRESS", value = var.ses_from_address },
    { name = "SALES_LEADER_EMAIL", value = var.sales_leader_email },
    { name = "LEGAL_LEADER_EMAIL", value = var.legal_leader_email },
    { name = "FINANCE_LEADER_EMAIL", value = var.finance_leader_email },
    { name = "HR_LEADER_EMAIL", value = var.hr_leader_email },
    { name = "DELIVERY_LEADER_EMAIL", value = var.delivery_leader_email },
    { name = "TEAMS_WEBHOOK_URL", value = var.teams_webhook_url },
    { name = "SLACK_WEBHOOK_URL", value = var.slack_webhook_url },
  ]
}

# ------------------------------------------------------------------
# Task role: SES send + logs. Keep separate from the API's task role so
# a scheduler bug can't accidentally read/write API-owned resources.
# ------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-schedulers-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "ses_send" {
  statement {
    effect = "Allow"
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail",
    ]
    # Scope by verified identity ARN. The identity is created below.
    resources = [
      "arn:${data.aws_partition.current.partition}:ses:${var.region}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_from_address}",
    ]
  }
}

resource "aws_iam_role_policy" "ses_send" {
  name   = "${var.name_prefix}-schedulers-ses"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.ses_send.json
}

# ------------------------------------------------------------------
# SES verified identity (sandbox — the integrator must click the link
# in the verification email before the first send succeeds).
# ------------------------------------------------------------------

resource "aws_ses_email_identity" "sender" {
  email = var.ses_from_address
}

# ------------------------------------------------------------------
# Log group shared by both scheduled tasks.
# ------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "schedulers" {
  name              = "/officeapp/${var.env}/schedulers"
  retention_in_days = var.log_retention_days
}

# ------------------------------------------------------------------
# Task definitions — same image, different container command.
# ------------------------------------------------------------------

resource "aws_ecs_task_definition" "alert_scheduler" {
  family                   = local.scheduler_family
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name        = "alert-scheduler"
      image       = "${var.ecr_repository_url}:${var.image_tag}"
      essential   = true
      command     = ["python", "-m", "worker.alert_scheduler"]
      environment = local.base_env
      secrets = [
        { name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "alert-scheduler"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "notification_sender" {
  family                   = local.sender_family
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name        = "notification-sender"
      image       = "${var.ecr_repository_url}:${var.image_tag}"
      essential   = true
      command     = ["python", "-m", "worker.notification_sender"]
      environment = local.base_env
      secrets = [
        { name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "notification-sender"
        }
      }
    }
  ])
}

# ------------------------------------------------------------------
# EventBridge Scheduler: role + rate rules that launch each task.
# ------------------------------------------------------------------

data "aws_iam_policy_document" "events_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "events" {
  name               = "${var.name_prefix}-schedulers-events"
  assume_role_policy = data.aws_iam_policy_document.events_assume.json
}

# Least-privilege: only allow RunTask on the two task defs, and pass the
# task + execution roles. Scoping by ARN keeps the events role blast-radius
# limited to the schedulers.
data "aws_iam_policy_document" "events_runtask" {
  statement {
    effect  = "Allow"
    actions = ["ecs:RunTask"]
    resources = [
      aws_ecs_task_definition.alert_scheduler.arn,
      aws_ecs_task_definition.notification_sender.arn,
    ]
  }

  statement {
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.task.arn,
      var.task_execution_role_arn,
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "events_runtask" {
  name   = "${var.name_prefix}-schedulers-events-runtask"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events_runtask.json
}

resource "aws_cloudwatch_event_rule" "alert_scheduler" {
  name                = "${var.name_prefix}-alert-scheduler"
  description         = "Run the DealGate alert scheduler tick."
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "alert_scheduler" {
  rule      = aws_cloudwatch_event_rule.alert_scheduler.name
  target_id = "alert-scheduler"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.alert_scheduler.arn
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

resource "aws_cloudwatch_event_rule" "notification_sender" {
  name                = "${var.name_prefix}-notification-sender"
  description         = "Drain the DealGate notification outbox."
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "notification_sender" {
  rule      = aws_cloudwatch_event_rule.notification_sender.name
  target_id = "notification-sender"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.notification_sender.arn
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
