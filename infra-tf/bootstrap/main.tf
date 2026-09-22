# -----------------------------------------------------------------------------
# Terraform state bootstrap — S14a.1 (22 September 2026).
#
# The one root allowed to hold LOCAL state indefinitely: it creates the two
# resources every other root depends on for remote state — an S3 bucket for
# the tfstate files and a DynamoDB table for the state lock. Every other
# root in this repo then uses:
#
#   terraform { backend "s3" {
#     bucket = "officeapp-tfstate-669810405473"
#     key    = "dealgate/<env>/terraform.tfstate"
#     region = "us-east-2"
#     dynamodb_table = "officeapp-tfstate-lock"
#     encrypt = true
#   } }
#
# Why local state here (and only here): remote state has to live somewhere.
# If this root pushed its own state into the very bucket it manages, a bad
# apply could delete the bucket and corrupt its own state. The industry
# pattern is "local state for the bootstrap, remote state for everything
# else, and never delete the bootstrap." The local state file is
# `infra-tf/bootstrap/terraform.tfstate` — committed via a targeted
# `!` in .gitignore below (see .gitignore entry).
#
# CLAUDE.md rule 12: no console/CLI infra changes. This includes the
# state bucket + lock table — they land via this Terraform root, not
# via `aws s3api create-bucket`.
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile

  default_tags {
    tags = {
      Project   = "officeapp"
      Component = "terraform-state"
      ManagedBy = "terraform"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-2"
}

variable "profile" {
  type    = string
  default = "lm-arbiter-poc"
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "officeapp-tfstate-${data.aws_caller_identity.current.account_id}"
  lock_table  = "officeapp-tfstate-lock"
}

resource "aws_s3_bucket" "state" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "lock" {
  name         = local.lock_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "lock_table" {
  value = aws_dynamodb_table.lock.name
}
