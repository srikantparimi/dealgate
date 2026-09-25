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

# S14a.3b (22 Sep 2026): DNS + SES + ACM cert for the app-owned Route 53 zone.
# Replaces the smartek21.com Cloudflare-hosted flow that required a hand-added
# CNAME and stranded the previous cert in PENDING_VALIDATION for weeks. See
# modules/dns for the full design (DKIM + custom MAIL FROM + strict DMARC).
module "dns" {
  source = "./modules/dns"
  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix           = local.name_prefix
  region                = var.region
  root_domain           = "dealgateapp.com"
  app_subdomain         = "app.dealgateapp.com"
  dmarc_reporting_email = "srikanthp@smartek21.com"
}

# The A/AAAA alias records point var.app_subdomain at the CloudFront
# distribution. They live at the root (not module.dns) because module.web
# depends on module.dns.app_certificate_arn — hosting the alias inside
# module.dns would depend on module.web and create a graph cycle.
# Z2FDTNDATAQYW2 is CloudFront's global hosted zone ID (constant for every
# CloudFront distribution).
resource "aws_route53_record" "app_alias_a" {
  zone_id = module.dns.zone_id
  name    = module.dns.app_subdomain
  type    = "A"

  alias {
    name                   = module.web.distribution_domain_name
    zone_id                = "Z2FDTNDATAQYW2"
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "app_alias_aaaa" {
  zone_id = module.dns.zone_id
  name    = module.dns.app_subdomain
  type    = "AAAA"

  alias {
    name                   = module.web.distribution_domain_name
    zone_id                = "Z2FDTNDATAQYW2"
    evaluate_target_health = false
  }
}

module "web" {
  source      = "./modules/web"
  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  kms_key_arn = module.kms.key_arn

  domain_name = var.domain
  # Certificate flows from module.dns. The validation resource in that module
  # blocks until ACM reports the cert ISSUED, so handing it here can never
  # give CloudFront a PENDING cert. Empty string when var.domain is "".
  acm_certificate_arn = var.domain == "" ? "" : module.dns.app_certificate_arn
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
  # S15: SOW bucket ARN feeds the sow_and_bedrock IAM policy (was hand-set
  # on the task role, now TF-owned per rule 12). Computed inline instead of
  # referencing module.storage.sows_bucket_arn because the sows bucket
  # exists in AWS but is not yet in Terraform state (import is s14a.1b
  # scope). The bucket name is deterministic — same pattern as the
  # storage module writes.
  sow_bucket_arn        = "arn:aws:s3:::${local.name_prefix}-sows-${data.aws_caller_identity.current.account_id}"
  agreements_bucket_arn = "arn:aws:s3:::${local.name_prefix}-agreements-${data.aws_caller_identity.current.account_id}"
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
  # S14a.3 (Kanna, 22 Sep 2026): cognito_user_pool_id + cognito_client_id are
  # intentionally NOT set. The scheduler workers (alert_scheduler,
  # notification_sender, renewals_scheduler, audit_export) do not touch
  # Cognito — they read DB, write S3 or SES, emit audit rows. Passing these
  # via module.auth would chain: schedulers task-def → module.auth →
  # var.cloudfront_domain → module.web.aws_cloudfront_distribution.web,
  # which forces a CloudFront update in every schedulers apply. That update
  # cannot land until the dealgate.smartek21.com ACM cert (us-east-1) exits
  # PENDING_VALIDATION — which requires the CNAME on Cloudflare that Task
  # #26 is tracking. Leaving these two vars at their "" defaults is inert
  # for the workers and breaks the graph coupling.
  audit_export_bucket_name = module.storage.audit_exports_bucket_name
  audit_export_bucket_arn  = module.storage.audit_exports_bucket_arn
  # S14a.3b (Kanna, 22 Sep 2026): sender flows from the verified SES domain
  # identity module.dns owns. `noreply@dealgateapp.com` — every mailbox
  # under dealgateapp.com is authorised by the same DKIM keys + SPF/DMARC.
  # Still in SES sandbox so recipients must be verified: Kanna's own
  # srikanthp+dealgate-staging@smartek21.com is verified from S14a.3
  # batch 1 and is the test inbox for the proofs below.
  ses_from_address         = module.dns.ses_from_address
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
