variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "region" {
  description = "AWS region used for the SES MAIL FROM MX endpoint (feedback-smtp.<region>.amazonses.com) and for tagging."
  type        = string
}

variable "root_domain" {
  description = "The registered Route 53 domain (apex), e.g. dealgateapp.com. The hosted zone is auto-created by Route 53 at registration and imported into state — this module does not create it."
  type        = string
}

variable "app_subdomain" {
  description = "The hostname the SPA + API live on, e.g. app.dealgateapp.com. Must be under root_domain."
  type        = string
}

variable "dmarc_reporting_email" {
  description = "Address that receives DMARC aggregate reports (rua=). Typically a security or ops mailbox. Reports come daily from every receiving mail provider that observed a message pretending to be from root_domain."
  type        = string
}

# The alias A/AAAA records that point var.app_subdomain at CloudFront live at
# the root, not here — module.web depends on this module's ACM cert output,
# so hosting the alias inside this module would create a graph cycle. The
# root main.tf consumes zone_id output + module.web.distribution_domain_name
# to build the records.
