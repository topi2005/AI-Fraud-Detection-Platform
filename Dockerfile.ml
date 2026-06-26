# ── ML Engine — training + model artifact builder ────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY ml-engine/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.11-slim

RUN groupadd -r mluser && useradd -r -g mluser -d /app mluser

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY ml-engine/ ./

RUN mkdir -p /models /data && chown -R mluser:mluser /app /models /data
USER mluser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MLFLOW_TRACKING_URI=sqlite:////models/mlflow.db

# Volume mounts expected:
#   /models  → EFS model store (persistent)
#   /data    → S3-synced training data
CMD ["sh", "-c", \
  "python data/generate_dataset.py --out /data/transactions.csv && \
   python train.py --data /data/transactions.csv"]
