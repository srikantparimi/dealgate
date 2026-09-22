output "alb_dns" {
  description = "Public ALB DNS name — API entrypoint until we add a custom domain."
  value       = module.api.alb_dns_name
}

output "cloudfront_domain" {
  description = "CloudFront default domain. Still a valid entrypoint after a custom domain is attached — the alias is added, not swapped."
  value       = module.web.distribution_domain_name
}

output "app_url" {
  description = "The URL people actually use. Falls back to the CloudFront hostname when no custom domain is configured."
  value       = var.domain == "" ? "https://${module.web.distribution_domain_name}" : "https://${var.domain}"
}

output "web_certificate_arn" {
  description = "ACM certificate backing the custom domain, or null when none is configured. Sourced from module.dns (which owns the cert + DNS validation)."
  value       = var.domain == "" ? null : module.dns.app_certificate_arn
}

output "app_domain_zone_ns" {
  description = "The four Route 53 nameservers for the dealgateapp.com zone. Matches the registrar defaults; surfaced for any future external delegation."
  value       = module.dns.zone_name_servers
}

output "api_ecr_uri" {
  description = "ECR repo URI to push api images to."
  value       = module.ecr.repository_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool id (also injected into the API task)."
  value       = module.auth.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito app client id (SPA + API)."
  value       = module.auth.client_id
}

output "cognito_hosted_ui_url" {
  description = "Base URL for the Cognito hosted UI."
  value       = module.auth.hosted_ui_url
}

output "github_oidc_role_arn" {
  description = "IAM role GitHub Actions assumes for deploys."
  value       = module.github_oidc.role_arn
}

output "db_secret_arn" {
  description = "Secrets Manager ARN holding the composed POSTGRES_URL."
  value       = module.secrets.db_url_secret_arn
}

output "agreements_bucket_name" {
  description = "S3 bucket that holds signed NDA/MSA evidence uploads (S2-E3). Feed into the API task's AGREEMENTS_BUCKET env var."
  value       = module.storage.agreements_bucket_name
}
