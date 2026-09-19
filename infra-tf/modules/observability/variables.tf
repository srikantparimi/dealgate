variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev). Drives every resource name in this module."
  type        = string
}

variable "region" {
  description = "AWS region — used for the CloudTrail S3 key condition and for alarm dimensions."
  type        = string
}

variable "account_id" {
  description = "AWS account id — appended to the CloudTrail bucket name for global uniqueness."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the customer-managed KMS key that encrypts the CloudTrail bucket + CloudTrail log-file SSE."
  type        = string
}

variable "rds_instance_id" {
  description = "RDS instance identifier (e.g. officeapp-dev-db) used as the CloudWatch alarm dimension for CPU / free storage."
  type        = string
}

variable "rds_allocated_storage_gb" {
  description = "Allocated storage of the RDS instance in GB. Used to compute the 10% free-storage threshold."
  type        = number
}

variable "ecs_cluster_name" {
  description = "ECS cluster name (used as the alarm dimension for the ECS service failure alarm)."
  type        = string
}

variable "ecs_service_name" {
  description = "ECS API service name (used as the alarm dimension for the ECS service failure alarm)."
  type        = string
}

variable "alert_email" {
  description = "Email address subscribed to the SNS alerts topic. The subscription starts in PendingConfirmation until the recipient clicks the confirmation link."
  type        = string
  default     = "srikantp@smartek21.com"
}

variable "cloudtrail_retention_years" {
  description = "Object Lock retention (in years) on the CloudTrail bucket. COMPLIANCE mode. 7 is the auditor default."
  type        = number
  default     = 7
}
