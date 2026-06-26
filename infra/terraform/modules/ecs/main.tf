# modules/ecs/main.tf

variable "prefix"              {}
variable "vpc_id"              {}
variable "public_subnet_ids"   {}
variable "private_subnet_ids"  {}
variable "security_group_ids"  {}
variable "ecr_api_url"         {}
variable "ecr_dashboard_url"   {}
variable "image_tag"           { default = "latest" }
variable "db_host"             {}
variable "db_name"             {}
variable "db_username"         {}
variable "db_password"         { sensitive = true }
variable "redis_host"          {}
variable "kafka_brokers"       {}
variable "secret_key"          { sensitive = true }
variable "environment"         {}
variable "aws_region"          {}
variable "efs_id"              {}
variable "efs_access_point"    {}

# ── IAM ───────────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["ecs-tasks.amazonaws.com"] }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.prefix}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "${var.prefix}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task_cloudwatch" {
  name = "${var.prefix}-ecs-task-cw"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "arn:aws:logs:*:*:log-group:/fraud-detection/*"
    }]
  })
}

# ── ECS Cluster ───────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "${var.prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = var.environment == "prod" ? "FARGATE" : "FARGATE_SPOT"
    weight            = 1
  }
}

# ── Common environment block ──────────────────────────────────────────────────
locals {
  common_env = [
    { name = "POSTGRES_HOST",           value = var.db_host },
    { name = "POSTGRES_DB",             value = var.db_name },
    { name = "POSTGRES_USER",           value = var.db_username },
    { name = "POSTGRES_PASSWORD",       value = var.db_password },
    { name = "REDIS_HOST",              value = var.redis_host },
    { name = "KAFKA_BOOTSTRAP_SERVERS", value = var.kafka_brokers },
    { name = "SECRET_KEY",              value = var.secret_key },
    { name = "ENVIRONMENT",             value = var.environment },
    { name = "AWS_DEFAULT_REGION",      value = var.aws_region },
    { name = "MODEL_PATH",              value = "/models/fraud_model.pkl" },
  ]
}

# ── API Task Definition ───────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "models"
    efs_volume_configuration {
      file_system_id     = var.efs_id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = var.efs_access_point
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${var.ecr_api_url}:${var.image_tag}"
    essential = true
    portMappings = [{ containerPort = 8000; hostPort = 8000; protocol = "tcp" }]
    environment  = local.common_env
    mountPoints  = [{ sourceVolume = "models"; containerPath = "/models"; readOnly = true }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = "/fraud-detection/api"
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }

    ulimits = [{ name = "nofile"; softLimit = 65536; hardLimit = 65536 }]
  }])
}

# ── Worker Task Definition ────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "models"
    efs_volume_configuration {
      file_system_id     = var.efs_id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = var.efs_access_point
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([{
    name         = "worker"
    image        = "${var.ecr_api_url}:${var.image_tag}"
    essential    = true
    command      = ["python", "worker.py"]
    environment  = local.common_env
    mountPoints  = [{ sourceVolume = "models"; containerPath = "/models"; readOnly = true }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = "/fraud-detection/worker"
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}

# ── Dashboard Task Definition ─────────────────────────────────────────────────
resource "aws_ecs_task_definition" "dashboard" {
  family                   = "${var.prefix}-dashboard"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn

  container_definitions = jsonencode([{
    name      = "dashboard"
    image     = "${var.ecr_dashboard_url}:${var.image_tag}"
    essential = true
    portMappings = [{ containerPort = 80; hostPort = 80; protocol = "tcp" }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = "/fraud-detection/dashboard"
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "dashboard"
      }
    }
  }])
}

# ── ALB ───────────────────────────────────────────────────────────────────────
resource "aws_lb" "main" {
  name               = "${var.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [module_alb_sg_id]   # referenced via data lookup below
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "prod"
  tags = { Name = "${var.prefix}-alb" }
}

data "aws_security_group" "alb" {
  filter {
    name   = "tag:Name"
    values = ["${var.prefix}-alb-sg"]
  }
  vpc_id = var.vpc_id
}

resource "aws_lb" "main_corrected" {
  name               = "${var.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [data.aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "prod"

  lifecycle { create_before_destroy = true }
}

resource "aws_lb_target_group" "api" {
  name        = "${var.prefix}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_target_group" "dashboard" {
  name        = "${var.prefix}-dash-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path = "/"
    interval = 30
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main_corrected.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.dashboard.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern { values = ["/api/*", "/health", "/docs", "/metrics"] }
  }
}

# ── ECS Services ─────────────────────────────────────────────────────────────
resource "aws_ecs_service" "api" {
  name            = "${var.prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.environment == "prod" ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker { enable = true; rollback = true }
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  lifecycle { ignore_changes = [desired_count] }
}

resource "aws_ecs_service" "worker" {
  name            = "${var.prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.environment == "prod" ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }

  deployment_circuit_breaker { enable = true; rollback = true }
}

resource "aws_ecs_service" "dashboard" {
  name            = "${var.prefix}-dashboard"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.dashboard.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.dashboard.arn
    container_name   = "dashboard"
    container_port   = 80
  }
}

# ── Auto-scaling (API) ────────────────────────────────────────────────────────
resource "aws_appautoscaling_target" "api" {
  max_capacity       = 10
  min_capacity       = var.environment == "prod" ? 2 : 1
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${var.prefix}-api-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 65.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "alb_dns_name"    { value = aws_lb.main_corrected.dns_name }
output "alb_arn_suffix"  { value = aws_lb.main_corrected.arn_suffix }
output "cluster_name"    { value = aws_ecs_cluster.main.name }
output "api_service_name"{ value = aws_ecs_service.api.name }
