# -----------------------------------------------------------------------------
# S14a.3b: DNS + SES domain + ACM cert for the app-owned Route 53 zone.
#
# Route 53 auto-creates a public hosted zone when a domain is registered via
# route53domains. That zone is imported into state (see
# docs/runbooks/domain-bootstrap.md) — this module never creates it. Every
# other resource here (SES identity, DKIM, MAIL FROM, ACM cert, alias records,
# validation records) is pure Terraform on top of the imported zone.
#
# Design constraints:
#   - ACM cert lives in us-east-1 because CloudFront ignores certs in any
#     other region. Provider alias `aws.us_east_1` is required.
#   - SES sits in var.region (us-east-2 for dev). The MAIL FROM MX record
#     targets feedback-smtp.<region>.amazonses.com; changing region needs a
#     record change here.
#   - SPF, DKIM, DMARC together are what make `noreply@<domain>` land in
#     the inbox rather than the spam folder for Gmail / Google Workspace /
#     Microsoft 365. Missing any one flips deliverability from ~99% to
#     ~30% on first-send. Do not remove any of them.
#   - Custom MAIL FROM (bounce.<domain>) provides SPF *alignment*, which
#     DMARC's aspf=s check requires. Without it, DMARC's SPF alignment
#     fails even though SPF itself passes, so aspf=s must be aspf=r and
#     that widens the spoof surface.
# -----------------------------------------------------------------------------

resource "aws_route53_zone" "root" {
  name    = var.root_domain
  comment = "Managed by Terraform (S14a.3b). Adopted via `import` block from the zone Route 53 auto-created at domain registration."

  # Do not force-destroy — losing the zone kills every subdomain including
  # the SPA alias and any future MX for the domain.
  force_destroy = false
}

# Adopted via explicit `terraform import module.dns.aws_route53_zone.root
# Z05394412HNCUGGL2X45I` on first apply — see docs/reports/s14a.3.md for
# the runbook. (Import blocks inside child modules combine badly with
# `-target`, which is how every apply in this codebase is being landed
# right now; explicit import command is more reliable.)

# --- SES domain identity + DKIM ---------------------------------------------

resource "aws_ses_domain_identity" "root" {
  domain = var.root_domain
}

resource "aws_ses_domain_dkim" "root" {
  domain = aws_ses_domain_identity.root.domain
}

# Three CNAMEs, one per DKIM selector. Amazon uses 1024-bit keys; each token
# resolves to a *.dkim.amazonses.com hostname. Rotating keys later means new
# tokens + new records — same resource shape.
resource "aws_route53_record" "dkim" {
  count = 3

  zone_id = aws_route53_zone.root.zone_id
  name    = "${aws_ses_domain_dkim.root.dkim_tokens[count.index]}._domainkey.${var.root_domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.root.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

# Waits until AWS reports the domain identity as Success. First-time DNS
# propagation is typically 2-10 minutes since Route 53 is fast and
# amazonses.com is a well-known DKIM host.
resource "aws_ses_domain_identity_verification" "root" {
  domain     = aws_ses_domain_identity.root.domain
  depends_on = [aws_route53_record.dkim]
}

# --- MAIL FROM domain -------------------------------------------------------
#
# Amazon SES uses `amazonses.com` as the envelope From by default, which
# fails DMARC SPF *alignment* against var.root_domain (aspf=s in the DMARC
# record). Configuring a custom MAIL FROM under our own domain fixes this.
# We use `bounce.<root_domain>` because it makes bounce reports visibly
# associated with mail delivery.

resource "aws_ses_domain_mail_from" "root" {
  domain           = aws_ses_domain_identity.root.domain
  mail_from_domain = "bounce.${var.root_domain}"

  # If SES ever can't send bounces to the MAIL FROM domain (e.g. records
  # temporarily missing), fall back to using the default amazonses.com
  # From. Default is RejectMessage, which would drop legitimate mail
  # during a DNS blip.
  behavior_on_mx_failure = "UseDefaultValue"

  depends_on = [aws_ses_domain_identity_verification.root]
}

resource "aws_route53_record" "mail_from_mx" {
  zone_id = aws_route53_zone.root.zone_id
  name    = aws_ses_domain_mail_from.root.mail_from_domain
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${var.region}.amazonses.com"]
}

# SPF for the MAIL FROM subdomain: tells receiving mail servers that
# amazonses.com is authorised to send on behalf of bounce.<domain>.
resource "aws_route53_record" "mail_from_spf" {
  zone_id = aws_route53_zone.root.zone_id
  name    = aws_ses_domain_mail_from.root.mail_from_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com -all"]
}

# --- SPF + DMARC on the root domain -----------------------------------------
#
# Root SPF: authorises amazonses.com to send from the visible From address
# (noreply@<domain>). The `-all` hardfail means receivers reject anything
# else claiming to be us.

resource "aws_route53_record" "root_spf" {
  zone_id = aws_route53_zone.root.zone_id
  name    = var.root_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com -all"]
}

# DMARC in reject mode: any message that fails SPF alignment AND DKIM
# alignment is rejected by receivers. adkim/aspf=s means *strict* alignment
# (subdomain != domain fails). rua=mailto delivers daily aggregate reports.
resource "aws_route53_record" "root_dmarc" {
  zone_id = aws_route53_zone.root.zone_id
  name    = "_dmarc.${var.root_domain}"
  type    = "TXT"
  ttl     = 600
  records = [
    "v=DMARC1; p=reject; adkim=s; aspf=s; rua=mailto:${var.dmarc_reporting_email}; fo=1"
  ]
}

# --- ACM cert for the app subdomain (us-east-1 for CloudFront) --------------

resource "aws_acm_certificate" "app" {
  provider = aws.us_east_1

  domain_name       = var.app_subdomain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.name_prefix}-app"
  }
}

# ACM's DNS validation record is written into Route 53 automatically because
# the zone is programmable. This replaces the manual-CNAME-in-Cloudflare flow
# that stranded the smartek21 cert in PENDING_VALIDATION for weeks.
#
# `domain_validation_options` is a set with exactly one entry when the cert
# has a single domain and no SANs, which is the case here. Reaching in with
# `tolist(...)[0]` avoids for_each on an unknown value — a for_each derived
# from cert output can't be planned until the cert exists, which breaks
# every `-target=` apply in this codebase.
locals {
  acm_validation = tolist(aws_acm_certificate.app.domain_validation_options)[0]
}

resource "aws_route53_record" "acm_validation" {
  zone_id         = aws_route53_zone.root.zone_id
  name            = local.acm_validation.resource_record_name
  type            = local.acm_validation.resource_record_type
  ttl             = 60
  records         = [local.acm_validation.resource_record_value]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "app" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [aws_route53_record.acm_validation.fqdn]
}

# The alias A/AAAA records that point var.app_subdomain at the CloudFront
# distribution live at the ROOT (not this module) because module.web depends
# on module.dns.app_certificate_arn and this module would otherwise depend
# on module.web.distribution_domain_name — a cycle. See root main.tf.
