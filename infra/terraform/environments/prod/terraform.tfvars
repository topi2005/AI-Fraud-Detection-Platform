# infra/terraform/environments/prod/terraform.tfvars
# Copy to infra/terraform/ and fill in secrets before applying

aws_region         = "us-east-1"
environment        = "prod"
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

# RDS
db_username        = "fraud_user"
db_password        = "REPLACE_WITH_STRONG_PASSWORD"   # use AWS Secrets Manager
rds_instance_class = "db.t3.medium"

# Redis
redis_node_type    = "cache.t3.small"

# Kafka
msk_instance_type  = "kafka.t3.small"

# ECS
image_tag          = "latest"   # overridden by CI/CD with git SHA

# API
api_secret_key     = "REPLACE_WITH_32_CHAR_RANDOM_SECRET"
