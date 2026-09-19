variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev). Drives the key alias."
  type        = string
}

variable "region" {
  description = "AWS region for the ViaService conditions on the key policy delegation statements."
  type        = string
}

variable "account_id" {
  description = "AWS account id; used to scope the root-account principal in the key policy."
  type        = string
}

# NOTE: the ECS task role does NOT need a key-policy statement here — the
# delegated-service statement (kms:ViaService = s3/secretsmanager/rds) plus
# an IAM policy attached to the task role in modules/api is what allows the
# task to GenerateDataKey / Decrypt through S3 and Secrets Manager. Wiring
# the task role ARN into this module would create a kms -> api -> secrets ->
# kms cycle.

variable "deletion_window_in_days" {
  description = "Waiting period (in days) before AWS finalizes key deletion once scheduled. 7 is the minimum; 30 is the default."
  type        = number
  default     = 30
}
