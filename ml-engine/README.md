# ML Engine — Phase 2

Trains a fraud detection ensemble (Random Forest + XGBoost) and exposes
a reusable `FraudScorer` class consumed by the FastAPI service in Phase 3.

## Directory layout

```
ml-engine/
├── data/
│   ├── generate_dataset.py   # synthetic labelled dataset generator
│   └── transactions.csv      # generated — git-ignored
├── models/
│   ├── fraud_model.pkl       # trained pipeline — git-ignored
│   ├── model_meta.json       # version, threshold, metrics
│   ├── mlflow.db             # local MLflow tracking store
│   └── plots/                # confusion matrix, PR/ROC curves, feature importance
├── features.py               # feature schema + engineering (offline + online)
├── inference.py              # FraudScorer wrapper (used by API)
├── train.py                  # training script
├── Dockerfile
└── requirements.txt
```

## Quick start

```bash
cd ml-engine
pip install -r requirements.txt

# 1. Generate 100 k synthetic labelled transactions
python data/generate_dataset.py --rows 100000

# 2. Train the ensemble (~2-3 min on a laptop)
python train.py

# 3. (Optional) View MLflow UI
mlflow ui --backend-store-uri sqlite:///models/mlflow.db
# → open http://localhost:5000

# 4. Smoke-test inference
python inference.py
```

## Model details

| Component        | Algorithm               | Purpose                          |
|-----------------|------------------------|----------------------------------|
| Preprocessor     | ColumnTransformer       | Impute, scale, encode features   |
| Oversampling     | SMOTE (ratio 0.15)      | Handle class imbalance           |
| Classifier 1     | Random Forest (n=300)   | High recall, interpretable       |
| Classifier 2     | XGBoost (n=400)         | High precision, gradient boosted |
| Ensemble         | Soft-vote (w 1:1.5)     | Best of both                     |

## Feature groups

- **Velocity** — tx_count_1h/24h/7d, amount_sum windows
- **Behavioural** — amount z-score vs 30-day baseline, unique merchants
- **Geo anomaly** — distance from home, impossible travel flag
- **Temporal** — hour of day, day of week, is_night, is_weekend
- **Merchant risk** — merchant fraud rate, high-risk category flag

## Risk tiers

| Score      | Tier     | Action                        |
|-----------|---------|-------------------------------|
| ≥ 0.80    | critical | Auto-decline + alert analyst  |
| 0.55–0.80 | high     | Flag for review               |
| 0.30–0.55 | medium   | Monitor, soft challenge       |
| < 0.30    | low      | Approve                       |
