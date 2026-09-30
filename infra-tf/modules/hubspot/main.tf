# -----------------------------------------------------------------------------
# S19 slice 1 §B3: SQS queue for HubSpot webhook events.
#
# The webhook receiver (api) enqueues raw HubSpot events; the consumer worker
# (worker.hubspot_intake, run as a scheduled Fargate task on a 5-minute tick)
# long-polls and processes each message by re-reading the deal from the
# HubSpot CRM API — the webhook payload is untrusted per rule 7 and only
# carries an id + event type. Failed processing hits the DLQ after 3
# receive-attempts so a poison message can't stall the queue.
#
# IAM: this module only creates the SQS resources. The grant policies
# (SendMessage on api-task, ReceiveMessage/Delete on schedulers-task) live in
# their respective modules so the dependency graph is one-way (hubspot →
# consumers, never the reverse).
# -----------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  name                       = "${var.name_prefix}-hubspot-events-dlq"
  message_retention_seconds  = 1209600 # 14 days — the SQS max, matches ops runbook window for triage.
  visibility_timeout_seconds = 30
  kms_master_key_id          = var.kms_key_arn
  kms_data_key_reuse_period_seconds = 300

  tags = { Name = "${var.name_prefix}-hubspot-events-dlq" }
}

resource "aws_sqs_queue" "main" {
  name                       = "${var.name_prefix}-hubspot-events"
  message_retention_seconds  = 345600 # 4 days — enough for weekend + backlog drain; DLQ holds anything older.
  visibility_timeout_seconds = 300    # 5 minutes per B5; consumer processes a batch and deletes, must exceed longest handle.
  receive_wait_time_seconds  = 20     # long-poll per B5.
  kms_master_key_id          = var.kms_key_arn
  kms_data_key_reuse_period_seconds = 300

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Name = "${var.name_prefix}-hubspot-events" }
}
