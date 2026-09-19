variable "env" {
  description = "Deployment environment slug. Pinned to 'staging' in this root."
  type        = string
  default     = "staging"

  validation {
    condition     = var.env == "staging"
    error_message = "This root is staging-only. Use infra-tf/ for dev."
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
  description = "Optional custom domain (e.g. staging.dealgate.example.com). Empty string means use the CloudFront/ALB defaults."
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub 'owner/name' allowed to assume the deploy role via OIDC. Trust policy is scoped to this repo."
  type        = string
  default     = "smartek21/officeapp-dealgate"
}

variable "create_github_oidc_provider" {
  description = "Set true only if the token.actions.githubusercontent.com OIDC provider does not already exist in the AWS account. Staging almost always reuses dev's provider — leave false."
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Email that receives SNS alerts (RDS CPU / free storage / ECS task failures). Recipient must confirm the SNS subscription."
  type        = string
  default     = "srikantp@smartek21.com"
}
