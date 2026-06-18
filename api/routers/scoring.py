"""
api/routers/scoring.py
POST /api/v1/score          — score a single transaction
POST /api/v1/score/batch    — score up to 500 transactions
GET  /api/v1/model/health   — model metadata + metrics
"""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from config import get_settings
from dependencies import get_pg_connection, get_redis, get_scorer, get_kafka_producer
from middleware.auth import get_current_user
from schemas import (
    TransactionScoreRequest, TransactionScoreResponse,
    BatchScoreRequest, BatchScoreResponse,
    ModelHealthResponse,
)
from services.alert_service import create_alert

log    = logging.getLogger("api.scoring")
router = APIRouter(prefix="/api/v1", tags=["Scoring"])


def _build_tx_dict(req: TransactionScoreRequest) -> dict:
    """Convert request schema to the dict format expected by FraudScorer."""
    return {
        "tx_id":              req.tx_id,
        "account_id":         req.account_id,
        "amount":             req.amount,
        "currency":           req.currency,
        "transaction_type":   req.transaction_type,
        "channel":            req.channel,
        "ip_address":         req.ip_address,
        "latitude":           req.latitude,
        "longitude":          req.longitude,
        "country_code":       req.country_code,
        "city":               req.city or "",
        "merchant_category":  req.merchant_category or "retail",
        "merchant_id":        req.merchant_id or "",
        "initiated_at":       (req.initiated_at or datetime.utcnow()).isoformat(),
    }


def _persist_score(pg_conn, tx_id: str, account_id: str, result, req: TransactionScoreRequest):
    """Write transaction + feature score back to Postgres."""
    try:
        cur = pg_conn.cursor()

        # Upsert transaction record (may already exist from Kafka consumer)
        cur.execute("""
            INSERT INTO transactions (
                id, external_tx_id, account_id,
                amount, currency, transaction_type, channel,
                ip_address, latitude, longitude, country_code, city,
                fraud_score, risk_tier, model_version, scored_at,
                status, initiated_at, created_at
            ) VALUES (
                %s, %s,
                (SELECT id FROM accounts WHERE id::text = %s LIMIT 1),
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, NOW()
            )
            ON CONFLICT (external_tx_id) DO UPDATE SET
                fraud_score   = EXCLUDED.fraud_score,
                risk_tier     = EXCLUDED.risk_tier,
                model_version = EXCLUDED.model_version,
                scored_at     = EXCLUDED.scored_at,
                status        = CASE
                    WHEN EXCLUDED.risk_tier IN ('high','critical') THEN 'flagged'
                    ELSE transactions.status
                END
        """, (
            str(uuid.uuid4()), req.tx_id, account_id,
            req.amount, req.currency, req.transaction_type, req.channel,
            req.ip_address, req.latitude, req.longitude, req.country_code, req.city,
            result.fraud_score, result.risk_tier, result.model_version,
            datetime.utcnow(),
            "flagged" if result.risk_tier in ("high", "critical") else "pending",
            req.initiated_at or datetime.utcnow(),
        ))
    except Exception as e:
        log.warning("Could not persist score to DB (non-fatal): %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/score",
    response_model=TransactionScoreResponse,
    summary="Score a single transaction for fraud",
    status_code=status.HTTP_200_OK,
)
async def score_transaction(
    req:      TransactionScoreRequest,
    user:     dict            = Depends(get_current_user),
    pg_conn                   = Depends(get_pg_connection),
    redis_cli                 = Depends(get_redis),
    scorer                    = Depends(get_scorer),
    kafka                     = Depends(get_kafka_producer),
):
    if scorer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML model not loaded. Run `python train.py` in ml-engine/ first.",
        )

    settings  = get_settings()
    tx_dict   = _build_tx_dict(req)

    # ── Score ─────────────────────────────────────────────────────────────────
    result = scorer.score(tx_dict, redis_client=redis_cli, debug=True)

    # ── Persist ───────────────────────────────────────────────────────────────
    _persist_score(pg_conn, req.tx_id, req.account_id, result, req)

    # ── Alert ─────────────────────────────────────────────────────────────────
    alert_created = False
    if result.risk_tier in ("high", "critical"):
        alert = create_alert(
            pg_conn=pg_conn,
            kafka_producer=kafka,
            kafka_topic=settings.kafka_topic_alerts,
            transaction_id=req.tx_id,
            fraud_score=result.fraud_score,
            features=result.features,
        )
        alert_created = alert is not None

    # ── Publish scored event to Kafka ─────────────────────────────────────────
    if kafka:
        try:
            scored_event = {**tx_dict, "fraud_score": result.fraud_score,
                            "risk_tier": result.risk_tier, "is_fraud_pred": result.is_fraud_pred}
            kafka.send(settings.kafka_topic_scored, key=req.account_id,
                       value=json.dumps(scored_event))
        except Exception as e:
            log.warning("Failed to publish scored event: %s", e)

    return TransactionScoreResponse(
        tx_id         = result.tx_id,
        account_id    = result.account_id,
        fraud_score   = result.fraud_score,
        risk_tier     = result.risk_tier,
        is_fraud_pred = result.is_fraud_pred,
        threshold     = result.threshold,
        model_version = result.model_version,
        latency_ms    = result.latency_ms,
        alert_created = alert_created,
    )


@router.post(
    "/score/batch",
    response_model=BatchScoreResponse,
    summary="Score up to 500 transactions in one call",
)
async def score_batch(
    req:    BatchScoreRequest,
    user:   dict = Depends(get_current_user),
    scorer       = Depends(get_scorer),
):
    if scorer is None:
        raise HTTPException(status_code=503, detail="ML model not loaded.")

    t0       = time.perf_counter()
    tx_dicts = [_build_tx_dict(t) for t in req.transactions]
    results  = scorer.score_batch(tx_dicts)
    elapsed  = (time.perf_counter() - t0) * 1000

    responses = [
        TransactionScoreResponse(
            tx_id         = r.tx_id,
            account_id    = r.account_id,
            fraud_score   = r.fraud_score,
            risk_tier     = r.risk_tier,
            is_fraud_pred = r.is_fraud_pred,
            threshold     = r.threshold,
            model_version = r.model_version,
            latency_ms    = r.latency_ms,
        )
        for r in results
    ]

    return BatchScoreResponse(
        results     = responses,
        total       = len(results),
        fraud_count = sum(1 for r in results if r.is_fraud_pred),
        latency_ms  = round(elapsed, 2),
    )


@router.get(
    "/model/health",
    response_model=ModelHealthResponse,
    summary="Model metadata and performance metrics",
)
async def model_health(
    user:   dict = Depends(get_current_user),
    scorer       = Depends(get_scorer),
):
    if scorer is None:
        return ModelHealthResponse(
            model_version="N/A", threshold=0.35,
            model_loaded=False,
        )

    meta = scorer.meta
    return ModelHealthResponse(
        model_version = meta.get("model_version", "unknown"),
        threshold     = scorer.threshold,
        roc_auc       = meta.get("roc_auc"),
        avg_precision = meta.get("avg_precision"),
        f1            = meta.get("f1"),
        precision     = meta.get("precision"),
        recall        = meta.get("recall"),
        model_loaded  = True,
    )
