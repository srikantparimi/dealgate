# -----------------------------------------------------------------------------
# Staging root — parallel to infra-tf/main.tf (which is dev).
#
# This root instantiates every module the dev root does, under the prefix
# `officeapp-staging-*`, in the SAME AWS account (669810405473). Modules are
# env-agnostic; only name_prefix / sizes change per env, and staging mirrors
# dev sizes (single NAT, t4g.micro RDS, 1x Fargate task).
#
# The account-wide GitHub OIDC provider was already created by the dev apply,
# so `create_github_oidc_provider` defaults to false and the module looks the
# existing provider up via data source. The staging deploy role is named
# `officeapp-staging-gha-deploy`, distinct from dev's role.
# -----------------------------------------------------------------------------

locals {
  # Hard-pinned to staging so nothing in this root can accidentally scribble
  # over dev resources even if someone passes -var env=dev on the CLI.
  name_prefix = "officeapp-staging"

  common_tags = {
    Project   = "officeapp"
    Env       = "staging"
    ManagedBy = "terraform"
  }
}

data "aws_caller_identity" "current" {}

module "network" {
  source      = "../../modules/network"
  name_prefix = local.name_prefix
}

module "ecr" {
  source      = "../../modules/ecr"
  name_prefix = local.name_prefix
}

module "kms" {
  source      = "../../modules/kms"
  name_prefix = local.name_prefix
  region      = var.region
  account_id  = data.aws_caller_identity.current.account_id
}

module "secrets" {
  source      = "../../modules/secrets"
  name_prefix = local.name_prefix
  kms_key_arn = module.kms.key_arn
}

module "web" {
  source      = "../../modules/web"
  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  kms_key_arn = module.kms.key_arn
}

module "auth" {
  source            = "../../modules/auth"
  name_prefix       = local.name_prefix
  account_id        = data.aws_caller_identity.current.account_id
  region            = var.region
  cloudfront_domain = module.web.distribution_domain_name
}

module "api" {
  source                 = "../../modules/api"
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

  allow_dev_seed_endpoint = true
}

module "data" {
  source                = "../../modules/data"
  name_prefix           = local.name_prefix
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = module.network.private_subnet_ids
  api_security_group_id = module.api.api_security_group_id
  master_password       = module.secrets.db_password
  db_url_secret_id      = module.secrets.db_url_secret_id
  kms_key_arn           = module.kms.key_arn
}

module "storage" {
  source      = "../../modules/storage"
  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  kms_key_arn = module.kms.key_arn
}

module "schedulers" {
  source                   = "../../modules/schedulers"
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

# Reuses the account-wide OIDC provider created by the dev apply. The role
# itself is new: `officeapp-staging-gha-deploy`, scoped to the same repo slug
# but permitted for any ref (the workflow's `if:` decides which branch is
# allowed to deploy to staging).
module "github_oidc" {
  source                      = "../../modules/github_oidc"
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

module "observability" {
  source                   = "../../modules/observability"
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
