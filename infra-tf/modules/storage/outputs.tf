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
