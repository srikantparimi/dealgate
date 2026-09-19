output "key_arn" {
  description = "ARN of the customer-managed KMS key. Pass to S3 / RDS / Secrets Manager as kms_key_arn."
  value       = aws_kms_key.data.arn
}

output "key_id" {
  description = "Key id (UUID) of the customer-managed KMS key. Used where the AWS provider expects the short id rather than the full ARN."
  value       = aws_kms_key.data.key_id
}

output "alias_arn" {
  description = "Alias ARN — useful for consumers that prefer a stable name over the key ARN."
  value       = aws_kms_alias.data.arn
}

output "alias_name" {
  description = "Alias name, e.g. alias/officeapp-dev-data."
  value       = aws_kms_alias.data.name
}
