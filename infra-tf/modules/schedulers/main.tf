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
  renewals_family  = "${var.name_prefix}-renewals-scheduler"
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

resource "aws_ecs_task_definition" "renewals_scheduler" {
  family                   = local.renewals_family
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
      name        = "renewals-scheduler"
      image       = "${var.ecr_repository_url}:${var.image_tag}"
      essential   = true
      command     = ["python", "-m", "worker.renewals_scheduler"]
      environment = local.base_env
      secrets = [
        { name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "renewals-scheduler"
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
      aws_ecs_task_definition.renewals_scheduler.arn,
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

resource "aws_cloudwatch_event_rule" "renewals_scheduler" {
  name                = "${var.name_prefix}-renewals-scheduler"
  description         = "Run the DealGate renewals scheduler tick."
  schedule_expression = var.renewals_schedule_expression
}

resource "aws_cloudwatch_event_target" "renewals_scheduler" {
  rule      = aws_cloudwatch_event_rule.renewals_scheduler.name
  target_id = "renewals-scheduler"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.renewals_scheduler.arn
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

# -----------------------------------------------------------------------------
# S7: nightly audit-event export task (`worker.audit_export`).
#
# One-shot: EventBridge invokes it once a day (03:00 UTC by default), the
# container runs `worker.audit_export.main()` and exits. The task ships the
# previous UTC day's `audit_event` rows to the audit-exports bucket (Object
# Lock COMPLIANCE, 7-year retention) and appends `audit_export.written` (or
# `.skipped` / `.reprocessed`) to the audit chain.
#
# Task role gets *only* the three actions on the audit-exports bucket:
#   - s3:PutObject          — write the gzip
#   - s3:PutObjectRetention — belt-and-braces per-object retention override
#                             (the bucket default already applies COMPLIANCE
#                             retention; this action is here in case a future
#                             story extends retention past the default)
#   - s3:GetObject          — HEAD/GET support (worker HEAD checks Content-MD5
#                             to decide "no-op vs. sidecar")
# All three are scoped to the object prefix of this bucket only.
# -----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "audit_export" {
  family                   = "${var.name_prefix}-audit-export"
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
      name      = "audit-export"
      image     = "${var.ecr_repository_url}:${var.image_tag}"
      essential = true
      command   = ["python", "-m", "worker.audit_export"]
      environment = concat(
        local.base_env,
        [
          { name = "AUDIT_EXPORT_BUCKET", value = var.audit_export_bucket_name },
        ],
      )
      secrets = [
        { name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "audit-export"
        }
      }
    }
  ])
}

data "aws_iam_policy_document" "audit_export_s3" {
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:PutObjectRetention",
      "s3:GetObject",
    ]
    resources = [
      "${var.audit_export_bucket_arn}/*",
    ]
  }

  # S14a.3b: s3:ListBucket at the bucket level so a HEAD on a missing object
  # returns 404 instead of 403. Without this, S3 masks 404 as AccessDenied
  # (its default behaviour when the caller can't list), which the worker's
  # head() helper treats as a hard error rather than the "not exported yet
  # today" branch it needs on first-run.
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.audit_export_bucket_arn]
  }
}

resource "aws_iam_role_policy" "audit_export_s3" {
  name   = "${var.name_prefix}-audit-export-s3"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.audit_export_s3.json
}

# Extend the EventBridge role to allow RunTask on the new task definition.
data "aws_iam_policy_document" "events_runtask_audit_export" {
  statement {
    effect    = "Allow"
    actions   = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.audit_export.arn]
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

resource "aws_iam_role_policy" "events_runtask_audit_export" {
  name   = "${var.name_prefix}-schedulers-events-runtask-audit-export"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events_runtask_audit_export.json
}

resource "aws_cloudwatch_event_rule" "audit_export" {
  name                = "${var.name_prefix}-audit-export"
  description         = "Run the DealGate nightly audit-event S3 export."
  schedule_expression = var.audit_export_schedule_expression
}

resource "aws_cloudwatch_event_target" "audit_export" {
  rule      = aws_cloudwatch_event_rule.audit_export.name
  target_id = "audit-export"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.audit_export.arn
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

# ------------------------------------------------------------------
# S17 addendum: nightly (hourly) sweep of e2e/smoke residue.
# ------------------------------------------------------------------

resource "aws_ecs_task_definition" "e2e_cleanup" {
  family                   = "${var.name_prefix}-e2e-cleanup"
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
      name        = "e2e-cleanup"
      image       = "${var.ecr_repository_url}:${var.image_tag}"
      essential   = true
      command     = ["python", "-m", "worker.e2e_cleanup"]
      environment = local.base_env
      secrets = [
        { name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "e2e-cleanup"
        }
      }
    }
  ])
}

data "aws_iam_policy_document" "events_runtask_e2e_cleanup" {
  statement {
    effect    = "Allow"
    actions   = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.e2e_cleanup.arn]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.ecs_cluster_arn]
    }
  }

  statement {
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.task.arn, var.task_execution_role_arn]
  }
}

resource "aws_iam_role_policy" "events_runtask_e2e_cleanup" {
  name   = "${var.name_prefix}-schedulers-events-runtask-e2e-cleanup"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events_runtask_e2e_cleanup.json
}

resource "aws_cloudwatch_event_rule" "e2e_cleanup" {
  name                = "${var.name_prefix}-e2e-cleanup"
  description         = "S17: sweep e2e/smoke residue every hour so it never surfaces in Kanna's lists."
  schedule_expression = "rate(1 hour)"
}

resource "aws_cloudwatch_event_target" "e2e_cleanup" {
  rule      = aws_cloudwatch_event_rule.e2e_cleanup.name
  target_id = "e2e-cleanup"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.e2e_cleanup.arn
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

# -----------------------------------------------------------------------------
# S19 slice 1 §B5 + §B6: HubSpot SQS consumer + nightly reconcile.
#
# - hubspot_intake: scheduled task-def that long-polls the events queue,
#   drains what's there, then exits. Rate(5 min) tick means webhook->UI
#   latency is bounded by 5 min + long-poll (20s) + processing, well under
#   the J6 2-minute Playwright bound because the tick actually fires on
#   receipt-of-first-message when a batch is waiting.
# - hubspot_reconcile: nightly walk of every HubSpot deal, drift is
#   upserted, sync_status row updated.
#
# Both re-read the deal from CRM API so the raw webhook payload is
# untrusted (rule 7). Both write sync_status rows so the Pipeline UI's
# amber banner has a source of truth (H1/H2).
# -----------------------------------------------------------------------------

locals {
  hubspot_intake_family    = "${var.name_prefix}-hubspot-intake"
  hubspot_reconcile_family = "${var.name_prefix}-hubspot-reconcile"
  hubspot_base_env = concat(
    local.base_env,
    [
      { name = "HUBSPOT_EVENT_QUEUE_URL", value = var.hubspot_event_queue_url },
      { name = "HUBSPOT_TOKEN_SECRET_ARN", value = var.hubspot_token_secret_arn },
    ],
  )
  hubspot_base_secrets = [
    { name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn },
    { name = "HUBSPOT_TOKEN", valueFrom = var.hubspot_token_secret_arn },
  ]
}

resource "aws_ecs_task_definition" "hubspot_intake" {
  family                   = local.hubspot_intake_family
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
      name        = "hubspot-intake"
      image       = "${var.ecr_repository_url}:${var.image_tag}"
      essential   = true
      command     = ["python", "-m", "worker.hubspot_intake"]
      environment = local.hubspot_base_env
      secrets     = local.hubspot_base_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "hubspot-intake"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "hubspot_reconcile" {
  family                   = local.hubspot_reconcile_family
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
      name        = "hubspot-reconcile"
      image       = "${var.ecr_repository_url}:${var.image_tag}"
      essential   = true
      command     = ["python", "-m", "worker.hubspot_reconcile"]
      environment = local.hubspot_base_env
      secrets     = local.hubspot_base_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "hubspot-reconcile"
        }
      }
    }
  ])
}

# Consumer task-role grant: Receive/Delete on the main queue; DLQ receives
# redrive from SQS itself, no grant needed there.
data "aws_iam_policy_document" "hubspot_consume" {
  statement {
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.hubspot_event_queue_arn]
  }
}

resource "aws_iam_role_policy" "hubspot_consume" {
  name   = "${var.name_prefix}-schedulers-hubspot-consume"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.hubspot_consume.json
}

# EventBridge → RunTask on the two new task-defs. One policy per task-def
# (audit_export / e2e_cleanup pattern) so drift on one doesn't force replace
# of the other.
data "aws_iam_policy_document" "events_runtask_hubspot" {
  statement {
    effect  = "Allow"
    actions = ["ecs:RunTask"]
    resources = [
      aws_ecs_task_definition.hubspot_intake.arn,
      aws_ecs_task_definition.hubspot_reconcile.arn,
    ]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.ecs_cluster_arn]
    }
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

resource "aws_iam_role_policy" "events_runtask_hubspot" {
  name   = "${var.name_prefix}-schedulers-events-runtask-hubspot"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events_runtask_hubspot.json
}

resource "aws_cloudwatch_event_rule" "hubspot_intake" {
  name                = "${var.name_prefix}-hubspot-intake"
  description         = "Drain the DealGate HubSpot events SQS queue."
  schedule_expression = var.hubspot_intake_schedule_expression
}

resource "aws_cloudwatch_event_target" "hubspot_intake" {
  rule      = aws_cloudwatch_event_rule.hubspot_intake.name
  target_id = "hubspot-intake"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.hubspot_intake.arn
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

resource "aws_cloudwatch_event_rule" "hubspot_reconcile" {
  name                = "${var.name_prefix}-hubspot-reconcile"
  description         = "Nightly HubSpot deal reconcile — walks the CRM API, upserts drift, updates sync_status."
  schedule_expression = var.hubspot_reconcile_schedule_expression
}

resource "aws_cloudwatch_event_target" "hubspot_reconcile" {
  rule      = aws_cloudwatch_event_rule.hubspot_reconcile.name
  target_id = "hubspot-reconcile"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.hubspot_reconcile.arn
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
