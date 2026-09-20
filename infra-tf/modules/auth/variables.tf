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

# S12: when the SPA is served from a custom domain, Cognito must accept that
# origin's callback too. Kept alongside the CloudFront URL rather than
# replacing it, so a redeploy of the bundle to either hostname still logs in.
variable "custom_domain" {
  description = "Custom domain the SPA is served from (e.g. dealgate.smartek21.com). Empty means only the CloudFront hostname and localhost are registered."
  type        = string
  default     = ""
}
