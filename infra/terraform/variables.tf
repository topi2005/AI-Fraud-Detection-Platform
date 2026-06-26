# infra/terraform/variables.tf

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev | staging | prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Must be dev, staging, or prod."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs to deploy subnets into (min 2 for prod)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# ── Database ─────────────────────────────────────────────────────────────────
variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "fraud_user"
}

variable "db_password" {
  description = "RDS master password — use Secrets Manager in prod"
  type        = string
  sensitive   = true
}

variable "rds_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t3.medium"
}

# ── Cache ─────────────────────────────────────────────────────────────────────
variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

# ── Kafka ─────────────────────────────────────────────────────────────────────
variable "msk_instance_type" {
  description = "MSK broker instance type"
  type        = string
  default     = "kafka.t3.small"
}

# ── ECS ───────────────────────────────────────────────────────────────────────
variable "image_tag" {
  description = "Docker image tag to deploy (e.g. git SHA)"
  type        = string
  default     = "latest"
}

variable "api_secret_key" {
  description = "JWT signing secret — minimum 32 chars"
  type        = string
  sensitive   = true
}
