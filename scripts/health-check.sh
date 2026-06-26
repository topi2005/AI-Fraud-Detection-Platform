#!/usr/bin/env bash
# scripts/health-check.sh — verify all platform services are healthy
# Usage: ./scripts/health-check.sh [dev|prod] [alb-dns]

set -euo pipefail

ENV="${1:-dev}"
CLUSTER="fraud-${ENV}-cluster"

echo "══════════════════════════════════════"
echo "  FraudShield Health Check — $ENV"
echo "══════════════════════════════════════"

PASS=0; FAIL=0

check() {
  local name="$1"; shift
  if "$@" &>/dev/null; then
    echo "  ✅ $name"
    ((PASS++))
  else
    echo "  ❌ $name"
    ((FAIL++))
  fi
}

# ECS services
echo ""
echo "ECS Services:"
for SVC in api worker dashboard; do
  STATUS=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services "fraud-${ENV}-${SVC}" \
    --query 'services[0].status' --output text 2>/dev/null || echo "UNKNOWN")
  RUNNING=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services "fraud-${ENV}-${SVC}" \
    --query 'services[0].runningCount' --output text 2>/dev/null || echo "0")
  DESIRED=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services "fraud-${ENV}-${SVC}" \
    --query 'services[0].desiredCount' --output text 2>/dev/null || echo "0")

  if [ "$STATUS" = "ACTIVE" ] && [ "$RUNNING" = "$DESIRED" ]; then
    echo "  ✅ $SVC ($RUNNING/$DESIRED running)"
    ((PASS++))
  else
    echo "  ❌ $SVC — status=$STATUS running=$RUNNING desired=$DESIRED"
    ((FAIL++))
  fi
done

# HTTP health check
if [ -n "${2:-}" ]; then
  echo ""
  echo "HTTP:"
  check "API /health"    curl -sf "http://$2/health"
  check "Dashboard root" curl -sf "http://$2/"
fi

# CloudWatch alarms
echo ""
echo "CloudWatch Alarms:"
ALARMS=$(aws cloudwatch describe-alarms \
  --alarm-name-prefix "fraud-${ENV}" \
  --state-value ALARM \
  --query 'MetricAlarms[].AlarmName' \
  --output text 2>/dev/null || echo "")

if [ -z "$ALARMS" ]; then
  echo "  ✅ No alarms firing"
  ((PASS++))
else
  for ALARM in $ALARMS; do
    echo "  ❌ ALARM: $ALARM"
    ((FAIL++))
  done
fi

echo ""
echo "══════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "══════════════════════════════════════"

exit $FAIL
