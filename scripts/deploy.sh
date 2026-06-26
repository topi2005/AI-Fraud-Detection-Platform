#!/usr/bin/env bash
# scripts/deploy.sh — push a versioned production deploy
# Usage: ./scripts/deploy.sh v1.2.0

set -euo pipefail

TAG="${1:?Usage: ./scripts/deploy.sh <version-tag>}"
AWS_REGION="${AWS_REGION:-us-east-1}"
CLUSTER="${ECS_CLUSTER:-fraud-prod-cluster}"

ECR_API=$(aws ecr describe-repositories \
  --repository-names "fraud-prod-fraud-api" \
  --query 'repositories[0].repositoryUri' --output text)
ECR_DASH=$(aws ecr describe-repositories \
  --repository-names "fraud-prod-fraud-dashboard" \
  --query 'repositories[0].repositoryUri' --output text)

echo "🚀 Deploying $TAG → $CLUSTER"

# Login
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_API"

# Build
docker build -f Dockerfile.api       -t "$ECR_API:$TAG"  .
docker build -f Dockerfile.dashboard -t "$ECR_DASH:$TAG" .

# Push
docker push "$ECR_API:$TAG"
docker push "$ECR_DASH:$TAG"

# Tag latest
docker tag "$ECR_API:$TAG"  "$ECR_API:latest"  && docker push "$ECR_API:latest"
docker tag "$ECR_DASH:$TAG" "$ECR_DASH:latest" && docker push "$ECR_DASH:latest"

# Deploy ECS services
for SVC in api worker dashboard; do
  aws ecs update-service \
    --cluster "$CLUSTER" \
    --service  "fraud-prod-$SVC" \
    --force-new-deployment \
    --query 'service.serviceName' --output text
  echo "  ↳ $SVC deployment triggered"
done

# Wait for API
echo "⏳ Waiting for API to stabilise…"
aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services fraud-prod-api

echo "✅ Deploy $TAG complete"
