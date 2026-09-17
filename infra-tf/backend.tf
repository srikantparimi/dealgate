# Remote state is intentionally NOT configured for the first bootstrap so a
# fresh clone can `terraform init -backend=false` and validate.
#
# After the first apply creates the state bucket + lock table below, uncomment
# and re-run `terraform init -migrate-state` to move local state to S3.
#
# Suggested one-time bootstrap (run manually, not through this stack):
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
#     key            = "dealgate/dev/terraform.tfstate"
#     region         = "us-east-2"
#     dynamodb_table = "officeapp-tfstate-lock"
#     encrypt        = true
#     profile        = "lm-arbiter-poc"
#   }
# }
