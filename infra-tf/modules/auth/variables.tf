variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "account_id" {
  description = "AWS account id; last 6 digits used to make the Cognito hosted-UI domain unique."
  type        = string
}

variable "region" {
  description = "AWS region hosting the user pool (used to build the hosted-UI URL)."
  type        = string
}

variable "cloudfront_domain" {
  description = "CloudFront default domain (e.g. dXXXX.cloudfront.net); used for OAuth callback URLs."
  type        = string
}
