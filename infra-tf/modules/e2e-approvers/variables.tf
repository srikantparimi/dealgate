variable "name_prefix" {
  description = "Environment name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "user_pool_id" {
  description = "Cognito user pool that hosts the approvers."
  type        = string
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key used to encrypt the credentials secret."
  type        = string
}

variable "email_recipient" {
  description = "Real inbox that receives the SES verification links (plus-addressed per role). Should be a mailbox the PO owns."
  type        = string
  default     = "srikanthp@smartek21.com"
}

variable "aws_profile" {
  description = "AWS CLI profile used by the null_resource that flips the password to permanent. Must match the profile that runs `terraform apply`."
  type        = string
  default     = "lm-arbiter-poc"
}
