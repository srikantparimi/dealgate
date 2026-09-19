output "db_endpoint" {
  value = aws_db_instance.this.address
}

output "db_port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "db_security_group_id" {
  value = aws_security_group.db.id
}

output "db_instance_id" {
  description = "RDS instance identifier — used as the CloudWatch alarm dimension by modules/observability."
  value       = aws_db_instance.this.id
}

output "db_allocated_storage_gb" {
  description = "Allocated storage of the RDS instance in GB. Used by modules/observability to compute the free-storage alarm threshold."
  value       = aws_db_instance.this.allocated_storage
}
