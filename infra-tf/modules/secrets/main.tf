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
  # TODO(s14a.2): flip to var.kms_key_arn once the customer-managed CMK is
  # created by module.kms AND the API + execution roles carry the kms:Decrypt
  # grant scoped via kms:ViaService = secretsmanager.<region>.amazonaws.com.
  # Flipping this before the grant lands breaks the ECS execution role's
  # ability to fetch the secret at task start. Null = AWS-managed
  # aws/secretsmanager (current live state).
  kms_key_id = null
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
  # TODO(s14a.2): flip to var.kms_key_arn together with db_password + jwt_signing
  # once the CMK + kms:Decrypt grants land. See db_password above for the full
  # ordering constraint. Null = AWS-managed aws/secretsmanager (current live state).
  kms_key_id = null
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
  # TODO(s14a.2): flip to var.kms_key_arn together with db_password + db_url
  # once the CMK + kms:Decrypt grants land. See db_password above for the full
  # ordering constraint. Null = AWS-managed aws/secretsmanager (current live state).
  kms_key_id = null
}

resource "aws_secretsmanager_secret_version" "jwt_signing" {
  secret_id     = aws_secretsmanager_secret.jwt_signing.id
  secret_string = random_password.jwt_signing.result
}

# S18 · HubSpot private-app read token. The secret itself is provisioned
# out of band (Kanna owns the HubSpot side); this module only references it
# so TF never sees the value. A ``data`` source is intentional — a
# ``resource`` would want to manage the version, which would put the token
# through state. Kept in the same "secrets" module so every task-def that
# needs one Secrets Manager ARN gets both together.
data "aws_secretsmanager_secret" "hubspot_token" {
  name = "dealgate/staging/hubspot_token"
}
