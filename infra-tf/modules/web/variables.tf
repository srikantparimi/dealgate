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

# S12: custom domain for the SPA. Both default to "" so an environment that
# has not been given a domain yet keeps the CloudFront default certificate and
# hostname — the distribution stays valid either way.
variable "domain_name" {
  description = "Custom domain served by the CloudFront distribution (e.g. dealgate.smartek21.com). Empty means CloudFront's default *.cloudfront.net hostname only."
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ARN of an ISSUED ACM certificate in us-east-1 covering domain_name. Required when domain_name is set — CloudFront rejects an alias without a matching certificate."
  type        = string
  default     = ""
}
