locals {
  # Everything in the account gets this prefix so billing / IAM search / Cost
  # Explorer filters split "officeapp" resources from anything else.
  name_prefix = "officeapp-${var.env}"

  common_tags = {
    Project   = "officeapp"
    Env       = var.env
    ManagedBy = "terraform"
  }
}
