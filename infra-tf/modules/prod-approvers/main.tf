# -----------------------------------------------------------------------------
# S21 item 8 · production approver SES identities.
#
# From Kanna's 2026-10-01 click-through, directive §6: the five real
# people who receive routing on real SOWs. SES is in sandbox, so each
# address must be an aws_ses_email_identity resource; each person clicks
# their verification mail once. Production access remains an AWS support
# request tracked separately in docs/backlog/prod-environment.md.
#
# Rule 15 (interactive terraform prompts): this module adds resources
# only — the operator runs `terraform plan` here first and reviews the
# add list; `terraform apply` is reserved for Kanna. The null_resource
# that emits the verification mail (SES does this automatically on
# identity creation) will cause each of the five mailboxes to receive
# a "please verify" link. No apply happens here.
# -----------------------------------------------------------------------------

locals {
  prod_approvers = {
    delivery = {
      email = "shawnnad@smartek21.com"
      label = "Delivery"
    }
    delivery_fallback = {
      email = "srikanthp@smartek21.com"
      label = "Delivery fallback (OOO)"
    }
    sales = {
      email = "janicek@smartek21.com"
      label = "Sales"
    }
    legal = {
      email = "seema@smartek21.com"
      label = "Legal"
    }
    finance = {
      email = "scottpf@smartek21.com"
      label = "Finance"
    }
    ceo_exception = {
      email = "al@smartek21.com"
      label = "CEO exception"
    }
  }
}

resource "aws_ses_email_identity" "prod_approver" {
  for_each = local.prod_approvers
  email    = each.value.email
}

output "prod_approver_emails" {
  description = "Email addresses provisioned as SES verified-sending identities. Each receives a verification link on first apply."
  value       = [for k, v in local.prod_approvers : v.email]
}

output "prod_approver_identities" {
  description = "Map of role slug → SES identity ARN."
  value       = { for k, _ in local.prod_approvers : k => aws_ses_email_identity.prod_approver[k].arn }
}
