variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev). Role will be <name_prefix>-gha-deploy."
  type        = string
}

variable "github_repo" {
  description = "GitHub 'owner/name' allowed to assume the deploy role via OIDC."
  type        = string
}

variable "create_oidc_provider" {
  description = "Create the IAM OIDC provider for token.actions.githubusercontent.com. Set false if the account already has one."
  type        = bool
  default     = false
}

variable "ecr_repository_arn" {
  description = "ECR repo the deploy role may push to."
  type        = string
}

variable "ecs_cluster_name" {
  description = "ECS cluster the deploy role may manage."
  type        = string
}

variable "ecs_service_name" {
  description = "ECS service the deploy role may update / run tasks against."
  type        = string
}

variable "task_execution_role_arn" {
  description = "Task execution role the deploy role must be allowed to pass when registering new task defs."
  type        = string
}

variable "task_role_arn" {
  description = "Task role the deploy role must be allowed to pass when registering new task defs."
  type        = string
}

variable "web_bucket_arn" {
  description = "S3 bucket ARN the deploy role may sync SPA assets to."
  type        = string
}

variable "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN the deploy role may invalidate."
  type        = string
}
