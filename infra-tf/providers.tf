provider "aws" {
  region = var.region

  # AWS CLI profile is set outside Terraform (AWS_PROFILE=lm-arbiter-poc)
  # so the same code works from GitHub Actions with OIDC.

  default_tags {
    tags = {
      Project   = "officeapp"
      Env       = var.env
      ManagedBy = "terraform"
      Repo      = "smartek21/officeapp-dealgate"
    }
  }
}

# CloudFront only accepts ACM certificates issued in us-east-1, regardless of
# where the distribution's origins live. This alias exists solely to hold the
# SPA's custom-domain certificate; everything else stays in var.region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = "officeapp"
      Env       = var.env
      ManagedBy = "terraform"
      Repo      = "smartek21/officeapp-dealgate"
    }
  }
}
