variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "env" {
  description = "Environment slug written into DEALGATE_ENV env var."
  type        = string
}

variable "allow_dev_seed_endpoint" {
  description = "Explicit staging-only seed endpoint opt-in; ignored outside staging."
  type        = bool
  default     = false
}

variable "region" {
  description = "AWS region; forwarded to task env as AWS_REGION."
  type        = string
}

variable "vpc_id" {
  description = "VPC that hosts the ALB and Fargate tasks."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the internet-facing ALB."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnets for Fargate tasks."
  type        = list(string)
}

variable "ecr_repository_url" {
  description = "ECR repo URL; combined with image_tag into the task image reference."
  type        = string
}

variable "image_tag" {
  description = "Image tag to run. Bootstrap = 'bootstrap'; CI overrides per deploy."
  type        = string
}

variable "db_url_secret_arn" {
  description = "ARN of the Secrets Manager secret holding POSTGRES_URL. Injected via ECS `secrets`."
  type        = string
}

variable "jwt_signing_secret_arn" {
  description = "ARN of the Secrets Manager secret with the JWT signing key."
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito user pool ID (env var on the task)."
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito app client ID (env var on the task)."
  type        = string
}

variable "container_port" {
  description = "Port the API listens on inside the container."
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "Fargate task CPU units. 256 = 0.25 vCPU (cheapest)."
  type        = number
  default     = 256
}

variable "memory" {
  description = "Fargate task memory (MiB). 512 pairs with 256 CPU."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Task count. 1 for dev."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the API log group."
  type        = number
  default     = 14
}

# S7: the API task talks to KMS transparently through S3 (SSE-KMS PUT/GET)
# and Secrets Manager (secret decrypt on start). This is the CMK ARN it is
# allowed to invoke. Passed in from the root stack so this module doesn't
# need a data lookup on the alias.
variable "kms_key_arn" {
  description = "ARN of the customer-managed KMS key the task role needs GenerateDataKey / Decrypt on."
  type        = string
}
