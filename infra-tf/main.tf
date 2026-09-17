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

module "secrets" {
  source      = "./modules/secrets"
  name_prefix = local.name_prefix
}

module "web" {
  source      = "./modules/web"
  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
}

module "auth" {
  source            = "./modules/auth"
  name_prefix       = local.name_prefix
  account_id        = data.aws_caller_identity.current.account_id
  region            = var.region
  cloudfront_domain = module.web.distribution_domain_name
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
}

module "data" {
  source                = "./modules/data"
  name_prefix           = local.name_prefix
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = module.network.private_subnet_ids
  api_security_group_id = module.api.api_security_group_id
  master_password       = module.secrets.db_password
  db_url_secret_id      = module.secrets.db_url_secret_id
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
