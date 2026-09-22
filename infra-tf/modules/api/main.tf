data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

# ------------------------------------------------------------------
# Security groups
# ------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "Internet to ALB on 80."
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name_prefix}-alb-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "HTTP from anywhere"
}

resource "aws_vpc_security_group_egress_rule" "alb_all" {
  security_group_id = aws_security_group.alb.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "ALB egress unrestricted"
}

resource "aws_security_group" "api" {
  name        = "${var.name_prefix}-api-sg"
  description = "Fargate API tasks. Ingress only from the ALB SG."
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name_prefix}-api-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "api_from_alb" {
  security_group_id            = aws_security_group.api.id
  from_port                    = var.container_port
  to_port                      = var.container_port
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.alb.id
  description                  = "API port from ALB"
}

resource "aws_vpc_security_group_egress_rule" "api_all" {
  security_group_id = aws_security_group.api.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "API egress unrestricted (RDS, Secrets Manager, Bedrock, HubSpot, etc.)"
}

# ------------------------------------------------------------------
# ALB
# ------------------------------------------------------------------

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
  idle_timeout       = 60

  tags = { Name = "${var.name_prefix}-alb" }
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api-tg"
  port        = var.container_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path                = "/healthz"
    matcher             = "200-299"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }

  deregistration_delay = 30

  tags = { Name = "${var.name_prefix}-api-tg" }
}

# TODO(certs): add an ACM cert + HTTPS 443 listener once we have a Route53 zone
# for officeapp / DealGate. For dev we run HTTP-only on the ALB DNS name.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ------------------------------------------------------------------
# IAM: task execution role (pulls image, reads secrets, writes logs)
# ------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.name_prefix}-api-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow the execution role to read the two API secrets so ECS can inject them
# into the container before it starts.
data "aws_iam_policy_document" "secrets_read" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      var.db_url_secret_arn,
      var.jwt_signing_secret_arn,
    ]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "${var.name_prefix}-api-exec-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.secrets_read.json
}

# Task role (application runtime perms). Empty at S2; extended in S7 with
# KMS data-key ops so the task can PUT/GET SSE-KMS S3 objects and pull
# secrets that are encrypted under the shared CMK. Bedrock / SES / SQS
# grants get bolted on here as those integrations land.
resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# S7: allow the task role to mint data keys and decrypt under the CMK, but
# only when the call is proxied through S3 or Secrets Manager in this
# region. This mirrors the key-policy delegation on the KMS side — both
# sides must agree before the request goes through. Scoping via ViaService
# means a compromised task can't rip data keys out of KMS directly.
data "aws_iam_policy_document" "task_kms" {
  statement {
    effect = "Allow"
    actions = [
      "kms:GenerateDataKey",
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [var.kms_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values = [
        "s3.${var.region}.amazonaws.com",
        "secretsmanager.${var.region}.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role_policy" "task_kms" {
  name   = "${var.name_prefix}-api-task-kms"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_kms.json
}

# The task execution role also needs Decrypt on the CMK — ECS reads the two
# Secrets Manager secrets *before* the container starts, so it decrypts
# them with the execution role, not the task role.
data "aws_iam_policy_document" "task_execution_kms" {
  statement {
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [var.kms_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "task_execution_kms" {
  name   = "${var.name_prefix}-api-exec-kms"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_kms.json
}

# ------------------------------------------------------------------
# Cluster, log group, task def, service
# ------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/officeapp/${var.env}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # dev cost
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name_prefix}-api"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${var.ecr_repository_url}:${var.image_tag}"
      essential = true
      portMappings = [{
        containerPort = var.container_port
        protocol      = "tcp"
      }]
      environment = concat([
        { name = "DEALGATE_ENV", value = var.env },
        { name = "AWS_REGION", value = var.region },
        { name = "COGNITO_REGION", value = var.region },
        { name = "COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id },
        { name = "COGNITO_CLIENT_ID", value = var.cognito_client_id },
        { name = "PORT", value = tostring(var.container_port) },
        ], var.env == "staging" && var.allow_dev_seed_endpoint ? [
        { name = "ALLOW_DEV_SEED_ENDPOINT", value = "1" },
      ] : [])
      secrets = [
        { name = "POSTGRES_URL", valueFrom = var.db_url_secret_arn },
        { name = "JWT_SIGNING_KEY", valueFrom = var.jwt_signing_secret_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${var.name_prefix}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_port
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 200

  # CI updates the task def image; ignore that drift so `terraform apply` from
  # a laptop doesn't roll deploys backwards.
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.http]
}
