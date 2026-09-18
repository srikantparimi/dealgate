output "agreements_bucket_name" {
  description = "S3 bucket for signed evidence uploads. Feed to the API task as AGREEMENTS_BUCKET."
  value       = aws_s3_bucket.agreements.id
}

output "agreements_bucket_arn" {
  description = "ARN of the agreements bucket — used by IAM policies that grant PutObject/GetObject to the API task role."
  value       = aws_s3_bucket.agreements.arn
}
