# Remote state — S14a.1 (22 September 2026).
#
# The state bucket + lock table are created + owned by
# `infra-tf/bootstrap/` (its own tiny root, local state — never merge
# it into this backend). Adopted per s14a.1 to close the state-drift
# gap that S14a exposed.
#
# Migration on the first operator's machine (one-time):
#   cd infra-tf
#   terraform init -migrate-state
# Answer "yes" to copy the local `terraform.tfstate` to S3. After the
# migration completes, delete the local `terraform.tfstate*` files.
#
# The env key is `dealgate/staging/terraform.tfstate` because
# `infra-tf/` IS the staging environment (name_prefix `officeapp-dev`
# is a historical artefact; see docs/adr/0001-infra-tf-is-staging.md).

terraform {
  backend "s3" {
    bucket         = "officeapp-tfstate-669810405473"
    key            = "dealgate/staging/terraform.tfstate"
    region         = "us-east-2"
    dynamodb_table = "officeapp-tfstate-lock"
    encrypt        = true
    profile        = "lm-arbiter-poc"
  }
}
