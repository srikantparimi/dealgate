output "agreements_bucket_name" {
  description = "S3 bucket for signed evidence uploads. Feed to the API task as AGREEMENTS_BUCKET."
  value       = aws_s3_bucket.agreements.id
}

output "agreements_bucket_arn" {
  description = "ARN of the agreements bucket — used by IAM policies that grant PutObject/GetObject to the API task role."
  value       = aws_s3_bucket.agreements.arn
}

output "sows_bucket_name" {
  description = "S3 bucket for signed SOW uploads (S3-E5). Feed to the API task as SOW_BUCKET."
  value       = aws_s3_bucket.sows.id
}

output "sows_bucket_arn" {
  description = "ARN of the sows bucket — used by IAM policies that grant PutObject/GetObject/Bedrock-read to the API task role."
  value       = aws_s3_bucket.sows.arn
}

output "audit_exports_bucket_name" {
  description = "S3 bucket for the nightly audit-event export (WORM). Feed to the schedulers task as AUDIT_EXPORT_BUCKET."
  value       = aws_s3_bucket.audit_exports.id
}

output "audit_exports_bucket_arn" {
  description = "ARN of the audit-exports bucket — used by the audit-export scheduler task role for PutObject / PutObjectRetention / GetObject."
  value       = aws_s3_bucket.audit_exports.arn
}
