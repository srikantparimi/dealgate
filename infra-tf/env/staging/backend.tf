# Remote state is intentionally NOT configured for the first staging bootstrap
# so a fresh clone can `terraform init -backend=false` and validate exactly
# like dev does.
#
# Once the team is ready to move staging state to S3, uncomment the block
# below and run `terraform init -migrate-state`. The bucket + lock table are
# the SAME as dev — only the `key` differs, which keeps dev and staging state
# in separate objects under one bucket.
#
# One-time bucket + lock table creation (same as dev, run once per account):
#   aws s3api create-bucket \
#     --bucket officeapp-tfstate-669810405473 \
#     --region us-east-2 \
#     --create-bucket-configuration LocationConstraint=us-east-2 \
#     --profile lm-arbiter-poc
#   aws dynamodb create-table \
#     --table-name officeapp-tfstate-lock \
#     --attribute-definitions AttributeName=LockID,AttributeType=S \
#     --key-schema AttributeName=LockID,KeyType=HASH \
#     --billing-mode PAY_PER_REQUEST \
#     --region us-east-2 \
#     --profile lm-arbiter-poc
#
# terraform {
#   backend "s3" {
#     bucket         = "officeapp-tfstate-669810405473"
#     key            = "dealgate/staging/terraform.tfstate"
#     region         = "us-east-2"
#     dynamodb_table = "officeapp-tfstate-lock"
#     encrypt        = true
#     profile        = "lm-arbiter-poc"
#   }
# }
