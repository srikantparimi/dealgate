# -----------------------------------------------------------------------------
# S20 U01 · role-partitioned Cognito approvers for T27 + T44.
#
# Five test users, one per functional-review role, plus-addressed off the PO's
# corporate inbox so verification links + reset emails go to one mailbox:
#
#   srikanthp+submitter@smartek21.com   → Sales
#   srikanthp+delivery@smartek21.com    → Delivery
#   srikanthp+hr@smartek21.com          → HR
#   srikanthp+finance@smartek21.com     → Finance
#   srikanthp+legal@smartek21.com       → Legal
#
# The CEO account already exists (srikanthp+ceo@smartek21.com). Each new user is:
#   - created via aws_cognito_user with a random 24-char password
#   - flipped to permanent via a null_resource (Cognito's password field
#     leaves the user in FORCE_CHANGE_PASSWORD; the null_resource calls
#     admin-set-user-password --permanent so Playwright can sign in
#     without a first-login flow)
#   - added to (a) the role group and (b) the `officeapp-e2e` group so
#     admin tooling + the leak gate treat them as test data
#   - registered as an SES email identity so future automated notifications
#     (S3 approval, renewal, escalation) can reach them in the sandbox
#
# Credentials are written to a single Secrets Manager JSON blob at
# `officeapp-dev-e2e-approvers`; tests/e2e/fixtures/multi-role-auth.ts reads
# it via `aws secretsmanager get-secret-value` and mints tokens per role.
# -----------------------------------------------------------------------------

locals {
  # role slug → Cognito group name (must match the groups already in the
  # pool per `aws cognito-idp list-groups`).
  roles = {
    submitter = "Sales"
    delivery  = "Delivery"
    hr        = "HR"
    finance   = "Finance"
    legal     = "Legal"
  }

  # Plus-addressing so all five verification emails land in one mailbox.
  usernames = {
    for slug, group in local.roles :
    slug => "srikanthp+${slug}@smartek21.com"
  }
}

# ---- Passwords --------------------------------------------------------------

resource "random_password" "approver" {
  for_each = local.roles

  length           = 24
  special          = true
  override_special = "!@#$%^&*()-_=+"
  min_lower        = 2
  min_upper        = 2
  min_numeric      = 2
  min_special      = 2
}

# ---- Cognito users ---------------------------------------------------------
#
# `message_action = "SUPPRESS"` avoids Cognito auto-sending an invite email —
# the PO already knows the accounts exist because they approved this slice.
# `desired_delivery_mediums = ["EMAIL"]` keeps the user attribute shape right.

resource "aws_cognito_user" "approver" {
  for_each = local.roles

  user_pool_id             = var.user_pool_id
  username                 = local.usernames[each.key]
  password                 = random_password.approver[each.key].result
  message_action           = "SUPPRESS"
  desired_delivery_mediums = ["EMAIL"]
  force_alias_creation     = false

  attributes = {
    email          = local.usernames[each.key]
    email_verified = "true"
    name           = "S20 e2e approver (${each.key})"
  }
}

# ---- Flip password to permanent --------------------------------------------
#
# aws_cognito_user's `password` argument sets the value but leaves the user
# in FORCE_CHANGE_PASSWORD. Playwright cannot complete the first-login flow,
# so we call admin-set-user-password --permanent right after create.

resource "null_resource" "set_permanent" {
  for_each = local.roles

  triggers = {
    username = aws_cognito_user.approver[each.key].username
    # Include the password in the trigger hash so a password rotation
    # forces the null_resource to re-run.
    password_hash = sha256(random_password.approver[each.key].result)
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws --profile ${var.aws_profile} --region us-east-2 \
        cognito-idp admin-set-user-password \
        --user-pool-id ${var.user_pool_id} \
        --username '${local.usernames[each.key]}' \
        --password '${random_password.approver[each.key].result}' \
        --permanent
    EOT
  }
}

# ---- Group memberships -----------------------------------------------------
#
# Each user lands in TWO groups:
#   1. the role group (Delivery, HR, Finance, Legal, or Sales)
#   2. `officeapp-e2e` — the tag admin tooling + T27 use to identify test
#      users. Membership never overlaps with production role checks.

resource "aws_cognito_user_in_group" "role_group" {
  for_each = local.roles

  user_pool_id = var.user_pool_id
  username     = aws_cognito_user.approver[each.key].username
  group_name   = each.value

  depends_on = [null_resource.set_permanent]
}

resource "aws_cognito_user_in_group" "e2e_group" {
  for_each = local.roles

  user_pool_id = var.user_pool_id
  username     = aws_cognito_user.approver[each.key].username
  group_name   = "officeapp-e2e"

  depends_on = [null_resource.set_permanent]
}

# ---- SES email identities --------------------------------------------------
#
# Each address becomes a verified sending identity so notification-sender
# etc. can reach it in the sandbox. Verification emails go to
# `var.email_recipient` (default: srikanthp@smartek21.com — the PO's real
# mailbox); the PO clicks each of the 5 links to complete verification.

resource "aws_ses_email_identity" "approver" {
  for_each = local.roles
  email    = local.usernames[each.key]
}

# ---- Credentials secret ----------------------------------------------------
#
# The Playwright fixture at `tests/e2e/fixtures/multi-role-auth.ts` reads
# this secret and mints one Cognito token per role. Shape:
#
#   {
#     "user_pool_id": "us-east-2_VV03Ir8AF",
#     "client_id": "dg2b6dhiu126bq459tthcmso2",
#     "region": "us-east-2",
#     "roles": {
#       "submitter": { "username": "...", "password": "...", "group": "Sales" },
#       "delivery":  { "username": "...", "password": "...", "group": "Delivery" },
#       ...
#     }
#   }
#
# The single-secret shape keeps the fixture simple — one API call for all
# five accounts + the pool metadata it needs to construct the auth request.

resource "aws_secretsmanager_secret" "approvers" {
  name                    = "${var.name_prefix}-e2e-approvers-multirole"
  description             = "S20 U01 · role-partitioned Cognito approvers for T27 + T44 Playwright specs."
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 0

  tags = {
    Purpose = "e2e-approvers"
    Slice   = "S20-U01"
  }
}

resource "aws_secretsmanager_secret_version" "approvers" {
  secret_id = aws_secretsmanager_secret.approvers.id
  secret_string = jsonencode({
    user_pool_id = var.user_pool_id
    roles = {
      for slug, group in local.roles :
      slug => {
        username = local.usernames[slug]
        password = random_password.approver[slug].result
        group    = group
      }
    }
  })

  depends_on = [
    null_resource.set_permanent,
    aws_cognito_user_in_group.role_group,
    aws_cognito_user_in_group.e2e_group,
  ]
}
