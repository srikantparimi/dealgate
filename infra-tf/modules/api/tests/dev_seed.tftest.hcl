mock_provider "aws" {
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

variables {
  name_prefix            = "officeapp-test"
  env                    = "staging"
  region                 = "us-east-2"
  vpc_id                 = "vpc-00000000000000001"
  public_subnet_ids      = ["subnet-00000000000000001", "subnet-00000000000000002"]
  private_subnet_ids     = ["subnet-00000000000000003"]
  ecr_repository_url     = "123456789012.dkr.ecr.us-east-2.amazonaws.com/test"
  image_tag              = "test"
  db_url_secret_arn      = "arn:aws:secretsmanager:us-east-2:123456789012:secret:test-db"
  jwt_signing_secret_arn = "arn:aws:secretsmanager:us-east-2:123456789012:secret:test-jwt"
  cognito_user_pool_id   = "us-east-2_test"
  cognito_client_id      = "test"
  kms_key_arn            = "arn:aws:kms:us-east-2:123456789012:key/00000000-0000-0000-0000-000000000001"
}

run "disabled_by_default" {
  command = plan
  assert {
    condition     = !contains([for entry in jsondecode(aws_ecs_task_definition.api.container_definitions)[0].environment : entry.name], "ALLOW_DEV_SEED_ENDPOINT")
    error_message = "Seed access must default to absent."
  }
}

run "staging_opt_in" {
  command = plan
  variables { allow_dev_seed_endpoint = true }
  assert {
    condition     = contains(jsondecode(aws_ecs_task_definition.api.container_definitions)[0].environment, { name = "ALLOW_DEV_SEED_ENDPOINT", value = "1" })
    error_message = "Staging's explicit seed opt-in must be managed in the task definition."
  }
}

run "production_cannot_opt_in" {
  command = plan
  variables {
    env                     = "prod"
    allow_dev_seed_endpoint = true
  }
  assert {
    condition     = !contains([for entry in jsondecode(aws_ecs_task_definition.api.container_definitions)[0].environment : entry.name], "ALLOW_DEV_SEED_ENDPOINT")
    error_message = "Production must omit the seed flag even if opted in."
  }
}
