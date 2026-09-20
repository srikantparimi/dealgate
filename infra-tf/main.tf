# -----------------------------------------------------------------------------
# Root stack — dev only.
#
# To add staging/prod later, prefer one of:
#   (a) `terraform workspace new staging && terraform apply -var env=staging`
#       (requires the S3 backend from backend.tf to be enabled first);
#   (b) copy this root into `envs/staging/` with its own tfvars and backend key.
# The modules under modules/ are env-agnostic; only the name_prefix / sizes
# should change per env.
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

module "network" {
  source      = "./modules/network"
  name_prefix = local.name_prefix
}

module "ecr" {
  source      = "./modules/ecr"
  name_prefix = local.name_prefix
}

# S7: KMS is the anchor for encryption-at-rest across the stack (S3 buckets,
# RDS storage, Secrets Manager). Instantiated early because storage / web /
# data / secrets all need `module.kms.key_arn`. The KMS module itself has no
# module dependencies — the task-role KMS grant lives on the API side to
# avoid a kms -> api -> secrets -> kms cycle.
module "kms" {
  source      = "./modules/kms"
  name_prefix = local.name_prefix
  region      = var.region
  account_id  = data.aws_caller_identity.current.account_id
}

module "secrets" {
  source      = "./modules/secrets"
  name_prefix = local.name_prefix
  kms_key_arn = module.kms.key_arn
}

# Certificate for the SPA's custom domain. Must be us-east-1 — CloudFront
# ignores certificates in any other region.
#
# Validation is DNS, and smartek21.com is hosted on Cloudflare, not Route53.
# That means there is no aws_acm_certificate_validation resource here and there
# cannot be one: Terraform has no way to write the validation record into a zone
# it does not manage. The CNAME is added by hand in Cloudflare (see
# docs/runbooks/custom-domain.md). A certificate whose record was never added
# sits in PENDING_VALIDATION for 72 hours and then fails — which is exactly what
# happened to the training.smartek21.com certificate on 1 July.
resource "aws_acm_certificate" "web" {
  count = var.domain == "" ? 0 : 1

  provider          = aws.us_east_1
  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    # ACM certificates cannot be modified in place; replacing one that is
    # attached to a live distribution would break TLS for the window between
    # destroy and create.
    create_before_destroy = true
  }

  tags = {
    Name = "${local.name_prefix}-web"
  }
}

module "web" {
  source      = "./modules/web"
  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  kms_key_arn = module.kms.key_arn

  domain_name = var.domain
  # Only attach the certificate once ACM reports it ISSUED. Handing CloudFront
  # a PENDING_VALIDATION certificate fails the apply partway through, leaving
  # the distribution mid-update.
  acm_certificate_arn = var.domain == "" ? "" : one(aws_acm_certificate.web[*].arn)
}

module "auth" {
  source            = "./modules/auth"
  name_prefix       = local.name_prefix
  account_id        = data.aws_caller_identity.current.account_id
  region            = var.region
  cloudfront_domain = module.web.distribution_domain_name
  custom_domain     = var.domain
}

module "api" {
  source                 = "./modules/api"
  name_prefix            = local.name_prefix
  env                    = var.env
  region                 = var.region
  vpc_id                 = module.network.vpc_id
  public_subnet_ids      = module.network.public_subnet_ids
  private_subnet_ids     = module.network.private_subnet_ids
  ecr_repository_url     = module.ecr.repository_url
  image_tag              = var.image_tag
  db_url_secret_arn      = module.secrets.db_url_secret_arn
  jwt_signing_secret_arn = module.secrets.jwt_signing_secret_arn
  cognito_user_pool_id   = module.auth.user_pool_id
  cognito_client_id      = module.auth.client_id
  kms_key_arn            = module.kms.key_arn
}

module "data" {
  source                = "./modules/data"
  name_prefix           = local.name_prefix
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = module.network.private_subnet_ids
  api_security_group_id = module.api.api_security_group_id
  master_password       = module.secrets.db_password
  db_url_secret_id      = module.secrets.db_url_secret_id
  kms_key_arn           = module.kms.key_arn
}

# S2-E3: evidence bucket for NDA/MSA signed uploads. Consumed by the API
# task via AGREEMENTS_BUCKET (wave integrator wires the env var into
# module.api once this bucket exists in the target account).
module "storage" {
  source      = "./modules/storage"
  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  kms_key_arn = module.kms.key_arn
}

# S2-E3 Wave 2: scheduled alert scheduler + notification sender workers.
# Reuses the API ECS cluster + SG + subnets to avoid a second Fargate footprint.
module "schedulers" {
  source                   = "./modules/schedulers"
  name_prefix              = local.name_prefix
  env                      = var.env
  region                   = var.region
  ecs_cluster_arn          = module.api.cluster_arn
  private_subnet_ids       = module.network.private_subnet_ids
  task_security_group_ids  = [module.api.api_security_group_id]
  ecr_repository_url       = module.ecr.repository_url
  image_tag                = var.image_tag
  db_url_secret_arn        = module.secrets.db_url_secret_arn
  task_execution_role_arn  = module.api.task_execution_role_arn
  cognito_user_pool_id     = module.auth.user_pool_id
  cognito_client_id        = module.auth.client_id
  audit_export_bucket_name = module.storage.audit_exports_bucket_name
  audit_export_bucket_arn  = module.storage.audit_exports_bucket_arn
}

module "github_oidc" {
  source                      = "./modules/github_oidc"
  name_prefix                 = local.name_prefix
  github_repo                 = var.github_repo
  create_oidc_provider        = var.create_github_oidc_provider
  ecr_repository_arn          = module.ecr.repository_arn
  ecs_cluster_name            = module.api.cluster_name
  ecs_service_name            = module.api.service_name
  task_execution_role_arn     = module.api.task_execution_role_arn
  task_role_arn               = module.api.task_role_arn
  web_bucket_arn              = module.web.bucket_arn
  cloudfront_distribution_arn = module.web.distribution_arn
}

# S7: CloudTrail + GuardDuty + CloudWatch alarms + SNS alerts topic.
module "observability" {
  source                   = "./modules/observability"
  name_prefix              = local.name_prefix
  region                   = var.region
  account_id               = data.aws_caller_identity.current.account_id
  kms_key_arn              = module.kms.key_arn
  rds_instance_id          = module.data.db_instance_id
  rds_allocated_storage_gb = module.data.db_allocated_storage_gb
  ecs_cluster_name         = module.api.cluster_name
  ecs_service_name         = module.api.service_name
  alert_email              = var.alert_email
}
