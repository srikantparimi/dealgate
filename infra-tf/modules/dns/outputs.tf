output "zone_id" {
  value       = aws_route53_zone.root.zone_id
  description = "The imported hosted zone ID for var.root_domain."
}

output "zone_name_servers" {
  value       = aws_route53_zone.root.name_servers
  description = "The four Route 53 nameservers for the zone. Same values Route 53 already set at the registrar (dealgateapp.com is intra-account) — surfaced so any external delegation later doesn't need a console lookup."
}

output "app_certificate_arn" {
  value       = aws_acm_certificate_validation.app.certificate_arn
  description = "The ISSUED us-east-1 ACM cert for var.app_subdomain. Depends on the validation resource so consumers block until the cert leaves PENDING_VALIDATION."
}

output "ses_from_address" {
  value       = "noreply@${var.root_domain}"
  description = "The verified sender address to inject into the scheduler + notification-sender tasks. Depends on the SES identity being verified — consumers should chain via `depends_on = [module.dns]` to guarantee ordering."
}

output "app_subdomain" {
  value       = var.app_subdomain
  description = "Echo of the input for convenience at the root."
}
