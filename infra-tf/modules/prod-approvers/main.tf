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

# -----------------------------------------------------------------------------
# Release push 2026-10-04: the six approvers also need Cognito logins —
# roster membership routes to them, but without an account nobody can
# open the approval. Cognito emails each person its own temporary
# password (Cognito's native mailer, not SES, so the sandbox does not
# block the invite). Group attachment drives the cognito:groups claim
# the app reads at login; the invited DB rows are adopted by email on
# first sign-in (services/user_provisioning.ensure_user).
# -----------------------------------------------------------------------------

variable "user_pool_id" {
  description = "Cognito user pool that holds the business identities."
  type        = string
}

locals {
  approver_groups = {
    delivery          = "Delivery"
    delivery_fallback = "Delivery"
    sales             = "Sales"
    legal             = "Legal"
    finance           = "Finance"
    ceo_exception     = "CEO"
  }
}

resource "aws_cognito_user" "prod_approver" {
  for_each     = local.prod_approvers
  user_pool_id = var.user_pool_id
  username     = each.value.email

  desired_delivery_mediums = ["EMAIL"]

  attributes = {
    email          = each.value.email
    email_verified = "true"
  }
}

resource "aws_cognito_user_in_group" "prod_approver" {
  for_each     = local.prod_approvers
  user_pool_id = var.user_pool_id
  group_name   = local.approver_groups[each.key]
  username     = aws_cognito_user.prod_approver[each.key].username
}
