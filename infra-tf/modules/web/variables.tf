variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "account_id" {
  description = "Current AWS account id; used to make the S3 bucket name globally unique."
  type        = string
}
