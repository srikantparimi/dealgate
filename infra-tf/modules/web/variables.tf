variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "account_id" {
  description = "Current AWS account id; used to make the S3 bucket name globally unique."
  type        = string
}

# S7: KMS-at-rest wiring for the SPA origin bucket.
variable "kms_key_arn" {
  description = "ARN of the customer-managed KMS key used for SSE-KMS on the SPA origin bucket."
  type        = string
}
