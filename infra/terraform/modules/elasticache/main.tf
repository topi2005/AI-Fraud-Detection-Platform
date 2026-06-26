# modules/elasticache/main.tf
variable "prefix" {}; variable "vpc_id" {}; variable "subnet_ids" {}
variable "security_group_ids" {}
variable "node_type" { default = "cache.t3.micro" }
variable "num_cache_nodes" { default = 1 }

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.prefix}-redis-subnet-group"
  subnet_ids = var.subnet_ids
}

resource "aws_elasticache_parameter_group" "redis7" {
  name   = "${var.prefix}-redis7"
  family = "redis7"

  parameter { name = "maxmemory-policy"; value = "allkeys-lru" }
  parameter { name = "activerehashing";  value = "yes" }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = "${var.prefix}-redis"
  description                = "Fraud detection feature store"
  node_type                  = var.node_type
  num_cache_clusters         = var.num_cache_nodes
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = var.security_group_ids
  parameter_group_name       = aws_elasticache_parameter_group.redis7.name
  engine_version             = "7.1"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = false  # set true + auth_token for prod
  automatic_failover_enabled = var.num_cache_nodes > 1
  snapshot_retention_limit   = 3
  snapshot_window            = "05:00-06:00"

  tags = { Name = "${var.prefix}-redis" }
}

output "endpoint"         { value = aws_elasticache_replication_group.main.primary_endpoint_address }
output "reader_endpoint"  { value = aws_elasticache_replication_group.main.reader_endpoint_address }
