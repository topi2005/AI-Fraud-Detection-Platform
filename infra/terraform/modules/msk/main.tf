# modules/msk/main.tf
variable "prefix" {}; variable "vpc_id" {}; variable "subnet_ids" {}
variable "security_group_ids" {}
variable "kafka_version"  { default = "3.6.0" }
variable "instance_type"  { default = "kafka.t3.small" }
variable "num_brokers"    { default = 1 }

resource "aws_msk_configuration" "main" {
  name              = "${var.prefix}-kafka-config"
  kafka_versions    = [var.kafka_version]
  server_properties = <<-PROPS
    auto.create.topics.enable=true
    default.replication.factor=${var.num_brokers > 1 ? 2 : 1}
    min.insync.replicas=${var.num_brokers > 1 ? 2 : 1}
    num.partitions=3
    log.retention.hours=48
    log.segment.bytes=1073741824
    offsets.retention.minutes=10080
  PROPS
}

resource "aws_msk_cluster" "main" {
  cluster_name           = "${var.prefix}-kafka"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.num_brokers

  broker_node_group_info {
    instance_type   = var.instance_type
    client_subnets  = slice(var.subnet_ids, 0, var.num_brokers)
    security_groups = var.security_group_ids

    storage_info {
      ebs_storage_info { volume_size = 100 }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = aws_msk_configuration.main.latest_revision
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS_PLAINTEXT"
      in_cluster    = true
    }
  }

  open_monitoring {
    prometheus {
      jmx_exporter  { enabled_in_broker = true }
      node_exporter  { enabled_in_broker = true }
    }
  }

  logging {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = "/fraud-detection/msk"
      }
    }
  }

  tags = { Name = "${var.prefix}-kafka" }
}

output "bootstrap_brokers"     { value = aws_msk_cluster.main.bootstrap_brokers }
output "bootstrap_brokers_tls" { value = aws_msk_cluster.main.bootstrap_brokers_tls }
output "zookeeper_connect"     { value = aws_msk_cluster.main.zookeeper_connect_string }
