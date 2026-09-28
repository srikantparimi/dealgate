output "db_password" {
  value     = random_password.db_master.result
  sensitive = true
}

output "db_password_secret_arn" {
  value = aws_secretsmanager_secret.db_password.arn
}

output "db_url_secret_arn" {
  value = aws_secretsmanager_secret.db_url.arn
}

output "db_url_secret_id" {
  value = aws_secretsmanager_secret.db_url.id
}

output "jwt_signing_secret_arn" {
  value = aws_secretsmanager_secret.jwt_signing.arn
}

output "hubspot_token_secret_arn" {
  value       = data.aws_secretsmanager_secret.hubspot_token.arn
  description = "ARN of the HubSpot private-app token stored in Secrets Manager. Value is never in TF or state — the API/worker task role decrypts it at container start."
}
