resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.name_prefix}-db-subnets"
  }
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db-sg"
  description = "Postgres 5432 open only to the API security group."
  vpc_id      = var.vpc_id

  tags = {
    Name = "${var.name_prefix}-db-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_api" {
  security_group_id            = aws_security_group.db.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  referenced_security_group_id = var.api_security_group_id
  description                  = "Postgres from ECS API tasks"
}

resource "aws_vpc_security_group_egress_rule" "db_all_out" {
  security_group_id = aws_security_group.db.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "Egress unrestricted (RDS makes no outbound connections in practice)"
}

resource "aws_db_parameter_group" "pg16" {
  name        = "${var.name_prefix}-pg16"
  family      = "postgres16"
  description = "Postgres 16 params for ${var.name_prefix}"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-db"
  engine         = "postgres"
  engine_version = "16.10"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = var.master_password

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  parameter_group_name   = aws_db_parameter_group.pg16.name

  publicly_accessible = false
  multi_az            = false # dev; flip to true for prod (ADR 0001)
  deletion_protection = false # dev; flip to true for prod

  backup_retention_period = 7
  backup_window           = "07:00-08:00"
  maintenance_window      = "sun:08:15-sun:09:15"

  performance_insights_enabled = false
  monitoring_interval          = 0

  skip_final_snapshot       = true # dev; set false for prod and configure final_snapshot_identifier
  final_snapshot_identifier = null

  apply_immediately = true

  tags = {
    Name = "${var.name_prefix}-db"
  }
}

# Write the composed DSN into the pre-created secret so the API just reads
# ${var.db_url_secret_id} without knowing password / host separately.
resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id = var.db_url_secret_id
  secret_string = format(
    "postgresql+psycopg://%s:%s@%s:%d/%s?sslmode=require",
    var.db_username,
    var.master_password,
    aws_db_instance.this.address,
    aws_db_instance.this.port,
    var.db_name,
  )
}
