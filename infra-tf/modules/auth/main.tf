locals {
  # Cognito hosted-UI domain must be globally unique per region. The account-id
  # suffix keeps it stable across re-creates.
  account_suffix = substr(var.account_id, length(var.account_id) - 6, 6)
  hosted_domain  = "${var.name_prefix}-${local.account_suffix}"

  callback_url = "https://${var.cloudfront_domain}/auth/callback"
  logout_url   = "https://${var.cloudfront_domain}/"

  # The custom domain is additive. Dropping the CloudFront URLs here would lock
  # out anyone mid-session on the old hostname, and would make a DNS problem
  # into a total outage rather than a cosmetic one.
  custom_callback_urls = var.custom_domain == "" ? [] : ["https://${var.custom_domain}/auth/callback"]
  custom_logout_urls   = var.custom_domain == "" ? [] : ["https://${var.custom_domain}/"]
}

resource "aws_cognito_user_pool" "this" {
  name = "${var.name_prefix}-users"

  # Corporate IdP federation lands later (ADR 0001). No self-signup for now.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 3
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  mfa_configuration = "OFF" # dev

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
    string_attribute_constraints {
      min_length = 3
      max_length = 256
    }
  }

  deletion_protection = "INACTIVE" # dev
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = local.hosted_domain
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false # PKCE from an SPA

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]

  supported_identity_providers = ["COGNITO"]

  callback_urls = concat(
    [local.callback_url, "http://localhost:5173/auth/callback"],
    local.custom_callback_urls,
  )
  logout_urls = concat(
    [local.logout_url, "http://localhost:5173/"],
    local.custom_logout_urls,
  )

  # ALLOW_ADMIN_USER_PASSWORD_AUTH is required by the Playwright E2E suite
  # (S13a) to programmatically sign in the fixture test user. Cognito's
  # UpdateUserPoolClient is a full replace — any flow omitted here is nulled
  # from the client, which breaks the E2E login. Keep this flow enabled in
  # every env until we move E2E to SRP.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
