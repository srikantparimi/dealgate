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

variable "sow_extract_model_id" {
  description = "Bedrock inference-profile id for SOW extraction. Must be a `us.` or `global.` cross-region profile that exists in the account per `aws bedrock list-inference-profiles --region <region>` AND has been enabled for the account (some models require an AWS Marketplace subscription — Opus 4.7 does, Sonnet 4.6 does not). Do NOT set to a bare model id — every Anthropic model in this account is INFERENCE_PROFILE-only and returns ValidationException otherwise. S15 (22 Sep 2026): default is Sonnet 4.6 (works today, ~5x cheaper than Opus). Opus 4.7 needs `aws bedrock` marketplace subscribe first; then switch this + the sow_and_bedrock IAM policy ARN."
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
}

variable "sow_bucket_arn" {
  description = "ARN of the SOWs S3 bucket. Wired into the sow_and_bedrock task-role policy for PutObject/GetObject/AbortMultipartUpload on the `sow/*` prefix + ListBucket at the root."
  type        = string
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
