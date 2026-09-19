output "alert_scheduler_task_definition_arn" {
  value       = aws_ecs_task_definition.alert_scheduler.arn
  description = "Task definition ARN launched by the alert-scheduler EventBridge rule."
}

output "notification_sender_task_definition_arn" {
  value       = aws_ecs_task_definition.notification_sender.arn
  description = "Task definition ARN launched by the notification-sender EventBridge rule."
}

output "task_role_arn" {
  value       = aws_iam_role.task.arn
  description = "IAM role assumed by both scheduled tasks (SES SendEmail + logs)."
}

output "events_role_arn" {
  value       = aws_iam_role.events.arn
  description = "IAM role EventBridge uses to RunTask on ECS."
}

output "ses_identity_arn" {
  value       = aws_ses_email_identity.sender.arn
  description = "Verified SES email identity ARN. Sandbox: the integrator must click the verification link before the first send."
}

output "log_group_name" {
  value       = aws_cloudwatch_log_group.schedulers.name
  description = "CloudWatch log group both scheduled tasks stream to."
}

output "audit_export_task_definition_arn" {
  value       = aws_ecs_task_definition.audit_export.arn
  description = "Task definition ARN launched by the nightly audit-export EventBridge rule (S7)."
}
