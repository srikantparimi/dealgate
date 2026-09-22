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
