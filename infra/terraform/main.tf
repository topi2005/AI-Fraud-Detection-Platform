# infra/terraform/main.tf
# ─────────────────────────────────────────────────────────────────────────────
# Fraud Detection Platform — AWS Infrastructure
# Provisions: VPC, RDS PostgreSQL, ElastiCache Redis, MSK Kafka,
#             ECR repos, ECS cluster + services, ALB, CloudWatch, IAM
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    random = { source = "hashicorp/random"; version = "~> 3.6" }
  }

  # Remote state — update bucket/key before first apply
  backend "s3" {
    bucket         = "fraud-detection-tfstate"
    key            = "infra/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "fraud-detection-tflock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "fraud-detection"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ── Random suffix for globally-unique names ───────────────────────────────────
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  prefix = "fraud-${var.environment}"
  suffix = random_id.suffix.hex
  name   = "${local.prefix}-${local.suffix}"
}

# ── Networking ────────────────────────────────────────────────────────────────
module "networking" {
  source = "./modules/networking"

  prefix             = local.prefix
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

# ── RDS PostgreSQL ────────────────────────────────────────────────────────────
module "rds" {
  source = "./modules/rds"

  prefix          = local.prefix
  vpc_id          = module.networking.vpc_id
  subnet_ids      = module.networking.private_subnet_ids
  security_group_ids = [module.networking.rds_sg_id]

  db_name         = "fraud_detection"
  db_username     = var.db_username
  db_password     = var.db_password
  instance_class  = var.rds_instance_class
  multi_az        = var.environment == "prod"
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────
module "elasticache" {
  source = "./modules/elasticache"

  prefix         = local.prefix
  vpc_id         = module.networking.vpc_id
  subnet_ids     = module.networking.private_subnet_ids
  security_group_ids = [module.networking.redis_sg_id]

  node_type      = var.redis_node_type
  num_cache_nodes= 1
}

# ── MSK (Managed Kafka) ───────────────────────────────────────────────────────
module "msk" {
  source = "./modules/msk"

  prefix         = local.prefix
  vpc_id         = module.networking.vpc_id
  subnet_ids     = module.networking.private_subnet_ids
  security_group_ids = [module.networking.msk_sg_id]

  kafka_version  = "3.6.0"
  instance_type  = var.msk_instance_type
  num_brokers    = var.environment == "prod" ? 3 : 1
}

# ── ECR Repositories ──────────────────────────────────────────────────────────
module "ecr" {
  source = "./modules/ecr"
  prefix = local.prefix
  repos  = ["fraud-api", "fraud-dashboard", "fraud-ml"]
}

# ── ECS Cluster + Services ────────────────────────────────────────────────────
module "ecs" {
  source = "./modules/ecs"

  prefix             = local.prefix
  vpc_id             = module.networking.vpc_id
  public_subnet_ids  = module.networking.public_subnet_ids
  private_subnet_ids = module.networking.private_subnet_ids
  security_group_ids = [module.networking.ecs_sg_id]

  ecr_api_url       = module.ecr.repo_urls["fraud-api"]
  ecr_dashboard_url = module.ecr.repo_urls["fraud-dashboard"]

  image_tag         = var.image_tag

  # Pass managed service endpoints to containers
  db_host           = module.rds.endpoint
  db_name           = "fraud_detection"
  db_username       = var.db_username
  db_password       = var.db_password
  redis_host        = module.elasticache.endpoint
  kafka_brokers     = module.msk.bootstrap_brokers

  secret_key        = var.api_secret_key
  environment       = var.environment
  aws_region        = var.aws_region

  # EFS for model store
  efs_id            = aws_efs_file_system.models.id
  efs_access_point  = aws_efs_access_point.models.id
}

# ── EFS (model artifact store shared between api + worker) ───────────────────
resource "aws_efs_file_system" "models" {
  creation_token   = "${local.prefix}-models"
  throughput_mode  = "bursting"
  encrypted        = true

  tags = { Name = "${local.prefix}-models" }
}

resource "aws_efs_access_point" "models" {
  file_system_id = aws_efs_file_system.models.id

  posix_user { uid = 1000; gid = 1000 }
  root_directory {
    path = "/models"
    creation_info { owner_uid = 1000; owner_gid = 1000; permissions = "755" }
  }
}

resource "aws_efs_mount_target" "models" {
  for_each        = toset(module.networking.private_subnet_ids)
  file_system_id  = aws_efs_file_system.models.id
  subnet_id       = each.value
  security_groups = [module.networking.efs_sg_id]
}

# ── CloudWatch Log Groups ─────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "api" {
  name              = "/fraud-detection/api"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/fraud-detection/worker"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "dashboard" {
  name              = "/fraud-detection/dashboard"
  retention_in_days = 14
}

# ── CloudWatch Alarms ─────────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.prefix}-api-5xx-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "API 5xx error rate too high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = module.ecs.alb_arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${local.prefix}-api-p99-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  extended_statistic  = "p99"
  threshold           = 2.0      # 2 seconds
  alarm_description   = "API p99 latency > 2s"

  dimensions = {
    LoadBalancer = module.ecs.alb_arn_suffix
  }
}
