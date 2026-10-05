mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

variables {
  name_prefix               = "officeapp-test"
  env                       = "staging"
  region                    = "us-east-2"
  ecs_cluster_arn           = "arn:aws:ecs:us-east-2:123456789012:cluster/test"
  private_subnet_ids        = ["subnet-00000000000000001"]
  task_security_group_ids   = ["sg-00000000000000001"]
  ecr_repository_url        = "123456789012.dkr.ecr.us-east-2.amazonaws.com/test"
  image_tag                 = "s21-reviewed"
  db_url_secret_arn         = "arn:aws:secretsmanager:us-east-2:123456789012:secret:test-db"
  task_execution_role_arn   = "arn:aws:iam::123456789012:role/test-execution"
  ses_from_address          = "noreply@synthetic.invalid"
  audit_export_bucket_name  = "test-audit"
  audit_export_bucket_arn   = "arn:aws:s3:::test-audit"
  hubspot_event_queue_url   = "https://sqs.us-east-2.amazonaws.com/123456789012/test"
  hubspot_event_queue_arn   = "arn:aws:sqs:us-east-2:123456789012:test"
  hubspot_events_queue_name = "test"
  hubspot_events_dlq_name   = "test-dlq"
  hubspot_token_secret_arn  = "arn:aws:secretsmanager:us-east-2:123456789012:secret:test-hubspot"
}

run "jobs_disabled_until_reviewed_cutover" {
  command = plan
  module { source = "./modules/schedulers" }
  assert {
    condition     = alltrue([for rule in aws_cloudwatch_event_rule.s21_job : rule.state == "DISABLED"])
    error_message = "New S21 workers must not run before the reviewed cutover."
  }
  assert {
    condition     = length(aws_cloudwatch_event_rule.e2e_cleanup) == 0
    error_message = "Scheduled cleanup resources must remain absent until trusted provenance cleanup is reviewed."
  }
  assert {
    condition     = aws_cloudwatch_event_rule.hubspot_intake.state == "DISABLED"
    error_message = "Legacy scheduled HubSpot intake must stay disabled; it accumulated long-running tasks in staging."
  }
  assert {
    condition = alltrue([for definition in aws_ecs_task_definition.s21_job :
    contains(jsondecode(definition.container_definitions)[0].environment, { name = "DEALGATE_TENANT_ID", value = "officeapp-test" })])
    error_message = "Every new worker must receive the same explicit runtime tenant as the API."
  }
}

run "both_jobs_use_exact_release_image" {
  command = plan
  module { source = "./modules/schedulers" }
  variables { s21_jobs_enabled = true }
  assert {
    condition     = alltrue([for rule in aws_cloudwatch_event_rule.s21_job : rule.state == "ENABLED"])
    error_message = "Reviewed cutover must activate both persisted job queues."
  }
  assert {
    condition = alltrue([for name, definition in aws_ecs_task_definition.s21_job :
      jsondecode(definition.container_definitions)[0].image == "123456789012.dkr.ecr.us-east-2.amazonaws.com/test:s21-reviewed" &&
    jsondecode(definition.container_definitions)[0].command[2] == "worker.${name}"])
    error_message = "Worker command and immutable release tag must match each queue."
  }
}
