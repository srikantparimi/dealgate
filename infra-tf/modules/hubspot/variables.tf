variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key used for SQS SSE-KMS. Shared with the rest of the stack."
  type        = string
}
