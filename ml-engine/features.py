"""
ml-engine/features.py

Feature engineering pipeline.

Two modes:
  1. OFFLINE  — operates on a full Pandas DataFrame for training
  2. ONLINE   — operates on a single dict (from Kafka) + Redis lookups

The same FeaturePipeline class handles both so training and inference
always use identical transformations.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer


# ──────────────────────────────────────────────────────────────────────────────
# Feature schema — single source of truth
# ──────────────────────────────────────────────────────────────────────────────

NUMERIC_FEATURES = [
    "amount",
    "tx_count_1h",
    "tx_count_24h",
    "tx_count_7d",
    "amount_sum_1h",
    "amount_sum_24h",
    "amount_sum_7d",
    "avg_amount_30d",
    "std_amount_30d",
    "amount_zscore",
    "unique_merchants_7d",
    "unique_countries_7d",
    "geo_distance_km",
    "time_since_last_tx_min",
    "last_tx_amount",
    "merchant_fraud_rate_30d",
    "hour_of_day",
    "day_of_week",
]

BINARY_FEATURES = [
    "is_weekend",
    "is_night",
    "impossible_travel",
    "is_high_risk_merchant",
]

CATEGORICAL_FEATURES = [
    "channel",            # already int-encoded in dataset; keep as ordinal
    "transaction_type",
    "merchant_category",
]

ALL_FEATURES = NUMERIC_FEATURES + BINARY_FEATURES + CATEGORICAL_FEATURES
TARGET       = "is_fraud"


# ──────────────────────────────────────────────────────────────────────────────
# Custom transformers
# ──────────────────────────────────────────────────────────────────────────────

class AmountZScoreTransformer(BaseEstimator, TransformerMixin):
    """
    Recomputes amount z-score from the dataset's avg/std columns.
    Handles edge case where std is 0.
    """
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        df = pd.DataFrame(X, columns=self.feature_names_in_) if hasattr(self, "feature_names_in_") else pd.DataFrame(X)
        if "amount" in df.columns and "avg_amount_30d" in df.columns and "std_amount_30d" in df.columns:
            std = df["std_amount_30d"].replace(0, 1)
            df["amount_zscore"] = (df["amount"] - df["avg_amount_30d"]) / std
        return df.values


class VelocityRatioTransformer(BaseEstimator, TransformerMixin):
    """
    Adds derived velocity ratio: tx_count_1h / (tx_count_24h + 1).
    High ratios indicate sudden bursts.
    """
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        arr = np.array(X, dtype=float)
        # columns: tx_count_1h=0, tx_count_24h=1
        ratio = arr[:, 0] / (arr[:, 1] + 1)
        return np.column_stack([arr, ratio])


# ──────────────────────────────────────────────────────────────────────────────
# Sklearn ColumnTransformer pipeline
# ──────────────────────────────────────────────────────────────────────────────

def build_preprocessor() -> ColumnTransformer:
    """
    Returns a fitted-ready ColumnTransformer.
    Numeric features are imputed + scaled.
    Binary features pass through as-is.
    Categorical features get ordinal encoding.
    """
    numeric_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
    ])

    categorical_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])

    binary_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
    ])

    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe,     NUMERIC_FEATURES),
            ("bin", binary_pipe,      BINARY_FEATURES),
            ("cat", categorical_pipe, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def get_feature_names_out(preprocessor: ColumnTransformer) -> list[str]:
    """Return ordered feature names after transformation."""
    names = []
    for name, _, cols in preprocessor.transformers_:
        if name != "remainder":
            names.extend(cols)
    # velocity ratio is appended by VelocityRatioTransformer if used
    return names


# ──────────────────────────────────────────────────────────────────────────────
# Online feature computation (single transaction + Redis)
# ──────────────────────────────────────────────────────────────────────────────

def compute_online_features(tx: dict, redis_client) -> dict:
    """
    Given a raw transaction dict from Kafka and a Redis client,
    compute the full feature vector for real-time inference.

    Redis keys used:
      customer:<account_id>   → CustomerProfile JSON
      feats:<account_id>      → rolling aggregate JSON
    """
    account_id = tx.get("account_id", "")
    amount     = float(tx.get("amount", 0))

    # ── Load cached profile ───────────────────────────────────────────────────
    raw_profile = redis_client.get(f"customer:{account_id}")
    profile = json.loads(raw_profile) if raw_profile else {}
    avg_monthly = float(profile.get("avg_monthly_spend", 1000))
    avg_daily   = avg_monthly / 30
    home_lat    = float(profile.get("home_lat", 0))
    home_lon    = float(profile.get("home_lon", 0))
    last_lat    = float(profile.get("last_tx_lat") or home_lat)
    last_lon    = float(profile.get("last_tx_lon") or home_lon)

    # ── Load rolling aggregates ───────────────────────────────────────────────
    raw_feats = redis_client.get(f"feats:{account_id}")
    agg = json.loads(raw_feats) if raw_feats else {}

    tx_count_1h   = int(agg.get("tx_count_1h", 0))
    tx_count_24h  = int(agg.get("tx_count_24h", 0))
    tx_count_7d   = int(agg.get("tx_count_7d", 0))
    sum_1h        = float(agg.get("amount_sum_1h", 0))
    sum_24h       = float(agg.get("amount_sum_24h", 0))
    sum_7d        = float(agg.get("amount_sum_7d", 0))
    avg_30d       = float(agg.get("avg_amount_30d", avg_daily))
    std_30d       = float(agg.get("std_amount_30d", avg_daily * 0.4))
    uniq_merch_7d = int(agg.get("unique_merchants_7d", 1))
    uniq_ctry_7d  = int(agg.get("unique_countries_7d", 1))
    merch_fraud   = float(agg.get("merchant_fraud_rate_30d", 0.0))
    last_amount   = float(agg.get("last_tx_amount", avg_daily))
    time_since    = float(agg.get("time_since_last_tx_min", 300))

    # ── Derived features ──────────────────────────────────────────────────────
    from datetime import datetime
    now   = datetime.utcnow()
    hour  = now.hour
    dow   = now.weekday()

    tx_lat = float(tx.get("latitude") or home_lat)
    tx_lon = float(tx.get("longitude") or home_lon)
    geo_dist = _haversine(home_lat, home_lon, tx_lat, tx_lon)

    impossible = 0
    if time_since < 120 and geo_dist > 1000:   # >1000 km in <2h
        impossible = 1

    zscore = (amount - avg_30d) / max(std_30d, 1)

    # channel / tx_type / category encoded as integers (match training encoding)
    channel_map = {"card": 0, "online": 1, "mobile": 2, "atm": 3, "wire": 4}
    type_map    = {"purchase": 0, "online_purchase": 1, "atm_withdrawal": 2,
                   "transfer": 3, "international": 4, "refund": 5}
    cat_map     = {"retail": 0, "online_retail": 1, "food_beverage": 2, "fuel": 3,
                   "digital_services": 4, "atm": 5, "gambling": 6, "cryptocurrency": 7,
                   "money_transfer": 8, "travel": 9, "healthcare": 10, "education": 11}

    channel  = channel_map.get(tx.get("channel", "card"), 0)
    tx_type  = type_map.get(tx.get("transaction_type", "purchase"), 0)
    merchant = tx.get("merchant_category", "retail")
    cat      = cat_map.get(merchant, 0)
    high_risk = int(merchant in {"gambling", "cryptocurrency", "money_transfer"})

    return {
        "amount":                   amount,
        "tx_count_1h":              tx_count_1h,
        "tx_count_24h":             tx_count_24h,
        "tx_count_7d":              tx_count_7d,
        "amount_sum_1h":            sum_1h,
        "amount_sum_24h":           sum_24h,
        "amount_sum_7d":            sum_7d,
        "avg_amount_30d":           avg_30d,
        "std_amount_30d":           std_30d,
        "amount_zscore":            round(zscore, 4),
        "unique_merchants_7d":      uniq_merch_7d,
        "unique_countries_7d":      uniq_ctry_7d,
        "geo_distance_km":          round(geo_dist, 2),
        "time_since_last_tx_min":   time_since,
        "last_tx_amount":           last_amount,
        "merchant_fraud_rate_30d":  merch_fraud,
        "hour_of_day":              hour,
        "day_of_week":              dow,
        "is_weekend":               int(dow >= 5),
        "is_night":                 int(hour < 6 or hour >= 22),
        "impossible_travel":        impossible,
        "is_high_risk_merchant":    high_risk,
        "channel":                  channel,
        "transaction_type":         tx_type,
        "merchant_category":        cat,
    }


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0, a)))


def score_to_risk_tier(score: float) -> str:
    """Map a fraud probability (0-1) to a risk tier label."""
    if score >= 0.80:
        return "critical"
    elif score >= 0.55:
        return "high"
    elif score >= 0.30:
        return "medium"
    return "low"
