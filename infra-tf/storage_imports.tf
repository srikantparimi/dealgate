# S21 review-only adoption of existing staging buckets, observed 2026-10-02.
# These declarations do not change state until a human-approved root apply.
# Never recreate a bucket to resolve a missing Terraform state entry.
import {
  to = module.storage.aws_s3_bucket.sows
  id = "officeapp-dev-sows-669810405473"
}
import {
  to = module.storage.aws_s3_bucket_versioning.sows
  id = "officeapp-dev-sows-669810405473"
}
import {
  to = module.storage.aws_s3_bucket_server_side_encryption_configuration.sows
  id = "officeapp-dev-sows-669810405473"
}
import {
  to = module.storage.aws_s3_bucket_public_access_block.sows
  id = "officeapp-dev-sows-669810405473"
}
import {
  to = module.storage.aws_s3_bucket.agreements
  id = "officeapp-dev-agreements-669810405473"
}
import {
  to = module.storage.aws_s3_bucket_versioning.agreements
  id = "officeapp-dev-agreements-669810405473"
}
import {
  to = module.storage.aws_s3_bucket_server_side_encryption_configuration.agreements
  id = "officeapp-dev-agreements-669810405473"
}
import {
  to = module.storage.aws_s3_bucket_public_access_block.agreements
  id = "officeapp-dev-agreements-669810405473"
}
