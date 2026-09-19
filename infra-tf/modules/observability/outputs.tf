output "cloudtrail_bucket_name" {
  description = "S3 bucket name that stores the CloudTrail multi-region trail."
  value       = aws_s3_bucket.cloudtrail.id
}

output "cloudtrail_bucket_arn" {
  description = "ARN of the CloudTrail bucket."
  value       = aws_s3_bucket.cloudtrail.arn
}

output "cloudtrail_arn" {
  description = "ARN of the CloudTrail trail resource."
  value       = aws_cloudtrail.audit.arn
}

output "guardduty_detector_id" {
  description = "GuardDuty detector id. Useful for follow-up modules that add filters or SecurityHub integration."
  value       = aws_guardduty_detector.this.id
}

output "alerts_topic_arn" {
  description = "SNS topic ARN. Wire additional alarms / cross-account events here."
  value       = aws_sns_topic.alerts.arn
}
