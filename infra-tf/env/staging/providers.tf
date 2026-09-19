provider "aws" {
  region = var.region

  # AWS CLI profile is set outside Terraform (AWS_PROFILE=lm-arbiter-poc)
  # so the same code works from GitHub Actions with OIDC.

  default_tags {
    tags = {
      Project   = "officeapp"
      Env       = "staging"
      ManagedBy = "terraform"
      Repo      = "smartek21/officeapp-dealgate"
    }
  }
}
