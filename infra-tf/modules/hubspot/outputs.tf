output "queue_url" {
  value       = aws_sqs_queue.main.url
  description = "URL of the main HubSpot events queue. Fed to api (enqueue side) and schedulers (consumer side) as HUBSPOT_EVENT_QUEUE_URL."
}

output "queue_arn" {
  value       = aws_sqs_queue.main.arn
  description = "ARN of the main HubSpot events queue. Scopes IAM grants for SendMessage / ReceiveMessage / DeleteMessage."
}

output "queue_name" {
  value       = aws_sqs_queue.main.name
  description = "Main queue NAME (SQS CloudWatch dimension). Fed to schedulers module for the freshness alarms."
}

output "dlq_name" {
  value       = aws_sqs_queue.dlq.name
  description = "DLQ NAME for the freshness alarms."
}

output "dlq_arn" {
  value       = aws_sqs_queue.dlq.arn
  description = "ARN of the dead-letter queue. Poison messages land here after 3 receive attempts."
}
