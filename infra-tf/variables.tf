variable "trusted_cleanup_enabled" {
  type        = bool
  description = "Enable fixture cleanup only after trusted provenance cleanup is reviewed."
  default     = false
}

variable "operational_hardening_enabled" {
  type        = bool
  description = "Create the irreversible CloudTrail/GuardDuty/SNS hardening bundle only after its separate cost, retention and notification review."
  default     = false
}

variable "production_approver_identities_enabled" {
  type        = bool
  description = "Create real-person SES identities only after the recipients and verification-email side effects are approved."
  default     = false
}

variable "s21_jobs_enabled" {
  type        = bool
  description = "Enable new persisted Forecast and deletion workers after the release plan is approved."
  default     = false
}

variable "reporting_timezone" {
  type        = string
  description = "Organization-approved reporting timezone. Must be resolved before S21 staging acceptance."
  default     = ""
}

variable "reporting_currency" {
  type        = string
  description = "Organization-approved reporting currency. Must be resolved before S21 staging acceptance."
  default     = ""
}

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
  description = "Explicit reviewed ECR release tag shared by API and workers. No default may silently downgrade deployed code."
  type        = string
  validation {
    condition     = length(trimspace(var.image_tag)) > 0 && !contains(["latest", "bootstrap"], var.image_tag)
    error_message = "Supply an explicit immutable release tag."
  }
}

variable "allowed_account_ids" {
  description = "Account guard for this root, including the CloudFront alias provider."
  type        = list(string)
  default     = ["669810405473"]
}

variable "hubspot_continuous_enabled" {
  description = "Reviewed paired cutover: one continuous consumer and disabled legacy intake schedule. False restores scheduled intake."
  type        = bool
  default     = false
}

variable "hubspot_portal_id" {
  description = "HubSpot portal ID used to scope resumable deal scans to this deployment."
  type        = string
  default     = "48656168"

  validation {
    condition     = can(regex("^[0-9]+$", var.hubspot_portal_id))
    error_message = "hubspot_portal_id must contain only decimal digits."
  }
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
  default     = "srikanthp@smartek21.com"
}
