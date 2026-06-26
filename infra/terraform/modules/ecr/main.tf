# modules/ecr/main.tf
variable "prefix" {}
variable "repos"  { type = list(string) }

resource "aws_ecr_repository" "repos" {
  for_each             = toset(var.repos)
  name                 = "${var.prefix}-${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration { scan_on_push = true }

  encryption_configuration { encryption_type = "AES256" }

  tags = { Name = "${var.prefix}-${each.key}" }
}

# Keep last 10 tagged images; delete untagged after 1 day
resource "aws_ecr_lifecycle_policy" "repos" {
  for_each   = aws_ecr_repository.repos
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection    = { tagStatus = "untagged"; countType = "sinceImagePushed"; countUnit = "days"; countNumber = 1 }
        action       = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 10 tagged images"
        selection    = { tagStatus = "tagged"; tagPrefixList = ["v", "sha-"]; countType = "imageCountMoreThan"; countNumber = 10 }
        action       = { type = "expire" }
      }
    ]
  })
}

output "repo_urls" {
  value = { for k, v in aws_ecr_repository.repos : k => v.repository_url }
}
