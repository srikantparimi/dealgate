# -----------------------------------------------------------------------------
# S20 W1 D4 · T32 — HubSpot freshness alarms.
#
# Three alarms guard the sync:
#
#   1. Queue backlog age — main queue oldest visible message. Alarms when
#      the age exceeds `backlog_age_threshold_seconds` (default 300s /
#      5 min). Sampled from `ApproximateAgeOfOldestMessage` on the main
#      queue.
#
#   2. DLQ non-empty — alarms when the DLQ has ANY messages
#      (`ApproximateNumberOfMessagesVisible >= 1`). A poison event should
#      never sit unattended.
#
#   3. Processing lag — alarms when the continuous consumer hasn't logged
#      a "hubspot_worker_run_complete" line in more than
#      `lag_alarm_seconds` (default 300s). Uses a metric filter on the
#      schedulers log group so we don't need a custom metric emitted from
#      the worker.
#
# All three alarm into the shared `hubspot_alarms_topic_arn` if wired.
# When the variable is empty (default), alarms are still created but with
# an empty action list — safe to `terraform apply` before the SNS topic
# exists.
# -----------------------------------------------------------------------------

variable "hubspot_alarms_topic_arn" {
  description = "SNS topic ARN for the HubSpot freshness alarms. Empty string means no notification action (alarm still transitions state and CloudWatch console reflects it)."
  type        = string
  default     = ""
}

variable "backlog_age_threshold_seconds" {
  description = "Age threshold for the main HubSpot events queue backlog alarm. 300 seconds matches directive §4 (backlog age > 5 min)."
  type        = number
  default     = 300
}

variable "lag_alarm_seconds" {
  description = "Alarm if the continuous consumer has not logged a completed loop within this window. 300 s = the 5-minute end-to-end SLO plus a safety buffer."
  type        = number
  default     = 300
}

variable "hubspot_events_queue_name" {
  description = "Main HubSpot events queue NAME (SQS dimension), matching the queue passed into hubspot_event_queue_url. Used by CloudWatch alarms that read AWS/SQS metrics."
  type        = string
  # S20 Lead default so root main.tf doesn't have to wire the argument
  # until W1's freshness-alarms slice ships in Session 2. Value matches
  # the queue name written by modules/hubspot.
  default = "officeapp-dev-hubspot-events"
}

variable "hubspot_events_dlq_name" {
  description = "DLQ NAME for the HubSpot events pipeline (SQS dimension). Alarms when > 0 messages visible."
  type        = string
  default     = "officeapp-dev-hubspot-events-dlq"
}

locals {
  hubspot_alarm_actions = length(var.hubspot_alarms_topic_arn) > 0 ? [var.hubspot_alarms_topic_arn] : []
  ok_actions            = local.hubspot_alarm_actions
}

# ---- 1. Backlog age -----------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "hubspot_backlog_age" {
  alarm_name          = "${var.name_prefix}-hubspot-events-backlog-age"
  alarm_description   = "HubSpot events queue backlog age (oldest visible message) exceeds ${var.backlog_age_threshold_seconds}s. Directive S20 §4 D4 threshold."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = var.backlog_age_threshold_seconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = var.hubspot_events_queue_name
  }

  alarm_actions = local.hubspot_alarm_actions
  ok_actions    = local.ok_actions
}

# ---- 2. DLQ non-empty ---------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "hubspot_dlq_nonzero" {
  alarm_name          = "${var.name_prefix}-hubspot-events-dlq-nonzero"
  alarm_description   = "HubSpot DLQ has messages. A poison event should not sit here unattended; the on-call runbook is in docs/runbooks/hubspot-dlq.md."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = var.hubspot_events_dlq_name
  }

  alarm_actions = local.hubspot_alarm_actions
  ok_actions    = local.ok_actions
}

# ---- 3. Processing lag (log-metric filter on run-complete lines) --------
resource "aws_cloudwatch_log_metric_filter" "hubspot_worker_complete" {
  name           = "${var.name_prefix}-hubspot-worker-complete"
  log_group_name = aws_cloudwatch_log_group.schedulers.name
  pattern        = "\"hubspot_worker_run_complete\""

  metric_transformation {
    name          = "HubSpotWorkerRunComplete"
    namespace     = "DealGate/HubSpot"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "hubspot_processing_lag" {
  alarm_name          = "${var.name_prefix}-hubspot-processing-lag"
  alarm_description   = "HubSpot continuous consumer hasn't logged a completed loop within ${var.lag_alarm_seconds}s. Either the service is unhealthy or the queue has been silent for a long time; check the continuous ECS service."
  namespace           = "DealGate/HubSpot"
  metric_name         = "HubSpotWorkerRunComplete"
  statistic           = "Sum"
  period              = var.lag_alarm_seconds
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  alarm_actions = local.hubspot_alarm_actions
  ok_actions    = local.ok_actions
}
