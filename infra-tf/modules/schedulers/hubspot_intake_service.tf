# -----------------------------------------------------------------------------
# S20 W1 D4 · §4 — continuous HubSpot intake ECS service.
#
# Replaces the every-5-minute EventBridge-scheduled task-def with a
# long-running Fargate service that drains the queue continuously. See
# `docs/directives/s20-overnight.md` §4 for the cutover plan. The service
# is deployed with `desired_count = 0` so applying this file has zero
# behavioural change; the Lead flips the count to 1 during D5 deploy
# after confirming the queue is empty and disabling the schedule rule.
#
# Why a new file (not additions to main.tf):
#   - Kept isolated so a rollback is `terraform destroy -target=
#     module.schedulers.aws_ecs_service.hubspot_intake_continuous` without
#     ripping through the legacy scheduled task-def.
#   - Terraform plan output stays readable — every resource in this
#     file is new (no `~` updates to existing task-defs).
# -----------------------------------------------------------------------------

# ---- Task definition -----------------------------------------------------
# Identical container command + image as the scheduled variant so the
# consumer code runs unchanged. The tick's soft-budget env is deliberately
# uncapped ("0" means "loop forever") so the loop in
# ``worker.hubspot_intake.run_once`` keeps draining until the process is
# killed. The container is essential so a crash triggers ECS restart.

resource "aws_ecs_task_definition" "hubspot_intake_continuous" {
  family                   = "${var.name_prefix}-hubspot-intake-continuous"
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
      name      = "hubspot-intake-continuous"
      image     = "${var.ecr_repository_url}:${var.image_tag}"
      essential = true
      command   = ["python", "-m", "worker.hubspot_intake"]
      environment = concat(
        local.hubspot_base_env,
        [
          # A single tick soft-budget of 24 h — the outer supervisor
          # (ECS) will restart the task when it exits or crashes; the
          # long-lived process just keeps looping.
          { name = "HUBSPOT_WORKER_SOFT_BUDGET", value = "86400" },
        ],
      )
      secrets = local.hubspot_base_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.schedulers.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "hubspot-intake-continuous"
        }
      }
    }
  ])
}

# ---- ECS service ---------------------------------------------------------
# desired_count intentionally 0 on first apply. Cutover flips to 1 via a
# variable override once the schedule rule has been disabled and the
# queue is drained (§4 D4 step 3).

variable "hubspot_intake_service_desired_count" {
  description = "Desired count for the continuous HubSpot intake service. Kept at 0 on first apply so the schedule-rule cutover (S20 §4 D4) is a separate, reversible flip."
  type        = number
  default     = 0
}

resource "aws_ecs_service" "hubspot_intake_continuous" {
  name            = "${var.name_prefix}-hubspot-intake"
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.hubspot_intake_continuous.arn
  desired_count   = var.hubspot_intake_service_desired_count
  launch_type     = "FARGATE"

  # No load balancer, no service registry — the task only talks OUTBOUND
  # to SQS + HubSpot + the DB. Health is measured by watermark advance,
  # not by an HTTP probe.
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = var.task_security_group_ids
    assign_public_ip = false
  }

  # Deployment tuning: at most one task at a time. A rolling replace
  # briefly drops throughput while the new task boots, which is fine
  # because SQS holds messages during the swap.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  # A stopped task exits with 0 when the worker's soft budget ends; ECS
  # restarts it immediately. If the code panics, the restart is capped
  # by ECS's default back-off.
  enable_ecs_managed_tags = true
  propagate_tags          = "SERVICE"

  # Ignore desired_count in normal drift so an on-call `aws ecs update-
  # service --desired-count 0` incident scale-down survives a terraform
  # apply without immediately being reverted. Rule 12/15 still requires
  # the *cutover* to go through terraform, but a paging response is a
  # separate story.
  lifecycle {
    ignore_changes = [desired_count]
  }
}

# ---- CloudWatch freshness alarms (D4, T32) ------------------------------
# The alarms sample the sync_status columns via CloudWatch metric filters
# on the schedulers log group. See `hubspot_freshness_alarms.tf`.
