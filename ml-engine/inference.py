"""
ml-engine/inference.py

Lightweight inference wrapper around the trained pipeline.
Used directly by the FastAPI risk-scoring service (Phase 3).

Usage:
    scorer = FraudScorer()
    result = scorer.score(transaction_dict, redis_client)
    # result → ScoringResult(fraud_score=0.87, risk_tier='critical', …)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Any

import joblib
import numpy as np
import pandas as pd

from features import ALL_FEATURES, compute_online_features, score_to_risk_tier

log = logging.getLogger("inference")

MODELS_DIR    = Path(__file__).parent / "models"
MODEL_PATH    = MODELS_DIR / "fraud_model.pkl"
META_PATH     = MODELS_DIR / "model_meta.json"


@dataclass
class ScoringResult:
    tx_id:          str
    account_id:     str
    fraud_score:    float          # 0.0 – 1.0
    risk_tier:      str            # low | medium | high | critical
    is_fraud_pred:  bool           # threshold applied
    threshold:      float
    model_version:  str
    latency_ms:     float
    features:       Optional[dict] = None   # returned only in debug mode

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class FraudScorer:
    """
    Thread-safe, singleton-style scorer.
    Load once at startup, call score() many times.
    """

    def __init__(self, model_path: str = str(MODEL_PATH)):
        self._model     = None
        self._meta      = {}
        self._threshold = 0.35
        self._version   = "unknown"
        self._load(model_path)

    def _load(self, path: str):
        log.info("Loading fraud model from %s …", path)
        if not Path(path).exists():
            raise FileNotFoundError(
                f"Model not found at {path}. Run `python train.py` first."
            )
        self._model = joblib.load(path)

        meta_path = Path(path).parent / "model_meta.json"
        if meta_path.exists():
            self._meta      = json.loads(meta_path.read_text())
            self._threshold = self._meta.get("threshold", 0.35)
            self._version   = self._meta.get("model_version", "unknown")

        log.info("Model loaded ✅  version=%s  threshold=%.2f", self._version, self._threshold)

    def score(
        self,
        tx: dict,
        redis_client=None,
        debug: bool = False,
    ) -> ScoringResult:
        """
        Score a single transaction dict.

        tx must contain at minimum:
          tx_id, account_id, amount, channel, transaction_type

        redis_client (optional): used for online feature computation.
        If None, only the fields present in tx are used (batch mode).
        """
        t0 = time.perf_counter()

        # ── Feature extraction ────────────────────────────────────────────────
        if redis_client is not None:
            feats = compute_online_features(tx, redis_client)
        else:
            # Batch / offline mode: tx dict is expected to already have all features
            feats = {k: tx.get(k, 0) for k in ALL_FEATURES}

        feat_df = pd.DataFrame([feats])[ALL_FEATURES]

        # ── Inference ─────────────────────────────────────────────────────────
        proba      = float(self._model.predict_proba(feat_df)[0, 1])
        risk_tier  = score_to_risk_tier(proba)
        is_fraud   = proba >= self._threshold
        latency_ms = (time.perf_counter() - t0) * 1000

        return ScoringResult(
            tx_id         = tx.get("tx_id", ""),
            account_id    = tx.get("account_id", ""),
            fraud_score   = round(proba, 4),
            risk_tier     = risk_tier,
            is_fraud_pred = is_fraud,
            threshold     = self._threshold,
            model_version = self._version,
            latency_ms    = round(latency_ms, 2),
            features      = feats if debug else None,
        )

    def score_batch(self, txns: list[dict]) -> list[ScoringResult]:
        """
        Score a list of transactions without Redis lookups.
        Useful for batch reprocessing historical data.
        """
        rows = [{k: tx.get(k, 0) for k in ALL_FEATURES} for tx in txns]
        feat_df = pd.DataFrame(rows)[ALL_FEATURES]
        probas  = self._model.predict_proba(feat_df)[:, 1]

        results = []
        for tx, proba in zip(txns, probas):
            p = float(proba)
            results.append(ScoringResult(
                tx_id         = tx.get("tx_id", ""),
                account_id    = tx.get("account_id", ""),
                fraud_score   = round(p, 4),
                risk_tier     = score_to_risk_tier(p),
                is_fraud_pred = p >= self._threshold,
                threshold     = self._threshold,
                model_version = self._version,
                latency_ms    = 0.0,
            ))
        return results

    @property
    def meta(self) -> dict:
        return self._meta

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float):
        if not 0 < value < 1:
            raise ValueError("Threshold must be between 0 and 1")
        self._threshold = value
        log.info("Threshold updated → %.3f", value)


# ── Quick smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    scorer = FraudScorer()

    sample_normal = {
        "tx_id": "test-001", "account_id": "acc-abc",
        "amount": 45.0, "channel": 0, "transaction_type": 0,
        "merchant_category": 0, "hour_of_day": 14, "day_of_week": 2,
        "is_weekend": 0, "is_night": 0, "tx_count_1h": 1, "tx_count_24h": 3,
        "tx_count_7d": 12, "amount_sum_1h": 45, "amount_sum_24h": 120,
        "amount_sum_7d": 800, "avg_amount_30d": 50, "std_amount_30d": 20,
        "amount_zscore": -0.25, "unique_merchants_7d": 5,
        "unique_countries_7d": 1, "geo_distance_km": 3.2,
        "time_since_last_tx_min": 480, "impossible_travel": 0,
        "last_tx_amount": 62, "merchant_fraud_rate_30d": 0.002,
        "is_high_risk_merchant": 0,
    }

    sample_fraud = {**sample_normal,
        "tx_id": "test-002", "amount": 8500.0,
        "channel": 4, "transaction_type": 3,   # wire / transfer
        "amount_zscore": 22.5, "geo_distance_km": 9500,
        "impossible_travel": 1, "is_night": 1,
        "unique_countries_7d": 4, "is_high_risk_merchant": 1,
    }

    for tx in [sample_normal, sample_fraud]:
        r = scorer.score(tx, debug=True)
        print(f"\n[{r.tx_id}] score={r.fraud_score:.4f}  tier={r.risk_tier}  fraud={r.is_fraud_pred}  latency={r.latency_ms:.1f}ms")
