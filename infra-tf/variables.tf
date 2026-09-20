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
  description = "ECR image tag the ECS task should run. Bootstrap uses 'bootstrap'; CI updates this per deploy."
  type        = string
  default     = "bootstrap"
}

variable "domain" {
  description = "Custom domain for the SPA. Empty string means use the CloudFront default hostname. Setting this creates an ACM certificate in us-east-1 and attaches it as a distribution alias; the DNS records are added by hand in Cloudflare (docs/runbooks/custom-domain.md)."
  type        = string
  default     = "dealgate.smartek21.com"
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
