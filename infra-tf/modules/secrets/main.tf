# Auto-generated RDS master password. The `data` module reads this secret when
# it builds the DB instance, and the `api` module wires the composed connection
# URL into the ECS task via `secrets` (never as a plaintext env var).
resource "random_password" "db_master" {
  length           = 32
  special          = true
  override_special = "!#$%^&*()-_=+"
  min_lower        = 2
  min_upper        = 2
  min_numeric      = 2
  min_special      = 2
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${var.name_prefix}-db-master-password"
  description             = "RDS Postgres master password. Rotation is OFF for dev."
  recovery_window_in_days = 0 # dev: allow immediate re-create
  kms_key_id              = var.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_master.result
}

# The full connection URL, populated by the root stack after RDS + password
# exist. This is what the ECS task actually reads.
resource "aws_secretsmanager_secret" "db_url" {
  name                    = "${var.name_prefix}-db-url"
  description             = "postgresql://... DSN for the API. Written by the data module."
  recovery_window_in_days = 0
  kms_key_id              = var.kms_key_arn
}

# JWT signing key for anything issued locally by the API (Cognito signs its own
# tokens; this is a spare for internal signed URLs). Auto-generated once.
resource "random_password" "jwt_signing" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "jwt_signing" {
  name                    = "${var.name_prefix}-jwt-signing-key"
  description             = "Symmetric key for API-issued signed URLs. Rotation OFF for dev."
  recovery_window_in_days = 0
  kms_key_id              = var.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "jwt_signing" {
  secret_id     = aws_secretsmanager_secret.jwt_signing.id
  secret_string = random_password.jwt_signing.result
}
