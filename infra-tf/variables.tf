variable "env" {
  description = "Deployment environment slug (dev|staging|prod). Drives naming prefix and defaults."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be one of dev, staging, prod."
  }
}

variable "region" {
  description = "AWS region for all resources in this stack."
  type        = string
  default     = "us-east-2"
}

variable "image_tag" {
  description = "ECR image tag the ECS task should run. CI updates this per deploy; the default here is the last known-good tag for a laptop-run `terraform plan/apply` (see git log for what's in ECR right now). Never set to 'bootstrap' — that tag stopped being pushed months ago and any task using it fails with CannotPullContainerError."
  type        = string
  default     = "s14a.3b-workers-creds-fix"
}

variable "domain" {
  description = "Custom domain for the SPA. Empty string means use the CloudFront default hostname. Setting this creates an ACM certificate (in us-east-1 per CloudFront's constraint) and attaches it as a distribution alias; when the domain lives in an AWS-managed Route 53 zone, ACM's DNS validation record is written into that zone automatically (see infra-tf/modules/dns — added when Kanna picks the app's own domain in s14a.3b's DNS follow-up)."
  type        = string
  # S14a.3b (22 Sep 2026): the smartek21.com dependency was cut and the
  # app-owned Route 53 zone (dealgateapp.com) took its place. The SPA lives
  # at app.dealgateapp.com; module.dns owns the zone, SES identity, ACM cert,
  # and root DNS records; module.web attaches the cert to CloudFront and
  # picks up this value as the alias. Setting to "" reverts CloudFront to
  # its default cert.
  default = "app.dealgateapp.com"
}

variable "github_repo" {
  description = "GitHub 'owner/name' allowed to assume the deploy role via OIDC. Trust policy is scoped to this repo."
  type        = string
  default     = "smartek21/officeapp-dealgate"
}

variable "create_github_oidc_provider" {
  description = "Set true only if the token.actions.githubusercontent.com OIDC provider does not already exist in the AWS account."
  type        = bool
  default     = false
}

# S7: observability module wires this straight into the SNS alerts subscription.
variable "alert_email" {
  description = "Email that receives SNS alerts (RDS CPU / free storage / ECS task failures). Recipient must confirm the SNS subscription."
  type        = string
  default     = "srikantp@smartek21.com"
}
