output "secret_arn" {
  value       = aws_secretsmanager_secret.approvers.arn
  description = "ARN of the credentials JSON. Consumed by tests/e2e/fixtures/multi-role-auth.ts."
}

output "secret_name" {
  value       = aws_secretsmanager_secret.approvers.name
  description = "Human-readable secret name, matches the id the fixture reads."
}

output "usernames" {
  value = {
    for slug, _ in {
      submitter = null
      delivery  = null
      hr        = null
      finance   = null
      legal     = null
    } :
    slug => aws_cognito_user.approver[slug].username
  }
  description = "role → Cognito username, for the report + SES verification checklist."
}

output "ses_identities" {
  value       = [for slug, _ in aws_ses_email_identity.approver : aws_ses_email_identity.approver[slug].email]
  description = "SES identities awaiting verification-link clicks by the PO."
}
