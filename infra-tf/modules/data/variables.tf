variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "vpc_id" {
  description = "VPC to place the RDS security group in."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the DB subnet group. Must be at least two AZs for RDS to accept the group."
  type        = list(string)
}

variable "api_security_group_id" {
  description = "Security group of the ECS API tasks; only source allowed to reach 5432."
  type        = string
}

variable "master_password" {
  description = "RDS master password (from the secrets module). Sensitive."
  type        = string
  sensitive   = true
}

variable "db_url_secret_id" {
  description = "Secrets Manager secret id where the composed postgresql:// URL is written."
  type        = string
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "dealgate"
}

variable "db_username" {
  description = "RDS master username."
  type        = string
  default     = "dealgate_admin"
}

variable "instance_class" {
  description = "RDS instance class. db.t4g.micro is the cheapest ARM burstable option that supports Postgres 16."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  description = "gp3 storage size in GB."
  type        = number
  default     = 20
}
