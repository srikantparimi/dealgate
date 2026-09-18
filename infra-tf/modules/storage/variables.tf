variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "account_id" {
  description = "AWS account id — appended to the bucket name for global uniqueness."
  type        = string
}
