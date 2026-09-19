variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "env" {
  description = "Environment slug written into DEALGATE_ENV."
  type        = string
}

variable "region" {
  description = "AWS region; forwarded into task env + EventBridge target."
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ECS cluster the scheduled task runs on. Reuse the API cluster to avoid a second Fargate footprint."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for the Fargate scheduler task."
  type        = list(string)
}

variable "task_security_group_ids" {
  description = "Security groups for the scheduler task (share the API's egress SG so SES / RDS are reachable)."
  type        = list(string)
}

variable "ecr_repository_url" {
  description = "ECR repo URL for the worker image (same image as the API)."
  type        = string
}

variable "image_tag" {
  description = "Image tag CI last pushed; the schedule always launches this tag."
  type        = string
}

variable "db_url_secret_arn" {
  description = "Secrets Manager ARN for POSTGRES_URL. Injected into the task."
  type        = string
}

variable "task_execution_role_arn" {
  description = "Reuse the API's execution role — it already has pull + secrets + logs perms."
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Passed through as env so the shared bootstrap can construct the auth deps if needed."
  type        = string
  default     = ""
}

variable "cognito_client_id" {
  description = "Passed through as env for the same reason."
  type        = string
  default     = ""
}

variable "cpu" {
  description = "Fargate CPU units. 256 is enough for the scheduler tick."
  type        = number
  default     = 256
}

variable "memory" {
  description = "Fargate memory (MiB)."
  type        = number
  default     = 512
}

variable "ses_from_address" {
  description = "Verified SES sender address; also created as an SES identity by this module."
  type        = string
  default     = "srikantp@smartek21.com"
}

variable "sales_leader_email" {
  description = "Env value for SALES_LEADER_EMAIL — the Sales function head."
  type        = string
  default     = ""
}

variable "legal_leader_email" {
  description = "Env value for LEGAL_LEADER_EMAIL — the Legal function head."
  type        = string
  default     = ""
}

variable "finance_leader_email" {
  description = "Env value for FINANCE_LEADER_EMAIL."
  type        = string
  default     = ""
}

variable "hr_leader_email" {
  description = "Env value for HR_LEADER_EMAIL."
  type        = string
  default     = ""
}

variable "delivery_leader_email" {
  description = "Env value for DELIVERY_LEADER_EMAIL."
  type        = string
  default     = ""
}

variable "teams_webhook_url" {
  description = "Optional Teams webhook. Leave empty until Teams sender ships."
  type        = string
  default     = ""
}

variable "slack_webhook_url" {
  description = "Optional Slack webhook. Leave empty until Slack sender ships."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the scheduler log group."
  type        = number
  default     = 14
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for the alert-scheduler tick."
  type        = string
  default     = "rate(5 minutes)"
}

variable "renewals_schedule_expression" {
  description = "EventBridge schedule expression for the renewals-scheduler tick. Daily is enough — the finest time granularity a renewal cares about is a whole day."
  type        = string
  default     = "rate(1 hour)"
}

# S7: nightly audit-event S3 export (WORM bucket). Runs once a day; the
# default is 03:00 UTC so the previous UTC day is fully closed and the
# scheduler + notification-sender tasks (rate(5 minutes)) are quiet.
variable "audit_export_schedule_expression" {
  description = "EventBridge schedule expression for the nightly audit-export task. Default fires at 03:00 UTC daily."
  type        = string
  default     = "cron(0 3 * * ? *)"
}

variable "audit_export_bucket_name" {
  description = "S3 bucket name for the nightly audit export. Feed from module.storage.audit_exports_bucket_name."
  type        = string
}

variable "audit_export_bucket_arn" {
  description = "S3 bucket ARN for the nightly audit export. Used to scope the task role IAM policy to only this bucket."
  type        = string
}
