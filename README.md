# AI Fraud Detection Platform

A production-grade, end-to-end fraud detection system that ingests real-time banking transactions, scores each one with a machine learning ensemble in under 10ms, surfaces alerts to analysts through an interactive dashboard, and deploys to AWS via fully automated CI/CD.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Phase 1 — Data Layer](#phase-1--data-layer)
- [Phase 2 — ML Engine](#phase-2--ml-engine)
- [Phase 3 — Risk Scoring API](#phase-3--risk-scoring-api)
- [Phase 4 — Dashboard](#phase-4--dashboard)
- [Phase 5 — Infrastructure & CI/CD](#phase-5--infrastructure--cicd)
- [Fraud Patterns](#fraud-patterns)
- [ML Model Details](#ml-model-details)
- [API Reference](#api-reference)
- [AWS Deployment](#aws-deployment)
- [Configuration](#configuration)
- [Key Metrics](#key-metrics)

---

## Overview

FraudShield processes a continuous stream of banking transactions through a five-layer pipeline:

1. A **Kafka producer** simulates realistic transactions including six distinct fraud patterns
2. A **PostgreSQL schema** persists transactions, alerts, feature vectors, and audit history
3. A **Scikit-learn + XGBoost ensemble** scores each transaction for fraud probability
4. A **FastAPI service** exposes real-time scoring, alert management, and analytics endpoints
5. A **React dashboard** gives fraud analysts live monitoring, alert resolution, and model health visibility

Everything runs locally with one Docker Compose command, and deploys to production on AWS ECS Fargate via a GitHub Actions pipeline.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                              │
│  Kafka Producer → transactions.raw topic                        │
│  PostgreSQL (transactions, alerts, features, audit)             │
│  Redis (customer profile cache, rolling aggregates)             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                        ML ENGINE                                │
│  Feature Engineering (23 features across 5 groups)             │
│  SMOTE oversampling → RF (n=300) + XGBoost (n=400) ensemble     │
│  MLflow experiment tracking · FraudScorer inference class       │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                       API LAYER                                 │
│  FastAPI · /score · /score/batch · /alerts · /analytics         │
│  Kafka worker (consumer → score → persist → alert → publish)    │
│  JWT auth · Prometheus metrics · CloudWatch logging             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                      DASHBOARD                                  │
│  React + Recharts · 5 pages · live polling · JWT auth           │
│  Overview · Alerts · Transactions · Score sandbox · Model       │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                    INFRASTRUCTURE                               │
│  Docker (multi-stage, non-root) · Terraform (6 modules)         │
│  AWS ECS Fargate · RDS · ElastiCache · MSK · ECR · EFS · ALB   │
│  GitHub Actions CI/CD · OIDC auth · Trivy scanning             │
└─────────────────────────────────────────────────────────────────┘
```

**Transaction flow:** Producer → `transactions.raw` (Kafka) → Scoring Worker → PostgreSQL + `transactions.scored` + `fraud.alerts` → FastAPI → React Dashboard

---

## Tech Stack

| Layer | Technologies |
|---|---|
| Data | PostgreSQL 16, Apache Kafka 3.6, Redis 7 |
| ML | Scikit-learn, XGBoost, SMOTE, MLflow, Pandas, NumPy |
| API | FastAPI, Uvicorn, Pydantic v2, SQLAlchemy, kafka-python |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Frontend | React 18, React Router, Recharts, Vite, nginx |
| Containers | Docker (multi-stage), Docker Compose |
| IaC | Terraform 1.7+ |
| Cloud | AWS ECS Fargate, RDS, ElastiCache, MSK, ECR, EFS, ALB, CloudWatch |
| CI/CD | GitHub Actions, OIDC federation, Docker Buildx, Trivy |
| Monitoring | Prometheus, Grafana, CloudWatch alarms |

---

## Project Structure

```
fraud-detection/
├── data-layer/
│   ├── migrations/
│   │   └── 001_initial_schema.sql   # Full PostgreSQL schema (7 tables)
│   ├── models.py                    # TransactionEvent + CustomerProfile dataclasses
│   ├── simulator/
│   │   └── producer.py              # Kafka transaction producer with fraud injection
│   └── requirements.txt
│
├── ml-engine/
│   ├── data/
│   │   └── generate_dataset.py      # Synthetic labelled dataset generator
│   ├── features.py                  # Feature schema — offline + online modes
│   ├── train.py                     # RF + XGBoost ensemble training + MLflow tracking
│   ├── inference.py                 # FraudScorer class (used by API)
│   ├── models/                      # fraud_model.pkl + model_meta.json (git-ignored)
│   └── requirements.txt
│
├── api/
│   ├── main.py                      # FastAPI app with lifespan + middleware
│   ├── config.py                    # Pydantic settings
│   ├── dependencies.py              # DI: DB conn, Redis, scorer, Kafka producer
│   ├── schemas.py                   # All Pydantic request/response models
│   ├── worker.py                    # Kafka scoring consumer
│   ├── middleware/
│   │   └── auth.py                  # JWT auth + user store
│   ├── routers/
│   │   ├── scoring.py               # POST /score, /score/batch, GET /model/health
│   │   ├── alerts.py                # CRUD alert management
│   │   ├── analytics.py             # Dashboard data endpoints
│   │   └── auth.py                  # POST /token, GET /me
│   ├── services/
│   │   └── alert_service.py         # Alert creation logic
│   ├── tests/
│   │   └── test_api.py              # 25 integration tests (mocked deps)
│   └── requirements.txt
│
├── dashboard/
│   ├── src/
│   │   ├── lib/api.js               # Typed API client + JWT auth
│   │   ├── hooks/useApi.js          # Data fetching + polling hook
│   │   ├── components/
│   │   │   ├── layout/              # Sidebar, UI primitives (Card, Badge, StatCard)
│   │   │   ├── charts/              # TrendChart (area), CategoryChart (bar)
│   │   │   └── alerts/              # AlertFeed with live resolution
│   │   └── pages/
│   │       ├── Overview.jsx         # KPIs + charts + alert feed
│   │       ├── AlertsPage.jsx       # Full alert management table
│   │       ├── ActivityPage.jsx     # Live transaction feed with score bars
│   │       ├── ScorePage.jsx        # ML scoring sandbox with presets
│   │       └── ModelPage.jsx        # Model metrics + system health
│   └── package.json
│
├── infra/
│   ├── prometheus.yml               # Prometheus scrape config
│   └── terraform/
│       ├── main.tf                  # Root: wires all modules, EFS, CloudWatch alarms
│       ├── variables.tf
│       ├── outputs.tf
│       └── modules/
│           ├── networking/          # VPC, subnets, NAT, 6 security groups
│           ├── ecs/                 # Cluster, task defs, services, ALB, auto-scaling
│           ├── rds/                 # PostgreSQL 16 with Multi-AZ, backups, insights
│           ├── elasticache/         # Redis 7 replication group
│           ├── msk/                 # Managed Kafka with JMX metrics
│           └── ecr/                 # Repos with lifecycle policies + image scanning
│
├── .github/workflows/
│   └── deploy.yml                   # 5-stage CI/CD pipeline
├── scripts/
│   ├── deploy.sh                    # One-command production deploy
│   └── health-check.sh             # Full system health verification
├── Dockerfile.api                   # Multi-stage, non-root, production hardened
├── Dockerfile.dashboard             # Multi-stage nginx
├── Dockerfile.ml                    # Training job image
├── docker-compose.yml               # Local dev (all services)
├── docker-compose.prod.yml          # Production overrides + monitoring stack
└── RUNBOOK.md                       # Ops procedures, troubleshooting, scaling
```

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Node.js 20+

### 1. Clone and configure

```bash
git clone <repo-url>
cd fraud-detection
cp .env.example .env          # defaults work for local dev
```

### 2. Start infrastructure

```bash
docker compose up -d postgres redis kafka kafka-ui
# Kafka UI: http://localhost:8080
```

### 3. Train the ML model

```bash
cd ml-engine
pip install -r requirements.txt

python data/generate_dataset.py    # generates 100k labelled transactions (~10s)
python train.py                    # trains ensemble, saves model (~2-3 min)

# Optional: view MLflow experiments
mlflow ui --backend-store-uri sqlite:///models/mlflow.db
# → http://localhost:5000
```

### 4. Start the API and worker

```bash
cd api
pip install -r requirements.txt

uvicorn main:app --reload --port 8000 &   # API: http://localhost:8000
python worker.py &                          # Kafka scoring consumer

# API docs: http://localhost:8000/docs
```

### 5. Start the dashboard

```bash
cd dashboard
npm install
npm run dev
# → http://localhost:3000
# Login: admin / admin123
```

### 6. Start the transaction simulator

```bash
cd data-layer
pip install -r requirements.txt
python simulator/producer.py
# Produces 10 TPS with 2% fraud rate
```

### Full Docker start

```bash
# After training the model locally (step 3 above):
docker compose build
docker compose up -d
```

---

## Phase 1 — Data Layer

### PostgreSQL Schema

Seven tables covering the full fraud detection domain:

| Table | Purpose |
|---|---|
| `customers` | Account holders with risk tier classification |
| `accounts` | Bank accounts with balance and credit limit |
| `merchants` | Merchant registry with category and risk flag |
| `transactions` | Core fact table — amount, location, ML score, status |
| `fraud_alerts` | Alert lifecycle with resolution workflow |
| `transaction_features` | Materialized ML feature vectors per transaction |
| `audit_log` | Full change history for compliance |

The `transactions` table stores 30+ columns including geo-coordinates, IP address, fraud score (0.0–1.0), risk tier, model version, and scored timestamp. Partial indexes on flagged/fraud rows keep dashboard queries fast at scale.

### Kafka Producer Simulator

```bash
# Configuration via .env
SIMULATOR_TPS=10              # transactions per second
SIMULATOR_FRAUD_RATE=0.02     # 2% fraud injection rate
SIMULATOR_NUM_CUSTOMERS=500   # synthetic account pool
SIMULATOR_BURST_ENABLED=true  # random velocity-abuse bursts
```

The producer maintains 500 synthetic customers with home GPS coordinates cached in Redis, generates log-normal amount distributions, and randomly triggers fraud bursts of 15–40 rapid transactions against a single account.

---

## Phase 2 — ML Engine

### Feature Groups

| Group | Features |
|---|---|
| Velocity | `tx_count_1h/24h/7d`, `amount_sum_1h/24h/7d` |
| Behavioural | `amount_zscore`, `avg/std_amount_30d`, `unique_merchants_7d`, `unique_countries_7d` |
| Geo anomaly | `geo_distance_km`, `time_since_last_tx_min`, `impossible_travel` |
| Temporal | `hour_of_day`, `day_of_week`, `is_night`, `is_weekend` |
| Merchant risk | `merchant_fraud_rate_30d`, `is_high_risk_merchant` |

### Training Pipeline

```
ColumnTransformer (impute + scale + encode)
    → SMOTE (sampling_strategy=0.15)
        → VotingClassifier (soft, weights=[1, 1.5])
            ├── RandomForestClassifier (n=300, class_weight='balanced')
            └── XGBClassifier (n=400, scale_pos_weight=40)
```

```bash
cd ml-engine
python train.py --data data/transactions.csv --threshold 0.35
```

MLflow logs every run with parameters, all five metrics, and artifact plots. The trained model is saved as `models/fraud_model.pkl` alongside a `model_meta.json` sidecar consumed by the API at startup.

### Risk Tiers

| Score | Tier | Action |
|---|---|---|
| ≥ 80% | `critical` | Auto-decline + alert analyst |
| 55–80% | `high` | Flag for manual review |
| 30–55% | `medium` | Monitor, soft challenge |
| < 30% | `low` | Approve |

---

## Phase 3 — Risk Scoring API

### Endpoints

```
POST   /api/v1/auth/token              Get JWT access token
GET    /api/v1/auth/me                 Current user info

POST   /api/v1/score                   Score a single transaction
POST   /api/v1/score/batch             Score up to 500 transactions
GET    /api/v1/model/health            Live model metrics

GET    /api/v1/alerts                  List alerts (filterable, paginated)
GET    /api/v1/alerts/stats            24h KPI counts by severity + status
GET    /api/v1/alerts/{id}             Single alert detail
PATCH  /api/v1/alerts/{id}            Update alert status

GET    /api/v1/analytics/summary       Fraud KPIs for any time window
GET    /api/v1/analytics/trend         Hourly/daily fraud rate over time
GET    /api/v1/analytics/by-category   Breakdown by merchant category
GET    /api/v1/analytics/by-country    Breakdown by country
GET    /api/v1/analytics/transactions  Paginated transaction history

GET    /health                         System health (all dependencies)
GET    /metrics                        Prometheus metrics
```

### Scoring a transaction

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin&password=admin123" | jq -r .access_token)

# Score a transaction
curl -X POST http://localhost:8000/api/v1/score \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tx_id": "tx-001",
    "account_id": "acc-001",
    "amount": 8500.00,
    "transaction_type": "transfer",
    "channel": "wire",
    "country_code": "RO"
  }'
```

```json
{
  "tx_id": "tx-001",
  "fraud_score": 0.8734,
  "risk_tier": "critical",
  "is_fraud_pred": true,
  "threshold": 0.35,
  "model_version": "a3f9c21b",
  "latency_ms": 6.4
}
```

### Running tests

```bash
cd api
pytest tests/ -v --cov=. --cov-report=term-missing
# 25 tests across auth, scoring, alerts, analytics, and system
```

---

## Phase 4 — Dashboard

Five pages, all requiring JWT authentication:

| Page | Path | Refresh Rate |
|---|---|---|
| Overview | `/` | KPIs: 15s · Trend: 30s · Alerts: 10s |
| Alerts | `/alerts` | 15s |
| Transactions | `/activity` | 8s |
| Score Sandbox | `/score` | On submit |
| Model Health | `/model` | 60s |

**Built-in accounts:**

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Full access |
| `analyst` | `analyst123` | Read + alert resolution |

---

## Phase 5 — Infrastructure & CI/CD

### Local production stack

```bash
# Start with production overrides (resource limits, CloudWatch logging, monitoring)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Grafana: http://localhost:3001 (admin / admin)
# Prometheus: http://localhost:9090
```

### AWS Deployment

#### First-time setup

```bash
# 1. Bootstrap Terraform state
aws s3 mb s3://fraud-detection-tfstate --region us-east-1
aws dynamodb create-table --table-name fraud-detection-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# 2. Configure and apply infrastructure
cd infra/terraform
cp environments/prod/terraform.tfvars terraform.tfvars
# Edit terraform.tfvars with real values

terraform init
terraform plan -out=tfplan
terraform apply tfplan          # ~15 min (RDS + MSK take the longest)

# 3. Build and push images
ECR_API=$(terraform output -raw ecr_api_url)
TAG="sha-$(git rev-parse --short HEAD)"

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_API

docker build -f Dockerfile.api -t $ECR_API:$TAG . && docker push $ECR_API:$TAG
```

#### CI/CD pipeline

The GitHub Actions pipeline runs automatically on every push and tag:

```
PR pushed      → test + terraform validate
main pushed    → test → build → push to ECR → deploy dev → smoke test
v* tag pushed  → test → build → push to ECR → deploy dev → [manual approval] → deploy prod → GitHub Release
```

Configure these secrets in GitHub → Settings → Secrets:

| Secret | Value |
|---|---|
| `AWS_ROLE_ARN` | IAM role for OIDC federation |
| `AWS_REGION` | e.g. `us-east-1` |
| `ECR_REGISTRY` | e.g. `123456789012.dkr.ecr.us-east-1.amazonaws.com` |
| `ECS_CLUSTER_DEV` | `fraud-dev-cluster` |
| `ECS_CLUSTER_PROD` | `fraud-prod-cluster` |
| `POSTGRES_PASSWORD` | Database password |
| `API_SECRET_KEY` | JWT signing secret (min 32 chars) |

#### AWS resources provisioned

| Service | Purpose |
|---|---|
| ECS Fargate | API (2 vCPU / 4GB in prod), Worker, Dashboard tasks |
| RDS PostgreSQL 16 | Multi-AZ, encrypted, Performance Insights |
| ElastiCache Redis 7 | Feature store and profile cache |
| MSK Kafka | Managed transaction event streaming |
| ECR | Container image registry with vulnerability scanning |
| EFS | Shared ML model artifact store |
| ALB | Path-based routing (`/api/*` → API, `/` → Dashboard) |
| CloudWatch | Logs, alarms on 5xx rate > 1% and p99 latency > 2s |

---

## Fraud Patterns

The simulator injects six realistic fraud patterns:

| Pattern | Signal |
|---|---|
| `card_not_present` | Online purchase from foreign IP/location, high-risk merchant |
| `velocity_abuse` | Rapid succession of small transactions (20–60 per hour) |
| `amount_spike` | Single transaction 15–60× above 30-day average spend |
| `geo_anomaly` | Transaction location impossible to reach since last transaction |
| `account_takeover` | Wire transfer from new IP, sudden country change, night-time |
| `synthetic_id` | Unusual merchant diversity, high 7-day transaction count |

---

## ML Model Details

### Preprocessing

- **Numeric features** — median imputation + standard scaling
- **Binary features** — constant imputation (0)
- **Categorical features** — ordinal encoding with unknown handling

### Class imbalance

Real fraud rates are typically 0.1–3%. The pipeline uses SMOTE at a 15% minority-class ratio before fitting the ensemble, preventing the model from ignoring the minority class.

### Ensemble

The soft-vote ensemble combines Random Forest (weight 1) and XGBoost (weight 1.5). XGBoost receives higher weight because it delivers better precision on this feature set, while Random Forest provides diversity and stability.

### Threshold

The default decision threshold is **0.35** (lower than 0.5), tuned to maximize recall — catching more real fraud at the cost of some additional false positives, which are then resolved by analysts.

---

## API Reference

Full interactive documentation is available at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` once the API is running.

---

## Configuration

All configuration is loaded from environment variables (`.env` in local dev, ECS environment in AWS):

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=fraud_detection
POSTGRES_USER=fraud_user
POSTGRES_PASSWORD=fraud_secret

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC_TRANSACTIONS=transactions.raw
KAFKA_TOPIC_ALERTS=fraud.alerts
KAFKA_TOPIC_SCORED=transactions.scored

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# ML model
MODEL_PATH=../ml-engine/models/fraud_model.pkl
DEFAULT_FRAUD_THRESHOLD=0.35
ALERT_SCORE_THRESHOLD=0.55
AUTO_DECLINE_THRESHOLD=0.80

# Auth
SECRET_KEY=your-32-char-secret-key-here
```

---

## Key Metrics

| Dimension | Value |
|---|---|
| Total files | 69 |
| Lines of code | ~7,400 |
| ML features | 23 |
| Fraud patterns modeled | 6 |
| API endpoints | 18 |
| Test cases | 25 |
| Terraform modules | 6 |
| AWS services provisioned | 12 |
| CI/CD pipeline stages | 5 |
| Dashboard pages | 5 |
| Target inference latency | < 10ms |
| Auto-scaling range | 2–10 API tasks |
| Kafka partitions | 3 |
| RDS backup retention | 7 days |

---

## License

MIT
