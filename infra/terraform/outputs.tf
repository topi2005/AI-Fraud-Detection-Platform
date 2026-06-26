# infra/terraform/outputs.tf

output "alb_dns_name" {
  description = "Public ALB DNS — point your domain here"
  value       = module.ecs.alb_dns_name
}

output "ecr_api_url" {
  description = "ECR URL for the API image"
  value       = module.ecr.repo_urls["fraud-api"]
}

output "ecr_dashboard_url" {
  description = "ECR URL for the dashboard image"
  value       = module.ecr.repo_urls["fraud-dashboard"]
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.elasticache.endpoint
  sensitive   = true
}

output "kafka_brokers" {
  description = "MSK bootstrap broker string"
  value       = module.msk.bootstrap_brokers
  sensitive   = true
}

output "efs_id" {
  description = "EFS file system ID (model store)"
  value       = aws_efs_file_system.models.id
}
