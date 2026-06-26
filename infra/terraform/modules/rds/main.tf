# modules/rds/main.tf
variable "prefix" {}; variable "vpc_id" {}; variable "subnet_ids" {}
variable "security_group_ids" {}; variable "db_name" {}
variable "db_username" {}; variable "db_password" { sensitive = true }
variable "instance_class" { default = "db.t3.medium" }
variable "multi_az" { default = false }

resource "aws_db_subnet_group" "main" {
  name       = "${var.prefix}-rds-subnet-group"
  subnet_ids = var.subnet_ids
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${var.prefix}-pg16"
  family = "postgres16"

  parameter { name = "log_connections";          value = "1" }
  parameter { name = "log_disconnections";       value = "1" }
  parameter { name = "log_min_duration_statement"; value = "1000" }  # log slow queries >1s
  parameter { name = "shared_preload_libraries"; value = "pg_stat_statements" }
}

resource "aws_db_instance" "main" {
  identifier              = "${var.prefix}-postgres"
  engine                  = "postgres"
  engine_version          = "16.2"
  instance_class          = var.instance_class
  allocated_storage       = 50
  max_allocated_storage   = 500
  storage_encrypted       = true
  storage_type            = "gp3"

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = var.security_group_ids
  parameter_group_name   = aws_db_parameter_group.postgres.name

  multi_az               = var.multi_az
  backup_retention_period= 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "Mon:04:00-Mon:05:00"
  deletion_protection    = var.multi_az
  skip_final_snapshot    = !var.multi_az
  final_snapshot_identifier = var.multi_az ? "${var.prefix}-final-snapshot" : null

  performance_insights_enabled = true
  monitoring_interval         = 60
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = { Name = "${var.prefix}-postgres" }
}

output "endpoint" { value = aws_db_instance.main.endpoint }
output "arn"      { value = aws_db_instance.main.arn }
